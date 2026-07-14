#!/usr/bin/env python3
"""Health check: does yamap-export still work against the live YAMAP API?

YAMAP is an unofficial, undocumented target: they can change their JSON shape,
their image CDN, or the User-Agent gate at any time and quietly break this
tool. This script exercises the real endpoints and asserts the things the
exporter depends on, so a breakage is caught early instead of the next time
someone runs a full export.

Exit code 0 = healthy, 1 = something the exporter needs has changed.

Run it directly (``python scripts/healthcheck.py``) or on a schedule (see the
``healthcheck`` GitHub Actions workflow, or a local cron/launchd job). Set the
``YAMAP_TOKEN`` environment variable to also check authenticated GPS-track
download; without it, that one check is skipped.
"""

from __future__ import annotations

import os
import sys

import requests

from yamap_export.api import USER_AGENT, YamapClient, YamapError
from yamap_export.exporters import flat_record
from yamap_export.gpx import download_gpx, GpxUnavailable
from yamap_export.photos import best_photo_url

# A stable, public activity to probe. Override with env vars if it ever goes
# away.
USER_ID = int(os.environ.get("YAMAP_HEALTHCHECK_USER", "2486399"))
ACTIVITY_ID = int(os.environ.get("YAMAP_HEALTHCHECK_ACTIVITY", "49680490"))

# Fields the exporter reads and would break without.
REQUIRED_ACTIVITY_FIELDS = ("id", "title", "start_at", "time_zone", "images",
                            "map", "gpx_download_url")
REQUIRED_FLAT_KEYS = ("date", "title", "url", "mapName", "tags", "photos")


class CheckFailed(Exception):
    pass


def check(name: str, fn) -> bool:
    try:
        detail = fn()
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as e:  # noqa: BLE001 — a health check reports every failure
        print(f"  FAIL  {name} — {type(e).__name__}: {e}")
        return False


def main() -> int:
    print(f"yamap-export health check (UA: {USER_AGENT!r})")
    client = YamapClient(delay=0.5)
    results = []
    state = {}

    # 1. User activity listing + pagination metadata.
    def user_list():
        data = client.get_json(f"/users/{USER_ID}/activities", page=1)
        if "activities" not in data or "meta" not in data:
            raise CheckFailed("missing activities/meta")
        total = data["meta"].get("total_count")
        if not data["activities"]:
            raise CheckFailed("no activities returned")
        return f"{total} activities listed"

    results.append(check("user activity listing", user_list))

    # 2. Activity detail has every field the exporter reads.
    def activity_detail():
        act = client.activity(ACTIVITY_ID)
        missing = [f for f in REQUIRED_ACTIVITY_FIELDS if f not in act]
        if missing:
            raise CheckFailed(f"missing fields: {missing}")
        state["activity"] = act
        return f"{len(act.get('images') or [])} photos, title present"

    results.append(check("activity detail shape", activity_detail))

    # 3. The exporter transform still produces the expected keys.
    def transform():
        act = state.get("activity")
        if not act:
            raise CheckFailed("no activity to transform (earlier check failed)")
        rec = flat_record(act)
        missing = [k for k in REQUIRED_FLAT_KEYS if k not in rec]
        if missing:
            raise CheckFailed(f"flat_record missing: {missing}")
        return "flat record OK"

    results.append(check("exporter transform", transform))

    # 4. A photo URL still resolves on the CDN.
    def photo_cdn():
        act = state.get("activity")
        if not act or not act.get("images"):
            raise CheckFailed("no photos to check")
        url = best_photo_url(act["images"][0])
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                         timeout=30, stream=True)
        r.close()
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("image/"):
            raise CheckFailed(f"HTTP {r.status_code}, content-type {ctype!r}")
        return f"HTTP 200, {ctype}"

    results.append(check("photo CDN", photo_cdn))

    # 5. GPS track auth — only if a token is provided.
    token = os.environ.get("YAMAP_TOKEN")
    if token:
        def gpx_auth():
            import tempfile
            dest = os.path.join(tempfile.gettempdir(), "healthcheck.gpx")
            try:
                n = download_gpx(ACTIVITY_ID, token, dest)
            except GpxUnavailable as e:
                raise CheckFailed(str(e))
            finally:
                if os.path.exists(dest):
                    os.remove(dest)
            return f"{n} bytes"

        results.append(check("GPS track download (authenticated)", gpx_auth))
    else:
        print("  SKIP  GPS track download — set YAMAP_TOKEN to include it")

    ok = all(results)
    print()
    if ok:
        print("HEALTHY — yamap-export works against the live YAMAP API.")
        return 0
    print("BROKEN — yamap-export needs an update; see failures above.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (YamapError, requests.RequestException) as e:
        print(f"\nBROKEN — could not reach YAMAP: {e}")
        sys.exit(1)
