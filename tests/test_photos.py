"""Tests for the photo URL fallback chain.

YAMAP turned off the un-proxied ``base_url`` path in October 2026 (every
image answered 503), which broke photo download outright because the
exporter asked for that one URL and gave up. These tests pin the behaviour
that replaced it: walk the published URLs from largest down and keep the
first the CDN actually serves.
"""

import pytest
import requests

from yamap_export.photos import (PHOTO_URL_KEYS, PhotoUnavailable,
                                 best_photo_url, download_photo,
                                 photo_url_candidates)

IMAGE = {
    "base_url": "https://cdn/base.jpg",
    "url": "https://cdn/proxy-large.jpg",
    "medium_url": "https://cdn/proxy-medium.jpg",
    "small_url": "https://cdn/proxy-small.jpg",
    # no taken_at / coord, so no EXIF is written and the bytes stay as-is
}


class _Response:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _Session:
    """Serves the URLs in ``ok`` and fails everything else."""

    def __init__(self, ok):
        self.ok = ok
        self.tried = []

    def get(self, url, **kw):
        self.tried.append(url)
        if url in self.ok:
            return _Response(200, b"\xff\xd8pixels")
        return _Response(503)


def test_candidates_are_largest_first():
    assert photo_url_candidates(IMAGE) == [IMAGE[k] for k in PHOTO_URL_KEYS]


def test_candidates_drop_missing_and_duplicate_urls():
    image = {"base_url": "A", "url": "A", "medium_url": "", "small_url": "B"}
    assert photo_url_candidates(image) == ["A", "B"]
    assert photo_url_candidates({}) == []
    assert best_photo_url({}) is None


def test_falls_back_when_the_largest_url_is_not_served(tmp_path):
    # base_url 503s, as it did when YAMAP turned the un-proxied path off.
    session = _Session(ok={IMAGE["url"]})
    dest = tmp_path / "image01.jpg"
    download_photo(IMAGE, dest, session, tz_hours=9)
    assert dest.read_bytes() == b"\xff\xd8pixels"
    # It tried the largest first, then stopped at the one that worked.
    assert session.tried == [IMAGE["base_url"], IMAGE["url"]]


def test_falls_back_through_several_sizes(tmp_path):
    session = _Session(ok={IMAGE["small_url"]})
    dest = tmp_path / "image01.jpg"
    download_photo(IMAGE, dest, session, tz_hours=9)
    assert dest.exists()
    assert len(session.tried) == 4


def test_raises_when_no_url_is_served(tmp_path):
    session = _Session(ok=set())
    dest = tmp_path / "image01.jpg"
    with pytest.raises(PhotoUnavailable):
        download_photo(IMAGE, dest, session, tz_hours=9)
    assert not dest.exists()


def test_raises_value_error_when_there_is_nothing_to_download(tmp_path):
    with pytest.raises(ValueError):
        download_photo({}, tmp_path / "x.jpg", _Session(ok=set()), tz_hours=9)
