"""Polite fetching from Basketball-Reference.

Its robots.txt asks for a 3-second crawl delay, so requests are spaced out,
and every page is cached on disk so a rerun never asks twice for the same game.
"""

import time
from pathlib import Path

import requests

BASE = "https://www.basketball-reference.com"
USER_AGENT = "points-above-average/0.1 (personal stats page; github.com/tenache/points-above-average)"
DELAY = 4.0  # seconds between requests, above the 3 s robots.txt asks for


class Fetcher:
    def __init__(self, cache_dir=None, delay=DELAY, session=None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.delay = delay
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0
        self.requests_made = 0

    def get(self, path, use_cache=True):
        cached = self._cache_path(path)
        if use_cache and cached and cached.exists():
            return cached.read_text(encoding="utf-8")
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        response = self.session.get(BASE + path, timeout=30)
        self._last = time.monotonic()
        self.requests_made += 1
        if response.status_code == 429:
            raise RuntimeError("Basketball-Reference says too many requests (429); stopping")
        response.raise_for_status()
        response.encoding = "utf-8"
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(response.text, encoding="utf-8")
        return response.text

    def _cache_path(self, path):
        if not self.cache_dir:
            return None
        name = path.strip("/").replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
        return self.cache_dir / name


def schedule_path(season_end_year, month_name):
    return f"/leagues/NBA_{season_end_year}_games-{month_name}.html"


def pbp_path(game_id):
    return f"/boxscores/pbp/{game_id}.html"


def totals_path(season_end_year):
    return f"/leagues/NBA_{season_end_year}_totals.html"
