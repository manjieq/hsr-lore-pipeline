"""MediaWiki API client for the HSR Fandom wiki.

Every request is cached to disk (data/raw_cache/wiki/) so re-running the
scraper doesn't re-hit the wiki for pages it already has. Requests are
politely rate-limited and retried with backoff on transient errors.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path

import requests

API_URL = "https://honkai-star-rail.fandom.com/api.php"
USER_AGENT = (
    "hsr-lore-pipeline/0.1 "
    "(personal, non-commercial fan project; contact: eman80102909@gmail.com)"
)
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_cache" / "wiki"
MIN_DELAY_SECONDS = 1.0

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_last_request_time = 0.0


def _cache_path_for(params: dict) -> Path:
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _throttle() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    wait = MIN_DELAY_SECONDS - elapsed + random.uniform(0, 0.4)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.monotonic()


def api_get(params: dict, refresh: bool = False) -> dict:
    """GET against the MediaWiki API, cached to disk. Pass refresh=True to
    bypass the cache and re-fetch."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path_for(params)
    if not refresh and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    backoff = 2.0
    last_status = None
    for _ in range(5):
        _throttle()
        resp = _session.get(API_URL, params=params, timeout=20)
        last_status = resp.status_code
        if resp.status_code == 200:
            data = resp.json()
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(backoff)
            backoff *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"MediaWiki API request failed after retries (status {last_status}): {params}")


def get_category_members(category_title: str, refresh: bool = False) -> list[str]:
    """Return every article page title in a category (subcategories are
    excluded via cmtype=page), paginating via cmcontinue."""
    titles: list[str] = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmtype": "page",
            "cmlimit": 500,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params, refresh=refresh)
        titles.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def get_page_wikitext(title: str, refresh: bool = False) -> str:
    """Fetch the raw wikitext source for a page."""
    params = {"action": "parse", "page": title, "prop": "wikitext", "format": "json"}
    data = api_get(params, refresh=refresh)
    return data["parse"]["wikitext"]["*"]
