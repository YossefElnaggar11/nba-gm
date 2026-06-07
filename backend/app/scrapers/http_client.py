"""Shared HTTP client for scrapers. Real browser headers + polite throttling."""
from __future__ import annotations

import time
from pathlib import Path

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "html_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_last_request_at: dict[str, float] = {}
MIN_INTERVAL_SEC = 3.0  # be polite per-host


def _host(url: str) -> str:
    return url.split("/")[2]


def get(url: str, *, use_cache: bool = True, timeout: float = 20.0) -> str:
    """GET with browser headers, per-host throttling, and on-disk caching."""
    cache_key = url.replace("/", "_").replace(":", "").replace("?", "_")[:200]
    cache_file = CACHE_DIR / f"{cache_key}.html"
    if use_cache and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    host = _host(url)
    last = _last_request_at.get(host, 0.0)
    delta = time.time() - last
    if delta < MIN_INTERVAL_SEC:
        time.sleep(MIN_INTERVAL_SEC - delta)

    r = httpx.get(url, headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True)
    _last_request_at[host] = time.time()
    r.raise_for_status()
    cache_file.write_text(r.text, encoding="utf-8")
    return r.text
