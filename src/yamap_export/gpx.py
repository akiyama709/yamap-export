"""Download the GPS track (points.xml) for an activity.

This is the only part of the export that needs you to be signed in. See
:mod:`yamap_export.auth` for how the token is obtained; it is used only here
and only against api.yamap.com.
"""

from __future__ import annotations

from typing import Optional

import requests

from .api import API_BASE, USER_AGENT
from .auth import auth_header


class GpxUnavailable(RuntimeError):
    """Raised when a track cannot be downloaded (no login, or no track)."""


def download_gpx(activity_id: int, token: str, dest,
                 timeout: float = 60.0) -> int:
    """Save the activity's GPX track to ``dest``. Returns bytes written.

    Raises :class:`GpxUnavailable` on 401 (not signed in / not your track) or
    404 (activity has no recorded track).
    """
    url = f"{API_BASE}/activities/{activity_id}/points.xml"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/gpx+xml"}
    headers.update(auth_header(token))
    r = requests.get(url, headers=headers, timeout=timeout)

    if r.status_code == 401:
        raise GpxUnavailable(
            f"activity {activity_id}: not authorised. Sign in to yamap.com "
            "(downloading someone else's track needs YAMAP Premium)."
        )
    if r.status_code == 404:
        raise GpxUnavailable(f"activity {activity_id}: no GPS track recorded.")
    r.raise_for_status()

    with open(dest, "wb") as fh:
        fh.write(r.content)
    return len(r.content)


def has_track(activity: dict) -> Optional[bool]:
    """Whether the detail JSON says a track exists (None if unknown)."""
    if "has_points" in activity:
        return bool(activity["has_points"])
    return None
