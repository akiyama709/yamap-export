"""Command-line interface for yamap-export.

Typical use:

    # everything for one user (journals, photos, and — if signed in — tracks)
    yamap-export https://yamap.com/users/2486399 -o ./my-yamap-archive

    # only specific activities, no tracks
    yamap-export --activity 49680490 --activity 49512345 --no-gpx -o ./out
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Dict, List, Optional

import requests
from tqdm import tqdm

from . import __version__
from .api import (USER_AGENT, YamapClient, YamapError, parse_activity_id,
                  parse_user_id)
from .exporters import (details_txt, flat_record, iso_date, markdown,
                        photo_filename, photos_txt, slugify, to_json)
from .gpx import GpxUnavailable, download_gpx, has_track
from .photos import download_photo


# -- manifest (resume state) ----------------------------------------------
class Manifest:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, dict] = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def get(self, aid: int) -> dict:
        return self.data.setdefault(str(aid), {})

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


def activity_dirname(activity: dict, rec: dict) -> str:
    date = iso_date(activity.get("start_at"), activity.get("time_zone", 9))
    return f"{date}_{activity.get('id')}_{slugify(rec['title'])}"


# -- per-activity export ---------------------------------------------------
def export_activity(client: YamapClient, activity_id: int, outdir: str,
                    manifest: Manifest, *, want_photos: bool, want_gpx: bool,
                    want_markdown: bool, embed_photos: bool,
                    token: Optional[str], photo_delay: float,
                    force: bool) -> dict:
    state = manifest.get(activity_id)

    # 1. detail JSON (also the lossless raw archive)
    raw_dir = os.path.join(outdir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(raw_dir, f"{activity_id}.json")
    if force or not state.get("json") or not os.path.exists(raw_path):
        activity = client.activity(activity_id)
        with open(raw_path, "w", encoding="utf-8") as fh:
            json.dump(activity, fh, ensure_ascii=False, indent=2)
        state["json"] = True
    else:
        with open(raw_path, encoding="utf-8") as fh:
            activity = json.load(fh)

    rec = flat_record(activity)
    adir = os.path.join(outdir, "activities", activity_dirname(activity, rec))
    os.makedirs(adir, exist_ok=True)

    # 2. flat json + text mirrors (for Yamareco import extension)
    with open(os.path.join(adir, "activity.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(rec))
    with open(os.path.join(adir, "details.txt"), "w", encoding="utf-8") as fh:
        fh.write(details_txt(rec))
    with open(os.path.join(adir, "photos.txt"), "w", encoding="utf-8") as fh:
        fh.write(photos_txt(rec))

    # 3. markdown
    if want_markdown:
        with open(os.path.join(adir, "index.md"), "w", encoding="utf-8") as fh:
            fh.write(markdown(activity, rec, embed_photos=embed_photos))

    # 4. photos
    images = activity.get("images") or []
    if want_photos and images:
        tz = activity.get("time_zone", 9)
        done = set(state.get("photos_done", []))
        sess = requests.Session()
        total = len(images)
        for i, img in enumerate(images):
            fname = photo_filename(i, total)
            dest = os.path.join(adir, fname)
            if not force and i in done and os.path.exists(dest):
                continue
            # Retry transient network hiccups (e.g. macOS ephemeral-port
            # exhaustion, EADDRNOTAVAIL) rather than leaving a gap.
            for attempt in range(3):
                try:
                    download_photo(img, dest, sess, tz)
                    done.add(i)
                    break
                except ValueError as e:  # nothing to download
                    tqdm.write(f"  photo {fname} of {activity_id}: {e}")
                    break
                except (requests.RequestException, OSError) as e:
                    if attempt == 2:
                        tqdm.write(f"  photo {fname} of {activity_id} failed "
                                   f"after retries: {e}")
                    else:
                        time.sleep(1.0 * (attempt + 1))
            if photo_delay:
                time.sleep(photo_delay)
        state["photos_done"] = sorted(done)
        if len(done) == total:
            state["photos"] = True

    # 5. gpx track
    if want_gpx and token and not state.get("gpx"):
        if has_track(activity) is not False:
            try:
                download_gpx(activity_id, token,
                             os.path.join(adir, "track.gpx"))
                state["gpx"] = True
            except GpxUnavailable as e:
                state["gpx"] = "unavailable"
                tqdm.write(f"  track {activity_id}: {e}")
            except requests.RequestException as e:
                tqdm.write(f"  track {activity_id} failed: {e}")

    state["title"] = rec["title"]
    state["date"] = iso_date(activity.get("start_at"),
                             activity.get("time_zone", 9))
    state["dir"] = os.path.relpath(adir, outdir)
    return rec


def write_index_csv(outdir: str, manifest: Manifest) -> None:
    rows = sorted(manifest.data.items(),
                  key=lambda kv: kv[1].get("date", ""), reverse=True)
    path = os.path.join(outdir, "index.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "activity_id", "title", "folder",
                    "json", "photos", "gpx"])
        for aid, st in rows:
            w.writerow([st.get("date", ""), aid, st.get("title", ""),
                        st.get("dir", ""), st.get("json", False),
                        st.get("photos", False), st.get("gpx", False)])


# -- argument parsing ------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yamap-export",
        description="Bulk-export your YAMAP activities (journals, photos, GPS "
                    "tracks) for archival and migration to Yamareco, Strava, "
                    "Garmin, or back into YAMAP.",
    )
    p.add_argument("user", nargs="?",
                   help="your YAMAP user id or profile URL "
                        "(e.g. https://yamap.com/users/2486399)")
    p.add_argument("--activity", action="append", default=[], metavar="ID/URL",
                   help="export only this activity (repeatable); "
                        "skips user enumeration")
    p.add_argument("-o", "--outdir", default="yamap-archive",
                   help="output directory (default: ./yamap-archive)")

    p.add_argument("--no-photos", action="store_true",
                   help="skip photo download")
    p.add_argument("--no-gpx", action="store_true",
                   help="skip GPS track download (tracks need you to be "
                        "signed in to yamap.com)")
    p.add_argument("--no-markdown", action="store_true",
                   help="skip per-activity index.md")
    p.add_argument("--no-embed", action="store_true",
                   help="use standard markdown image links instead of "
                        "Obsidian ![[...]] embeds")

    p.add_argument("--token", metavar="YAMAP_TOKEN",
                   help="login token for track download "
                        "(else read from $YAMAP_TOKEN or your browser)")
    p.add_argument("--browser", default="auto",
                   choices=["auto", "chrome", "firefox", "edge", "brave",
                            "chromium", "safari"],
                   help="which browser to read the login cookie from")

    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds between API calls (default: 1.0)")
    p.add_argument("--photo-delay", type=float, default=0.3,
                   help="seconds between photo downloads (default: 0.3)")
    p.add_argument("--language", default="ja",
                   help="Accept-Language for place names/tags (default: ja)")
    p.add_argument("--limit", type=int, default=0,
                   help="export at most N activities (0 = all)")
    p.add_argument("--force", action="store_true",
                   help="re-download even if already present")
    p.add_argument("--version", action="version",
                   version=f"yamap-export {__version__}")
    return p


def resolve_token_quietly(args) -> Optional[str]:
    if args.no_gpx:
        return None
    from .auth import TokenError, resolve_token
    try:
        return resolve_token(args.token, args.browser)
    except TokenError as e:
        print(f"[tracks] {e}\n[tracks] Continuing without GPS tracks. "
              f"Re-run later to add them.\n", file=sys.stderr)
        return None


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # figure out the work list
    activity_ids: List[int] = []
    client = YamapClient(delay=args.delay, language=args.language)

    if args.activity:
        activity_ids = [parse_activity_id(a) for a in args.activity]
    elif args.user:
        try:
            uid = parse_user_id(args.user)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"Enumerating activities for user {uid} ...", file=sys.stderr)
        try:
            summaries = list(client.iter_user_activities(uid))
        except YamapError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        activity_ids = [a["id"] for a in summaries]
        print(f"Found {len(activity_ids)} activities.", file=sys.stderr)
    else:
        build_parser().print_help(sys.stderr)
        return 2

    if args.limit:
        activity_ids = activity_ids[:args.limit]
    if not activity_ids:
        print("Nothing to export.", file=sys.stderr)
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    manifest = Manifest(os.path.join(args.outdir, "manifest.json"))
    token = resolve_token_quietly(args)

    errors = 0
    for aid in tqdm(activity_ids, desc="activities", unit="act"):
        try:
            export_activity(
                client, aid, args.outdir, manifest,
                want_photos=not args.no_photos,
                want_gpx=not args.no_gpx,
                want_markdown=not args.no_markdown,
                embed_photos=not args.no_embed,
                token=token, photo_delay=args.photo_delay, force=args.force,
            )
        except (YamapError, requests.RequestException, OSError) as e:
            errors += 1
            tqdm.write(f"activity {aid} failed: {e}")
        finally:
            manifest.save()

    write_index_csv(args.outdir, manifest)

    # summary tallies, so it is obvious what actually came through
    n_json = sum(1 for s in manifest.data.values() if s.get("json"))
    n_photos = sum(len(s.get("photos_done", [])) for s in manifest.data.values())
    n_tracks = sum(1 for s in manifest.data.values() if s.get("gpx") is True)
    n_notrack = sum(1 for s in manifest.data.values()
                    if s.get("gpx") == "unavailable")

    print(f"\nDone. Output in {os.path.abspath(args.outdir)}", file=sys.stderr)
    print(f"  activities: {n_json}    photos: {n_photos}    "
          f"tracks: {n_tracks}", file=sys.stderr)
    if not args.no_gpx:
        if not token:
            print("  tracks were skipped (not signed in). See the README to "
                  "include GPS tracks.", file=sys.stderr)
        elif n_tracks == 0:
            print("  no tracks downloaded — check that you are signed in to "
                  "yamap.com in your browser.", file=sys.stderr)
        elif n_notrack:
            print(f"  ({n_notrack} activities had no recorded track.)",
                  file=sys.stderr)
    if errors:
        print(f"  {errors} activities had errors (re-run to retry).",
              file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
