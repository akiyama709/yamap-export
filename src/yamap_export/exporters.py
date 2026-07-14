"""Turn one activity's API data into the files we write to disk.

Outputs, per activity:
  * ``activity.json`` — flat schema compatible with the "Yamareco Activity
    Import Tool" browser extension, so a bulk export here can be imported into
    Yamareco one record at a time.
  * ``details.txt`` / ``photos.txt`` — plain-text mirror of the same data.
  * ``index.md`` — a human-readable / Obsidian-friendly journal with embedded
    photos.
The raw API response is also saved verbatim elsewhere for a lossless archive.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import List, Optional

_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]  # Monday = 0


# -- formatting helpers ----------------------------------------------------
def _local(ts: Optional[int], tz_hours: float) -> Optional[_dt.datetime]:
    if not ts:
        return None
    tz = _dt.timezone(_dt.timedelta(hours=tz_hours))
    return _dt.datetime.fromtimestamp(ts, tz)


def japanese_date(ts: int, tz_hours: float) -> str:
    d = _local(ts, tz_hours)
    if not d:
        return ""
    return f"{d.year}年{d.month:02d}月{d.day:02d}日({_WEEKDAY_JA[d.weekday()]})"


def iso_date(ts: int, tz_hours: float) -> str:
    d = _local(ts, tz_hours)
    return d.strftime("%Y-%m-%d") if d else ""


def duration_label(start: int, finish: int, tz_hours: float) -> str:
    """'日帰り' for a same-day trip, else 'N泊M日'."""
    ds, df = _local(start, tz_hours), _local(finish, tz_hours)
    if not ds or not df:
        return ""
    nights = (df.date() - ds.date()).days
    return "日帰り" if nights <= 0 else f"{nights}泊{nights + 1}日"


def _km(meters) -> str:
    try:
        return f"{float(meters) / 1000:.1f}km"
    except (TypeError, ValueError):
        return ""


def _m(meters) -> str:
    try:
        return f"{int(round(float(meters)))}m"
    except (TypeError, ValueError):
        return ""


def _calorie(activity: dict) -> str:
    c = activity.get("calorie")
    if isinstance(c, dict):
        c = c.get("calorie") or c.get("value")
    try:
        return f"{int(round(float(c)))}kcal"
    except (TypeError, ValueError):
        return ""


def slugify(text: str, maxlen: int = 40) -> str:
    text = (text or "").strip()
    text = re.sub(r"[\s/\\:*?\"<>|]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:maxlen] or "activity"


def photo_number(i: int, total: int) -> str:
    width = max(2, len(str(total)))
    return str(i + 1).zfill(width)


# -- record building -------------------------------------------------------
def flat_record(activity: dict) -> dict:
    """The import-extension-compatible flat schema."""
    tz = activity.get("time_zone", 9)
    start = activity.get("start_at")
    finish = activity.get("finish_at")

    prefs = " ".join(
        p.get("name", "") for p in activity.get("map", {}).get("prefectures", [])
    ).strip()
    tags = " ".join(t.get("name", "") for t in (activity.get("tags") or []))

    photos = []
    total = len(activity.get("images") or [])
    for img in activity.get("images") or []:
        photos.append({
            "url": img.get("base_url") or img.get("url"),
            "memo": img.get("caption") or "",
            "takenAt": _photo_taken_label(img.get("taken_at"), tz),
        })

    return {
        "date": japanese_date(start, tz),
        "days": duration_label(start, finish, tz),
        "userName": activity.get("user", {}).get("name", ""),
        "prefName": prefs,
        "mapName": activity.get("map", {}).get("name", ""),
        "title": activity.get("title", ""),
        "url": f"https://yamap.com/activities/{activity.get('id')}",
        "distance": _km(activity.get("distance")),
        "ascent": _m(activity.get("cumulative_up")),
        "descent": _m(activity.get("cumulative_down")),
        "calorie": _calorie(activity),
        "description": activity.get("description") or "",
        "tags": tags,
        "photos": photos,
    }


def _photo_taken_label(taken_at, tz_hours) -> str:
    d = _local(taken_at, tz_hours)
    if not d:
        return ""
    return f"{d.year}.{d.month:02d}.{d.day:02d}({_WEEKDAY_JA[d.weekday()]}) " \
           f"{d.hour:02d}:{d.minute:02d}"


def details_txt(rec: dict) -> str:
    fields = [
        ("Title", rec["title"]), ("URL", rec["url"]), ("Date", rec["date"]),
        ("Days", rec["days"]), ("User Name", rec["userName"]),
        ("Prefecture", rec["prefName"]), ("Map Name", rec["mapName"]),
        ("Tags", rec["tags"]), ("Distance", rec["distance"]),
        ("Ascent", rec["ascent"]), ("Descent", rec["descent"]),
        ("Calories", rec["calorie"]), ("Description", rec["description"]),
    ]
    return "\n".join(f"{k}: {v}" for k, v in fields)


def photos_txt(rec: dict) -> str:
    total = len(rec["photos"])
    out = []
    for i, p in enumerate(rec["photos"]):
        out.append(f"{photo_filename(i, total)}\n{p['memo']}\n")
    return "\n".join(out)


def photo_filename(i: int, total: int) -> str:
    return f"image{photo_number(i, total)}.jpg"


# -- markdown --------------------------------------------------------------
def markdown(activity: dict, rec: dict, embed_photos: bool = True) -> str:
    tz = activity.get("time_zone", 9)
    lines: List[str] = []
    lines.append("---")
    lines.append(f'title: "{rec["title"].replace(chr(34), chr(39))}"')
    lines.append(f"yamap_id: {activity.get('id')}")
    lines.append(f"date: {iso_date(activity.get('start_at'), tz)}")
    lines.append(f"url: {rec['url']}")
    if rec["mapName"]:
        lines.append(f'map: "{rec["mapName"]}"')
    if rec["prefName"]:
        lines.append(f"prefecture: {rec['prefName']}")
    if rec["tags"]:
        lines.append(f"tags: [{', '.join(t for t in rec['tags'].split())}]")
    for k in ("distance", "ascent", "descent", "calorie", "days"):
        if rec[k]:
            lines.append(f"{k}: {rec[k]}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {rec['title']}")
    lines.append("")
    meta = " ／ ".join(x for x in [rec["date"], rec["days"], rec["mapName"],
                                    rec["prefName"]] if x)
    if meta:
        lines.append(f"*{meta}*")
        lines.append("")
    stats = " ／ ".join(
        f"{label} {rec[k]}" for label, k in
        [("距離", "distance"), ("のぼり", "ascent"), ("くだり", "descent"),
         ("カロリー", "calorie")] if rec[k]
    )
    if stats:
        lines.append(stats)
        lines.append("")
    if rec["description"]:
        lines.append(rec["description"])
        lines.append("")

    total = len(rec["photos"])
    if total:
        lines.append("## 写真")
        lines.append("")
        for i, p in enumerate(rec["photos"]):
            fname = photo_filename(i, total)
            if embed_photos:
                lines.append(f"![[{fname}]]")
            else:
                lines.append(f"![{fname}]({fname})")
            caption = " / ".join(x for x in [p["takenAt"], p["memo"]] if x)
            if caption:
                lines.append(f"*{caption}*")
            lines.append("")
    return "\n".join(lines)


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
