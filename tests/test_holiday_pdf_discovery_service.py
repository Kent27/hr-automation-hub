from pathlib import Path

import pytest

from app.services.holiday_pdf_discovery_service import HolidayPdfDiscoveryService


VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _build_fetcher(mapping: dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        payload = mapping.get(url)
        if payload is None:
            raise ValueError(f"Missing fake payload for URL: {url}")
        return payload

    return _fetch


def test_discover_and_download_selects_best_trusted_candidate(tmp_path: Path):
    seed_url = "https://kemenkopmk.go.id/berita"
    trusted_pdf_url = "https://kemenkopmk.go.id/media/skb-libur-nasional-dan-cuti-bersama-2026.pdf"
    untrusted_pdf_url = "https://example.com/libur-nasional-2026.pdf"

    html = f"""
    <html>
      <body>
        <a href=\"{untrusted_pdf_url}\">Hari Libur Nasional 2026</a>
        <a href=\"{trusted_pdf_url}\">SKB Hari Libur Nasional dan Cuti Bersama 2026</a>
      </body>
    </html>
    """

    service = HolidayPdfDiscoveryService(
        seed_urls=[seed_url],
        allowed_domain_suffixes=[".go.id"],
        output_dir=tmp_path,
        fetcher=_build_fetcher(
            {
                seed_url: html.encode("utf-8"),
                trusted_pdf_url: VALID_PDF_BYTES,
            }
        ),
    )

    result = service.discover_and_download(year=2026)

    assert result.source_url == trusted_pdf_url
    assert result.pdf_path.exists()
    assert result.pdf_path.read_bytes().startswith(b"%PDF")


def test_discover_and_download_falls_back_when_first_candidate_is_not_pdf(tmp_path: Path):
    seed_url = "https://setkab.go.id/publikasi"
    first_pdf_url = "https://setkab.go.id/files/skb-libur-nasional-2026.pdf"
    second_pdf_url = "https://setkab.go.id/files/lampiran-cuti-bersama-2026.pdf"

    html = f"""
    <html>
      <body>
        <a href=\"{first_pdf_url}\">SKB Hari Libur Nasional 2026</a>
        <a href=\"{second_pdf_url}\">Lampiran Cuti Bersama 2026</a>
      </body>
    </html>
    """

    service = HolidayPdfDiscoveryService(
        seed_urls=[seed_url],
        allowed_domain_suffixes=[".go.id"],
        output_dir=tmp_path,
        fetcher=_build_fetcher(
            {
                seed_url: html.encode("utf-8"),
                first_pdf_url: b"<html>not-a-pdf</html>",
                second_pdf_url: VALID_PDF_BYTES,
            }
        ),
    )

    result = service.discover_and_download(year=2026)

    assert result.source_url == second_pdf_url
    assert result.pdf_path.exists()


def test_discover_candidates_raises_when_no_pdf_links_found(tmp_path: Path):
    seed_url = "https://kemenkopmk.go.id/berita"
    html = "<html><body><a href='/news'>No PDF here</a></body></html>"

    service = HolidayPdfDiscoveryService(
        seed_urls=[seed_url],
        allowed_domain_suffixes=[".go.id"],
        output_dir=tmp_path,
        fetcher=_build_fetcher({seed_url: html.encode("utf-8")}),
    )

    with pytest.raises(ValueError, match="No holiday PDF candidates"):
        service.discover_and_download(year=2026)
