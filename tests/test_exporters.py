"""Unit tests for the pure transform functions.

These need no network — they run against a small fixture that mirrors YAMAP's
API shape.
"""

import piexif

from yamap_export.api import parse_activity_id, parse_user_id
from yamap_export.exporters import (duration_label, flat_record, japanese_date,
                                    photo_filename, slugify)
from yamap_export.photos import _rational_dms, build_exif

# One same-day activity in JST (time_zone = 9) with two photos, one of which
# has a GPS fix and one of which does not.
FIXTURE = {
    "id": 49680490,
    "title": "260713：京都五山送り火「船形」の船山",
    "description": "近場の山に参りました。",
    "start_at": 1783903374,   # 2026-07-13 (JST)
    "finish_at": 1783914976,  # same day
    "time_zone": 9,
    "distance": 7622.03,
    "cumulative_up": 465,
    "cumulative_down": 504,
    "calorie": None,
    "user": {"name": "Laboratory of Integral Studies"},
    "map": {"name": "十三石山・釈迦谷山・沢山",
            "prefectures": [{"name": "京都"}]},
    "tags": [{"name": "登山・山登り"}],
    "images": [
        {"base_url": "https://example/a.jpg", "caption": "山頂",
         "taken_at": 1783903262, "coord": [135.7289, 35.0599],
         "altitude": 212.0, "hide_location": False},
        {"base_url": "https://example/b.jpg", "caption": None,
         "taken_at": 1783903300, "coord": None, "altitude": None},
    ],
}


def test_parse_ids():
    assert parse_user_id("2486399") == 2486399
    assert parse_user_id("https://yamap.com/users/2486399") == 2486399
    assert parse_activity_id("https://yamap.com/activities/49680490/article") \
        == 49680490


def test_dates():
    assert japanese_date(1783903374, 9) == "2026年07月13日(月)"
    assert duration_label(1783903374, 1783914976, 9) == "日帰り"
    # crossing to the next day -> 1泊2日
    assert duration_label(1783903374, 1783903374 + 86400, 9) == "1泊2日"


def test_flat_record_schema():
    rec = flat_record(FIXTURE)
    assert rec["title"].startswith("260713")
    assert rec["mapName"] == "十三石山・釈迦谷山・沢山"
    assert rec["prefName"] == "京都"
    assert rec["tags"] == "登山・山登り"
    assert rec["distance"] == "7.6km"
    assert rec["ascent"] == "465m"
    assert rec["days"] == "日帰り"
    assert len(rec["photos"]) == 2
    assert rec["photos"][0]["memo"] == "山頂"
    # every key the import extension may read is present
    for key in ("date", "days", "userName", "prefName", "mapName", "title",
                "url", "distance", "ascent", "descent", "calorie",
                "description", "tags", "photos"):
        assert key in rec


def test_slugify_and_filenames():
    assert "/" not in slugify("a/b:c")
    assert photo_filename(0, 77) == "image01.jpg"
    assert photo_filename(9, 77) == "image10.jpg"
    assert photo_filename(0, 5) == "image01.jpg"


def test_rational_dms_roundtrip():
    d, m, s = _rational_dms(35.0599)
    approx = d[0] / d[1] + (m[0] / m[1]) / 60 + (s[0] / s[1]) / 3600
    assert abs(approx - 35.0599) < 1e-4


def test_build_exif_has_datetime_and_gps():
    exif = build_exif(FIXTURE["images"][0], tz_hours=9)
    loaded = piexif.load(exif)
    assert loaded["Exif"][piexif.ExifIFD.DateTimeOriginal] == \
        b"2026:07:13 09:41:02"
    assert piexif.GPSIFD.GPSLatitude in loaded["GPS"]
    assert loaded["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"N"


def test_build_exif_without_gps_still_has_time():
    exif = build_exif(FIXTURE["images"][1], tz_hours=9)
    loaded = piexif.load(exif)
    assert piexif.ExifIFD.DateTimeOriginal in loaded["Exif"]
    assert piexif.GPSIFD.GPSLatitude not in loaded["GPS"]


def test_hidden_location_is_dropped():
    img = dict(FIXTURE["images"][0], hide_location=True)
    exif = build_exif(img, tz_hours=9)
    loaded = piexif.load(exif)
    assert piexif.GPSIFD.GPSLatitude not in loaded["GPS"]
