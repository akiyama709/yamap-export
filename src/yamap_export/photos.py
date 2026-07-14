"""Download photos and restore EXIF (capture time + GPS) into each JPEG.

YAMAP strips EXIF from stored photos, but its API still reports, per photo,
the capture timestamp (``taken_at``, second precision), the GPS coordinate
(``coord`` = [lon, lat]) and the altitude. We write these back into the JPEG
so that after export the photos sort chronologically and drop onto the map at
the right spot in Yamareco / Strava / etc.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

import piexif
import requests

from .api import USER_AGENT


def best_photo_url(image: dict) -> Optional[str]:
    """Highest-quality URL YAMAP exposes for a photo.

    ``base_url`` is the stored image that does not pass through the resizing
    proxy; it is larger and sharper than ``url``. Fall back to the proxied
    versions if it is absent.
    """
    for key in ("base_url", "url", "medium_url", "small_url"):
        u = image.get(key)
        if u:
            return u
    return None


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
    """Fetch one photo to ``dest`` (a path), restoring EXIF where possible."""
    url = best_photo_url(image)
    if not url:
        raise ValueError("photo has no downloadable URL")
    r = session.get(url, timeout=timeout,
                    headers={"User-Agent": USER_AGENT})
    r.raise_for_status()

    with open(dest, "wb") as fh:
        fh.write(r.content)

    exif_bytes = build_exif(image, tz_hours)
    if exif_bytes:
        try:
            # piexif.insert with a path writes the EXIF back into the file.
            piexif.insert(exif_bytes, str(dest))
        except Exception:
            # Some JPEGs can be awkward; keep the pixels rather than lose the
            # photo over EXIF.
            pass
