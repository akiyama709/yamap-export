"""Thin client over YAMAP's public JSON API.

Everything here works without logging in, because YAMAP serves public
activities and photos anonymously. The one exception is the GPS track
(``points.xml``), which lives in :mod:`yamap_export.gpx` because it needs
your login token.
"""

from __future__ import annotations

import re
import time
from typing import Dict, Iterator, List, Optional

import requests

API_BASE = "https://api.yamap.com"
# The API rejects any User-Agent starting with "yamap" as an outdated mobile
# app (HTTP 490). Lead with a browser token so we are treated as a web client,
# while still identifying this tool honestly.
USER_AGENT = (
    "Mozilla/5.0 (compatible) "
    "yamap-export/0.1 (+https://github.com/akiyama709/yamap-export)"
)


class YamapError(RuntimeError):
    pass


class YamapClient:
    """Polite, retrying client for api.yamap.com."""

    def __init__(self, delay: float = 1.0, timeout: float = 30.0,
                 max_retries: int = 4, language: str = "ja"):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            # Without this, place names and tags come back in English.
            "Accept-Language": language,
        })

    # -- low level ---------------------------------------------------------
    def _get(self, url: str, **kw) -> requests.Response:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, timeout=self.timeout, **kw)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise YamapError(f"HTTP {r.status_code} for {url}")
                return r
            except (requests.RequestException, YamapError) as e:
                last = e
                # exponential backoff: 1s, 2s, 4s, ...
                time.sleep(self.delay * (2 ** attempt))
        raise YamapError(f"giving up on {url}: {last}")

    def get_json(self, path: str, **params) -> dict:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        r = self._get(url, params=params or None)
        if r.status_code != 200:
            raise YamapError(f"HTTP {r.status_code} for {url}: {r.text[:200]}")
        time.sleep(self.delay)
        return r.json()

    # -- high level --------------------------------------------------------
    def activity(self, activity_id: int) -> dict:
        """Full detail for one activity (journal text, photos, checkpoints)."""
        return self.get_json(f"/activities/{activity_id}")["activity"]

    def iter_user_activities(self, user_id: int) -> Iterator[dict]:
        """Yield every activity summary for a user, following pagination."""
        page = 1
        while True:
            data = self.get_json(f"/users/{user_id}/activities", page=page)
            acts = data.get("activities", [])
            if not acts:
                return
            for a in acts:
                yield a
            meta = data.get("meta") or {}
            nxt = meta.get("next_page")
            if not nxt or nxt < 0 or nxt == page:
                return
            page = nxt

    def user_activity_count(self, user_id: int) -> int:
        data = self.get_json(f"/users/{user_id}/activities", page=1)
        return (data.get("meta") or {}).get("total_count", 0)


# -- input parsing ---------------------------------------------------------
def parse_user_id(value: str) -> int:
    """Accept a bare id, a profile URL, or a full users URL."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = re.search(r"/users/(\d+)", value)
    if m:
        return int(m.group(1))
    raise ValueError(f"could not read a user id from {value!r}")


def parse_activity_id(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = re.search(r"/activities/(\d+)", value)
    if m:
        return int(m.group(1))
    raise ValueError(f"could not read an activity id from {value!r}")
