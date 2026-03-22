from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, request

from app.config import (
    FX_RATE_CACHE_SECONDS,
    FX_REQUEST_TIMEOUT_SECONDS,
    FX_USD_IDR_API_URL,
)


@dataclass(frozen=True)
class ExchangeRateQuote:
    rate: float
    provider: Optional[str]
    as_of: Optional[str]
    source_url: str


class ExchangeRateService:
    def __init__(
        self,
        usd_idr_api_url: str = FX_USD_IDR_API_URL,
        timeout_seconds: int = FX_REQUEST_TIMEOUT_SECONDS,
        cache_seconds: int = FX_RATE_CACHE_SECONDS,
    ):
        self.usd_idr_api_url = usd_idr_api_url
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = max(0, cache_seconds)
        self._cached_quote: Optional[ExchangeRateQuote] = None
        self._cached_at: float = 0.0

    def get_usd_to_idr_quote(self) -> ExchangeRateQuote:
        now = time.time()
        if (
            self._cached_quote is not None
            and self.cache_seconds > 0
            and (now - self._cached_at) <= self.cache_seconds
        ):
            return self._cached_quote

        req = request.Request(
            self.usd_idr_api_url,
            headers={"Accept": "application/json"},
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_response = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Exchange rate API returned HTTP {exc.code}: {detail}")
        except error.URLError as exc:
            raise ValueError(f"Failed to reach exchange rate API: {exc.reason}")

        payload = self._safe_load_json(raw_response)
        if payload.get("result") not in {None, "success"}:
            raise ValueError(f"Exchange rate API error: {payload}")

        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise ValueError("Exchange rate API response missing 'rates'")

        raw_rate = rates.get("IDR")
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid USD->IDR rate from API: {raw_rate}")

        if rate <= 0:
            raise ValueError(f"Invalid USD->IDR rate from API: {rate}")

        provider = payload.get("provider") if isinstance(payload.get("provider"), str) else None
        as_of = (
            payload.get("time_last_update_utc")
            if isinstance(payload.get("time_last_update_utc"), str)
            else None
        )

        quote = ExchangeRateQuote(
            rate=rate,
            provider=provider,
            as_of=as_of,
            source_url=self.usd_idr_api_url,
        )

        self._cached_quote = quote
        self._cached_at = now
        return quote

    def get_usd_to_idr_rate(self) -> float:
        return self.get_usd_to_idr_quote().rate

    @staticmethod
    def _safe_load_json(text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
        return {}


exchange_rate_service = ExchangeRateService()
