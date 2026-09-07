"""Check that an exported archive is complete and intact.

A backup is only worth keeping if you can trust it. Downloads fail, disks
fill up, and a run can be interrupted half way. This walks an output
directory and, for every activity, compares what is on disk against what the
saved API response says should be there: the photos, their restored EXIF, and
the GPS track.

The raw JSON in ``raw/`` is the reference, so verification is offline and
costs YAMAP nothing.

A *problem* is a real gap (a photo that should be there and is not, a
truncated file). A *note* records an absence that is expected and harmless
(YAMAP had no coordinate for that photo, or the activity never had a track),
so a clean archive stays clean in the exit code.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import piexif

from .exporters import photo_filename

# A JPEG smaller than this is a failed or truncated download, not a photo.
# (Broken exports characteristically leave ~1 KB stubs behind.)
MIN_PHOTO_BYTES = 5000

SIDECAR_FILES = ("activity.json", "details.txt", "photos.txt")


@dataclass
class ActivityReport:
    activity_id: int
    title: str = ""
    directory: Optional[str] = None
    problems: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    photos_expected: int = 0
    photos_present: int = 0
    photos_with_time: int = 0
    photos_with_gps: int = 0
    gps_expected: int = 0
    track_expected: bool = False
    track_present: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class ArchiveReport:
    outdir: str
    activities: List[ActivityReport] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and all(a.ok for a in self.activities)

    def totals(self) -> Dict[str, int]:
        return {
            "activities": len(self.activities),
            "incomplete": sum(1 for a in self.activities if not a.ok),
            "photos_expected": sum(a.photos_expected for a in self.activities),
            "photos_present": sum(a.photos_present for a in self.activities),
            "photos_with_time": sum(a.photos_with_time for a in self.activities),
            "photos_with_gps": sum(a.photos_with_gps for a in self.activities),
            "gps_expected": sum(a.gps_expected for a in self.activities),
            "tracks_expected": sum(1 for a in self.activities if a.track_expected),
            "tracks_present": sum(1 for a in self.activities if a.track_present),
        }


def _load_manifest(outdir: str) -> dict:
    path = os.path.join(outdir, "manifest.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _find_directory(outdir: str, activity_id: int, manifest: dict) -> Optional[str]:
    """Locate an activity's folder via the manifest, else by its id in the name."""
    entry = manifest.get(str(activity_id)) or {}
    rel = entry.get("dir")
    if rel and os.path.isdir(os.path.join(outdir, rel)):
        return os.path.join(outdir, rel)
    matches = glob.glob(os.path.join(outdir, "activities", f"*_{activity_id}_*"))
    matches = [m for m in matches if os.path.isdir(m)]
    return matches[0] if matches else None


def _photo_expectations(image: dict) -> bool:
    """Whether this photo should carry GPS once EXIF is restored."""
    coord = image.get("coord")
    return bool(coord) and len(coord) == 2 and not image.get("hide_location")


def verify_activity(outdir: str, raw_path: str, manifest: dict,
                    check_exif: bool = True) -> ActivityReport:
    with open(raw_path, encoding="utf-8") as fh:
        activity = json.load(fh)

    report = ActivityReport(activity_id=activity.get("id", 0),
                            title=activity.get("title", ""))

    adir = _find_directory(outdir, report.activity_id, manifest)
    if not adir:
        report.problems.append("no activity folder found")
        return report
    report.directory = os.path.relpath(adir, outdir)

    for name in SIDECAR_FILES:
        if not os.path.exists(os.path.join(adir, name)):
            report.problems.append(f"missing {name}")

    images = activity.get("images") or []
    report.photos_expected = len(images)
    report.gps_expected = sum(1 for i in images if _photo_expectations(i))

    missing, truncated, no_time, no_gps = [], [], [], []
    for i, image in enumerate(images):
        fname = photo_filename(i, len(images))
        path = os.path.join(adir, fname)
        if not os.path.exists(path):
            missing.append(fname)
            continue
        report.photos_present += 1
        if os.path.getsize(path) < MIN_PHOTO_BYTES:
            truncated.append(fname)
            continue
        if not check_exif:
            continue
        try:
            exif = piexif.load(path)
        except Exception:
            report.problems.append(f"{fname}: not a readable JPEG")
            continue
        if exif["Exif"].get(piexif.ExifIFD.DateTimeOriginal):
            report.photos_with_time += 1
        elif image.get("taken_at"):
            no_time.append(fname)
        if exif["GPS"].get(piexif.GPSIFD.GPSLatitude):
            report.photos_with_gps += 1
        elif _photo_expectations(image):
            no_gps.append(fname)

    if missing:
        report.problems.append(
            f"{len(missing)} photo(s) missing (first: {missing[0]})")
    if truncated:
        report.problems.append(
            f"{len(truncated)} photo(s) truncated (first: {truncated[0]})")
    if no_time:
        report.problems.append(
            f"{len(no_time)} photo(s) lost their capture time")
    if no_gps:
        report.problems.append(
            f"{len(no_gps)} photo(s) lost their GPS position")

    skipped_gps = report.photos_expected - report.gps_expected
    if skipped_gps:
        report.notes.append(
            f"{skipped_gps} photo(s) have no position in YAMAP's own data")

    report.track_expected = activity.get("has_points") is not False
    report.track_present = os.path.exists(os.path.join(adir, "track.gpx"))
    if report.track_expected and not report.track_present:
        state = (manifest.get(str(report.activity_id)) or {}).get("gpx")
        if state == "unavailable":
            report.notes.append("no GPS track (YAMAP has none for this activity)")
        else:
            report.notes.append("no track.gpx — re-run signed in to fetch it")
    return report


def verify_archive(outdir: str, check_exif: bool = True) -> ArchiveReport:
    report = ArchiveReport(outdir=outdir)
    raw_dir = os.path.join(outdir, "raw")
    if not os.path.isdir(raw_dir):
        report.problems.append(
            f"{outdir} does not look like an archive (no raw/ directory)")
        return report

    raw_files = sorted(glob.glob(os.path.join(raw_dir, "*.json")))
    if not raw_files:
        report.problems.append("no activities found in raw/")
        return report

    manifest = _load_manifest(outdir)
    for raw_path in raw_files:
        try:
            report.activities.append(
                verify_activity(outdir, raw_path, manifest, check_exif))
        except (OSError, json.JSONDecodeError) as e:
            report.problems.append(f"{os.path.basename(raw_path)}: {e}")
    return report


def print_report(report: ArchiveReport, show_all: bool = False) -> None:
    for a in sorted(report.activities, key=lambda x: x.directory or ""):
        if a.ok and not show_all:
            continue
        head = f"{a.directory or a.activity_id}"
        print(f"{'OK  ' if a.ok else 'GAP '} {head}")
        for p in a.problems:
            print(f"       problem: {p}")
        if show_all:
            for n in a.notes:
                print(f"       note: {n}")

    for p in report.problems:
        print(f"ERROR  {p}")

    t = report.totals()
    print()
    print(f"{t['activities']} activities checked, {t['incomplete']} with gaps")
    print(f"photos: {t['photos_present']}/{t['photos_expected']} present, "
          f"{t['photos_with_time']} with capture time, "
          f"{t['photos_with_gps']}/{t['gps_expected']} with GPS")
    print(f"tracks: {t['tracks_present']}/{t['tracks_expected']} present")
    print()
    print("Archive is complete." if report.ok
          else "Archive has gaps — re-run the export to fill them.")
