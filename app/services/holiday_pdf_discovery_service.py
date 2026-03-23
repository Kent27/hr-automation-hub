from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib import error, parse, request

from app.config import (
    HOLIDAY_DISCOVERY_ALLOWED_DOMAIN_SUFFIXES,
    HOLIDAY_DISCOVERY_MAX_CANDIDATES,
    HOLIDAY_DISCOVERY_MAX_PDF_BYTES,
    HOLIDAY_DISCOVERY_OUTPUT_DIR,
    HOLIDAY_DISCOVERY_SEED_URLS,
    HOLIDAY_DISCOVERY_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_KEYWORD_WEIGHTS = {
    "libur": 5,
    "cuti": 4,
    "bersama": 2,
    "nasional": 2,
    "kalender": 2,
    "skb": 3,
    "keputusan": 2,
    "surat": 1,
}


@dataclass(frozen=True)
class HolidayPdfCandidate:
    url: str
    source_page: str
    anchor_text: str
    score: int


@dataclass(frozen=True)
class HolidayPdfDiscoveryResult:
    pdf_path: Path
    source_url: str
    source_page: str
    score: int

    def to_dict(self) -> dict[str, object]:
        return {
            "pdf_path": str(self.pdf_path),
            "source_url": self.source_url,
            "source_page": self.source_page,
            "score": self.score,
        }


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: List[tuple[str, str]] = []
        self._current_href: Optional[str] = None
        self._current_text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        href = next(
            (
                (value or "").strip()
                for key, value in attrs
                if key.lower() == "href" and value is not None
            ),
            "",
        )
        if not href:
            return
        self._current_href = href
        self._current_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None and data.strip():
            self._current_text_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        anchor_text = " ".join(self._current_text_parts).strip()
        self.links.append((self._current_href, anchor_text))
        self._current_href = None
        self._current_text_parts = []


class HolidayPdfDiscoveryService:
    def __init__(
        self,
        seed_urls: Iterable[str] = HOLIDAY_DISCOVERY_SEED_URLS,
        allowed_domain_suffixes: Iterable[str] = HOLIDAY_DISCOVERY_ALLOWED_DOMAIN_SUFFIXES,
        output_dir: Path = HOLIDAY_DISCOVERY_OUTPUT_DIR,
        timeout_seconds: int = HOLIDAY_DISCOVERY_TIMEOUT_SECONDS,
        max_pdf_bytes: int = HOLIDAY_DISCOVERY_MAX_PDF_BYTES,
        max_candidates: int = HOLIDAY_DISCOVERY_MAX_CANDIDATES,
        fetcher: Optional[Callable[[str], bytes]] = None,
    ):
        self.seed_urls = [value.strip() for value in seed_urls if value and value.strip()]
        self.allowed_domain_suffixes = [
            value.strip().lower()
            for value in allowed_domain_suffixes
            if value and value.strip()
        ]
        self.output_dir = output_dir
        self.timeout_seconds = max(1, timeout_seconds)
        self.max_pdf_bytes = max(1024, max_pdf_bytes)
        self.max_candidates = max(1, max_candidates)
        self.fetcher = fetcher

    def discover_and_download(
        self,
        year: int,
        extra_seed_urls: Optional[Iterable[str]] = None,
    ) -> HolidayPdfDiscoveryResult:
        if year < 2000 or year > 2100:
            raise ValueError("Year must be between 2000 and 2100")

        candidates = self.discover_candidates(year=year, extra_seed_urls=extra_seed_urls)
        for candidate in candidates[: self.max_candidates]:
            try:
                pdf_bytes = self._fetch_bytes(candidate.url)
                self._validate_pdf_bytes(pdf_bytes)
            except Exception as exc:
                logger.warning("Skipping PDF candidate %s: %s", candidate.url, exc)
                continue

            pdf_path = self._write_pdf(candidate.url, pdf_bytes, year)
            return HolidayPdfDiscoveryResult(
                pdf_path=pdf_path,
                source_url=candidate.url,
                source_page=candidate.source_page,
                score=candidate.score,
            )

        raise ValueError("Failed to download a valid holiday PDF from trusted candidates")

    def discover_candidates(
        self,
        year: int,
        extra_seed_urls: Optional[Iterable[str]] = None,
    ) -> List[HolidayPdfCandidate]:
        candidates_by_url: dict[str, HolidayPdfCandidate] = {}

        for candidate in self._known_direct_pdf_candidates(year):
            candidates_by_url[candidate.url] = candidate

        for seed_url in self._merge_seed_urls(extra_seed_urls):
            if not self._is_allowed_url(seed_url):
                logger.warning("Skipping untrusted seed URL: %s", seed_url)
                continue

            if self._looks_like_pdf_url(seed_url):
                score = self._score_candidate(seed_url, "", year)
                candidates_by_url[seed_url] = HolidayPdfCandidate(
                    url=seed_url,
                    source_page=seed_url,
                    anchor_text="",
                    score=score,
                )
                continue

            try:
                page_bytes = self._fetch_bytes(seed_url)
                page_links = self._extract_links(seed_url, page_bytes)
            except Exception as exc:
                logger.warning("Failed to read seed page %s: %s", seed_url, exc)
                continue

            for url, anchor_text in page_links:
                if not self._looks_like_pdf_url(url):
                    continue
                if not self._is_allowed_url(url):
                    continue

                score = self._score_candidate(url, anchor_text, year)
                if score <= 0:
                    continue

                existing = candidates_by_url.get(url)
                if existing is None or score > existing.score:
                    candidates_by_url[url] = HolidayPdfCandidate(
                        url=url,
                        source_page=seed_url,
                        anchor_text=anchor_text,
                        score=score,
                    )

        candidates = sorted(
            candidates_by_url.values(), key=lambda candidate: candidate.score, reverse=True
        )
        if not candidates:
            raise ValueError("No holiday PDF candidates found on trusted domains")
        return candidates



    def _known_direct_pdf_candidates(self, year: int) -> List[HolidayPdfCandidate]:
        candidates: List[HolidayPdfCandidate] = []

        bi_urls = [
            f"https://www.bi.go.id/id/publikasi/Kalender/Documents/Kalender-Libur-BI-{year}.pdf",
            f"https://www.bi.go.id/id/publikasi/Kalender/Documents/Kalender-Libur-BI_{year}.pdf",
        ]

        for url in bi_urls:
            if not self._is_allowed_url(url):
                continue
            score = self._score_candidate(url, "Bank Indonesia kalender libur", year) + 5
            candidates.append(
                HolidayPdfCandidate(
                    url=url,
                    source_page="known-pattern:bi.go.id",
                    anchor_text="Bank Indonesia calendar direct PDF pattern",
                    score=score,
                )
            )

        return candidates
    def _merge_seed_urls(self, extra_seed_urls: Optional[Iterable[str]]) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()

        for raw_url in [*self.seed_urls, *(extra_seed_urls or [])]:
            normalized = (raw_url or "").strip().split("#", 1)[0]
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)

        return merged

    def _extract_links(self, base_url: str, html_bytes: bytes) -> List[tuple[str, str]]:
        parser = _AnchorParser()
        parser.feed(html_bytes.decode("utf-8", errors="ignore"))
        parser.close()

        links: List[tuple[str, str]] = []
        for href, anchor_text in parser.links:
            absolute_url = parse.urljoin(base_url, href).split("#", 1)[0]
            if absolute_url:
                links.append((absolute_url, anchor_text))
        return links

    @staticmethod
    def _looks_like_pdf_url(url: str) -> bool:
        parsed = parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()
        return path.endswith(".pdf") or ".pdf" in path or "pdf" in query

    def _is_allowed_url(self, url: str) -> bool:
        parsed = parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").lower()
        if not host:
            return False

        for suffix in self.allowed_domain_suffixes:
            if suffix.startswith("."):
                if host.endswith(suffix):
                    return True
                continue

            if host == suffix or host.endswith(f".{suffix}"):
                return True

        return False

    def _score_candidate(self, url: str, anchor_text: str, year: int) -> int:
        haystack = f"{url} {anchor_text}".lower()
        score = 0

        if str(year) in haystack:
            score += 20

        for keyword, weight in _KEYWORD_WEIGHTS.items():
            if keyword in haystack:
                score += weight

        if self._looks_like_pdf_url(url):
            score += 3

        if ".go.id" in haystack:
            score += 2

        if score > 0 and str(year) not in haystack:
            score -= 4

        return score

    def _fetch_bytes(self, url: str) -> bytes:
        if self.fetcher:
            return self.fetcher(url)

        req = request.Request(
            url,
            headers={
                "Accept": "text/html,application/pdf,*/*;q=0.8",
                "User-Agent": "hr-automation-hub/1.0",
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = response.read(self.max_pdf_bytes + 1)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"HTTP {exc.code} while fetching {url}: {detail}")
        except error.URLError as exc:
            raise ValueError(f"Failed to fetch {url}: {exc.reason}")

        if len(payload) > self.max_pdf_bytes:
            raise ValueError(f"Response too large from {url}")
        return payload

    def _validate_pdf_bytes(self, payload: bytes) -> None:
        if not payload:
            raise ValueError("Empty response")
        if len(payload) > self.max_pdf_bytes:
            raise ValueError("PDF exceeds configured size limit")
        if not payload.lstrip().startswith(b"%PDF"):
            raise ValueError("Response is not a PDF")

    def _write_pdf(self, source_url: str, payload: bytes, year: int) -> Path:
        parsed = parse.urlparse(source_url)
        source_name = Path(parsed.path).name or f"holiday-{year}.pdf"
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", source_name).strip("-")
        if not sanitized:
            sanitized = f"holiday-{year}.pdf"
        if not sanitized.lower().endswith(".pdf"):
            sanitized += ".pdf"

        digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:10]
        output_name = f"{year}-{digest}-{sanitized}"
        output_path = self.output_dir / output_name

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        return output_path


holiday_pdf_discovery_service = HolidayPdfDiscoveryService()
