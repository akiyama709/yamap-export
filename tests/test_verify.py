"""Tests for archive verification.

These build a small synthetic archive on disk — real (if tiny) JPEGs with
restored EXIF — so the checks are exercised the same way they run against a
genuine export.
"""

import base64
import json
import os

import piexif
import pytest

from yamap_export.verify import MIN_PHOTO_BYTES, verify_archive

# A valid 1x1 JPEG, padded with a comment segment so it clears the
# truncated-download threshold.
_MIN_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)
ACTIVITY_ID = 12345


def _padded_jpeg(nbytes: int = MIN_PHOTO_BYTES + 1000) -> bytes:
    pad = b"\xff\xfe" + nbytes.to_bytes(2, "big") + b"\x00" * (nbytes - 2)
    return _MIN_JPEG[:2] + pad + _MIN_JPEG[2:]


def write_photo(path, *, with_time=True, with_gps=True):
    with open(path, "wb") as fh:
        fh.write(_padded_jpeg())
    exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    if with_time:
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = "2026:07:30 10:00:00"
    if with_gps:
        exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] = "N"
        exif["GPS"][piexif.GPSIFD.GPSLatitude] = ((26, 1), (12, 1), (0, 100))
    if with_time or with_gps:
        # piexif needs a path when it is to write the bytes back itself.
        piexif.insert(piexif.dump(exif), str(path))


def build_archive(tmp_path, n_photos=3, coords=True, has_points=False):
    images = []
    for _ in range(n_photos):
        images.append({
            "base_url": "https://example/x.jpg",
            "caption": None,
            "taken_at": 1785000000,
            "coord": [127.0, 26.2] if coords else None,
            "altitude": 100.0,
            "hide_location": False,
        })
    activity = {
        "id": ACTIVITY_ID,
        "title": "test activity",
        "start_at": 1785000000,
        "finish_at": 1785010000,
        "time_zone": 9,
        "distance": 1000,
        "cumulative_up": 100,
        "cumulative_down": 100,
        "calorie": None,
        "has_points": has_points,
        "user": {"name": "tester"},
        "map": {"name": "test map", "prefectures": []},
        "tags": [],
        "images": images,
    }
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / f"{ACTIVITY_ID}.json").write_text(
        json.dumps(activity, ensure_ascii=False), encoding="utf-8")

    adir = tmp_path / "activities" / f"2026-07-30_{ACTIVITY_ID}_test"
    adir.mkdir(parents=True)
    for name in ("activity.json", "details.txt", "photos.txt"):
        (adir / name).write_text("x", encoding="utf-8")
    for i in range(n_photos):
        write_photo(adir / f"image{i + 1:02d}.jpg")

    (tmp_path / "manifest.json").write_text(json.dumps({
        str(ACTIVITY_ID): {"dir": os.path.join("activities",
                                               adir.name)}
    }), encoding="utf-8")
    return adir


def test_healthy_archive_has_no_gaps(tmp_path):
    build_archive(tmp_path)
    report = verify_archive(str(tmp_path))
    assert report.ok
    t = report.totals()
    assert t["photos_present"] == t["photos_expected"] == 3
    assert t["photos_with_time"] == 3
    assert t["photos_with_gps"] == 3


def test_missing_photo_is_a_problem(tmp_path):
    adir = build_archive(tmp_path)
    os.remove(adir / "image02.jpg")
    report = verify_archive(str(tmp_path))
    assert not report.ok
    assert any("missing" in p for p in report.activities[0].problems)


def test_truncated_photo_is_a_problem(tmp_path):
    adir = build_archive(tmp_path)
    (adir / "image01.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)
    report = verify_archive(str(tmp_path))
    assert not report.ok
    assert any("truncated" in p for p in report.activities[0].problems)


def test_missing_sidecar_is_a_problem(tmp_path):
    adir = build_archive(tmp_path)
    os.remove(adir / "details.txt")
    report = verify_archive(str(tmp_path))
    assert not report.ok
    assert any("details.txt" in p for p in report.activities[0].problems)


def test_stripped_exif_is_a_problem(tmp_path):
    adir = build_archive(tmp_path)
    piexif.remove(str(adir / "image03.jpg"))
    report = verify_archive(str(tmp_path))
    assert not report.ok
    problems = " ".join(report.activities[0].problems)
    assert "capture time" in problems and "GPS" in problems


def test_photo_without_source_coordinate_is_only_a_note(tmp_path):
    # YAMAP itself has no position for these, so their absence is not a gap.
    adir = build_archive(tmp_path, coords=False)
    for i in range(3):
        write_photo(adir / f"image{i + 1:02d}.jpg", with_gps=False)
    report = verify_archive(str(tmp_path))
    assert report.ok
    assert any("no position in YAMAP" in n for n in report.activities[0].notes)


def test_missing_activity_folder_is_a_problem(tmp_path):
    adir = build_archive(tmp_path)
    for f in adir.iterdir():
        f.unlink()
    adir.rmdir()
    report = verify_archive(str(tmp_path))
    assert not report.ok
    assert "no activity folder found" in report.activities[0].problems


def test_directory_that_is_not_an_archive(tmp_path):
    report = verify_archive(str(tmp_path))
    assert not report.ok
    assert any("does not look like an archive" in p for p in report.problems)
