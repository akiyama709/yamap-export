"""Download photos and restore EXIF (capture time + GPS) into each JPEG.

YAMAP strips EXIF from stored photos, but its API still reports, per photo,
the capture timestamp (``taken_at``, second precision), the GPS coordinate
(``coord`` = [lon, lat]) and the altitude. We write these back into the JPEG
so that after export the photos sort chronologically and drop onto the map at
the right spot in Yamareco / Strava / etc.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

import piexif
import requests

from .api import USER_AGENT


class PhotoUnavailable(RuntimeError):
    """Raised when every published URL for a photo fails."""


# Photo URLs YAMAP publishes, largest first. ``base_url`` is the stored image
# that does not pass through the resizing proxy, so it is the sharpest when it
# is served at all; the rest come from the proxy at decreasing sizes. YAMAP has
# turned the un-proxied path off before (it answered 503 for every image from
# around October 2026), so never depend on a single one of these.
PHOTO_URL_KEYS = ("base_url", "url", "medium_url", "small_url")


def photo_url_candidates(image: dict) -> List[str]:
    """Every URL for this photo, largest first, for use as a fallback chain."""
    seen, out = set(), []
    for key in PHOTO_URL_KEYS:
        u = image.get(key)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def best_photo_url(image: dict) -> Optional[str]:
    """The largest URL YAMAP publishes for a photo, or None.

    This says nothing about whether that URL is currently being served; use
    :func:`photo_url_candidates` and try them in order.
    """
    candidates = photo_url_candidates(image)
    return candidates[0] if candidates else None


def _rational_dms(deg: float):
    """Decimal degrees -> EXIF ((d,1),(m,1),(s,100)) rational triple."""
    deg = abs(deg)
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60, 2)
    return ((d, 1), (m, 1), (int(s * 100), 100))


def _exif_datetime(taken_at: int, tz_hours: int) -> str:
    """Unix timestamp -> 'YYYY:MM:DD HH:MM:SS' in the activity's local time."""
    tz = _dt.timezone(_dt.timedelta(hours=tz_hours))
    return _dt.datetime.fromtimestamp(taken_at, tz).strftime("%Y:%m:%d %H:%M:%S")


def build_exif(image: dict, tz_hours: int) -> Optional[bytes]:
    """Assemble an EXIF block for one photo, or None if nothing to add."""
    zeroth: dict = {}
    exif: dict = {}
    gps: dict = {}

    taken_at = image.get("taken_at")
    if taken_at:
        dt = _exif_datetime(taken_at, tz_hours)
        zeroth[piexif.ImageIFD.DateTime] = dt
        exif[piexif.ExifIFD.DateTimeOriginal] = dt
        exif[piexif.ExifIFD.DateTimeDigitized] = dt

    coord = image.get("coord")
    if coord and len(coord) == 2 and not image.get("hide_location"):
        lon, lat = float(coord[0]), float(coord[1])
        gps[piexif.GPSIFD.GPSLatitudeRef] = "N" if lat >= 0 else "S"
        gps[piexif.GPSIFD.GPSLatitude] = _rational_dms(lat)
        gps[piexif.GPSIFD.GPSLongitudeRef] = "E" if lon >= 0 else "W"
        gps[piexif.GPSIFD.GPSLongitude] = _rational_dms(lon)
        alt = image.get("altitude")
        if alt is not None:
            gps[piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
            gps[piexif.GPSIFD.GPSAltitude] = (int(round(abs(alt) * 100)), 100)

    if not (zeroth or exif or gps):
        return None
    return piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps,
                        "1st": {}, "thumbnail": None})


def download_photo(image: dict, dest, session: requests.Session,
                   tz_hours: int, timeout: float = 60.0) -> None:
    """Fetch one photo to ``dest`` (a path), restoring EXIF where possible.

    Tries each published URL from the largest down and keeps the first one the
    CDN actually serves, so a size that YAMAP stops serving costs quality
    rather than the photo.
    """
    candidates = photo_url_candidates(image)
    if not candidates:
        raise ValueError("photo has no downloadable URL")

    last_error: Optional[Exception] = None
    content = None
    for url in candidates:
        try:
            r = session.get(url, timeout=timeout,
                            headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
        except requests.RequestException as e:
            last_error = e
            continue
        content = r.content
        break

    if content is None:
        raise PhotoUnavailable(
            f"none of the {len(candidates)} published URLs could be fetched "
            f"(last error: {last_error})")

    with open(dest, "wb") as fh:
        fh.write(content)

    exif_bytes = build_exif(image, tz_hours)
    if exif_bytes:
        try:
            # piexif.insert with a path writes the EXIF back into the file.
            piexif.insert(exif_bytes, str(dest))
        except Exception:
            # Some JPEGs can be awkward; keep the pixels rather than lose the
            # photo over EXIF.
            pass
