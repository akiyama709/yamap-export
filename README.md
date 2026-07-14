# yamap-export

**Bulk-export all of your [YAMAP](https://yamap.com) activities** — journals,
photos (at the best resolution YAMAP exposes, with EXIF capture-time and GPS
restored), and GPS tracks — for **archival** and **migration** to Yamareco,
Strava, Garmin, or back into YAMAP.

The official site and existing browser extensions only let you export **one
activity at a time**. This is a command-line tool that walks your whole
account, is **resumable**, and is polite to YAMAP's servers.

> 日本語の説明は [下のほう](#日本語) にあります。

---

## What you get

For every activity, in your output folder:

```
yamap-archive/
├── raw/<id>.json                     # verbatim API response (lossless archive)
├── activities/
│   └── 2026-07-13_49680490_<title>/
│       ├── activity.json             # flat schema for the Yamareco import extension
│       ├── details.txt               # plain-text metadata
│       ├── photos.txt                # captions, one per photo
│       ├── image01.jpg … imageNN.jpg # photos, best resolution, EXIF restored
│       ├── track.gpx                 # GPS track (only if you are signed in)
│       └── index.md                  # human-readable / Obsidian journal
├── index.csv                         # one row per activity
└── manifest.json                     # resume state (safe to delete to start over)
```

### Why this is better than exporting by hand

- **Photos come out sharper.** YAMAP strips EXIF and the common extensions grab
  a downscaled, quality-50 copy. This tool fetches the stored image
  (`base_url`), which is larger and cleaner, and **writes EXIF back**: the
  capture time (to the second) and the **GPS latitude/longitude/altitude**. So
  when you import to Yamareco or Strava, the photos sort chronologically and
  land on the map automatically.
- **One universal file set.** A GPX with per-point time + elevation plus
  EXIF-tagged JPEGs is exactly what Yamareco, Strava, Garmin, and YAMAP itself
  all accept. Export once, migrate anywhere.
- **Resumable.** 36,000 photos is fine — stop and re-run any time; it skips what
  it already has.

---

## Install

Requires Python 3.9+.

```bash
pip install git+https://github.com/akiyama709/yamap-export
# to read your login cookie automatically (for GPS tracks):
pip install "yamap-export[browser] @ git+https://github.com/akiyama709/yamap-export"
```

Or from a clone:

```bash
git clone https://github.com/akiyama709/yamap-export
cd yamap-export
pip install -e ".[browser]"
```

---

## Usage

Export everything for your account (find your user id in your profile URL,
`https://yamap.com/users/<id>`):

```bash
yamap-export https://yamap.com/users/2486399 -o ./my-yamap-archive
```

Just a few activities, no tracks:

```bash
yamap-export --activity 49680490 --activity 49557155 --no-gpx -o ./out
```

Useful flags:

| flag | meaning |
|---|---|
| `-o, --outdir DIR` | output directory (default `./yamap-archive`) |
| `--activity ID/URL` | export only this activity (repeatable) |
| `--no-photos` | skip photo download |
| `--no-gpx` | skip GPS tracks (they need you to be signed in) |
| `--no-markdown` | skip the per-activity `index.md` |
| `--no-embed` | use `![](file)` links instead of Obsidian `![[file]]` embeds |
| `--limit N` | export at most N activities |
| `--delay` / `--photo-delay` | throttle (defaults 1.0s / 0.3s) |
| `--force` | re-download even if already present |

The photos and journal text are **public** and download without signing in.

### GPS tracks (sign-in required)

YAMAP serves your GPS track (`points.xml`) only to a signed-in user. The tool
gets your login token in one of three ways, tried in order:

1. **From your browser** — if you have `browser-cookie3` installed and are
   signed in to yamap.com in Chrome/Firefox/Edge/Brave, the `yamap_token`
   cookie is read automatically.
2. **From an environment variable** — `export YAMAP_TOKEN=…`
3. **From `--token …`** — copy the `yamap_token` cookie value from your
   browser's developer tools (Application → Cookies → yamap.com).

The token is used **only** to fetch your own tracks from api.yamap.com. It is
never printed, saved, or sent anywhere else. Downloading *other* people's
tracks requires YAMAP Premium and is out of scope here.

If no token is found, the tool exports everything else and just skips tracks;
re-run later with a token to fill them in (it won't re-download the rest).

---

## Migrating to another service

The GPX (with time + elevation) and the EXIF-tagged JPEGs are the universal
migration set. Per-service notes, verified against each service's own docs
(2026-07):

| Service | Track import | Limits | Photos |
|---|---|---|---|
| **Yamareco** | GPX only, `<time>` required | ~5 MB; decimate long tracks | JPEG + EXIF → auto-placed on map |
| **YAMAP** (re-import) | GPX only, times required | ≤ 10 MB, PC/web only | — |
| **Strava** | .gpx / .tcx / .fit | ≤ 25 MB, bulk 15–25 files | add manually after upload |
| **Garmin Connect** | .gpx / .tcx / .fit | ≤ 25 MB, < 99,999 points | — |

### Yamareco specifically

Yamareco has no public API for individuals, so the practical path is the
existing browser extension **[Yamareco Activity Import
Tool](https://github.com/bunatree/yamareco-activity-import-tool)** by メロンパン.
It reads exactly the `activity.json` schema this tool writes, so you can:

1. Run `yamap-export` once to produce every activity folder.
2. For each activity, open Yamareco's "create record" page, drop the folder's
   `activity.json` onto the import extension (fills title, date, genre, notes),
   upload the `imageNN.jpg` files, and let it fill the captions in order.
3. Upload `track.gpx` in the record's GPS-log step.

Please migrate **your own** records at a **gentle pace** — Yamareco's terms
prohibit overloading the service.

---

## How it works (and being a good citizen)

- Reads YAMAP's public JSON endpoints (`api.yamap.com`) — the same data the
  website shows — one request at a time with a delay. No scraping of rendered
  HTML, no parallel hammering.
- Only ever reads; never uploads or modifies anything on YAMAP.
- Intended for exporting **your own** account for backup/migration. Respect
  YAMAP's Terms of Service and other users' content.

---

## License

MIT — see [LICENSE](LICENSE). Not affiliated with or endorsed by YAMAP, Yamareco,
Strava, or Garmin.

---

<a name="日本語"></a>
## 日本語

**YAMAP の全活動日記を一括エクスポート**するコマンドラインツールです。活動日記の
本文・写真（YAMAP が出せる最良解像度で、しかも **EXIF に撮影日時と GPS を復元**）・
GPS 軌跡（GPX）をまとめて書き出し、**バックアップ**や、**ヤマレコ／Strava／Garmin／
YAMAP への移行**に使えます。

公式サイトや既存の拡張機能は **1 件ずつ**しかエクスポートできませんが、本ツールは
アカウント全体を巡回し、**中断・再開可能**で、サーバーに負担をかけないよう配慮して
います。

### 既存の手作業より優れている点

- **写真が高品質。** YAMAP は EXIF を削除し、よくある拡張機能は縮小・低品質の
  コピーを取りますが、本ツールは保存版（`base_url`）を取得し、**EXIF を書き戻し**
  ます（撮影日時を秒精度で、**GPS の緯度・経度・標高**も）。だからヤマレコや Strava
  に取り込むと、写真が時系列に並び、地図上へ自動配置されます。
- **1 セットで全サービス対応。** 時刻・標高つき GPX と EXIF つき JPEG は、ヤマレコ・
  Strava・Garmin・YAMAP のすべてが受け付ける共通形式です。一度書き出せばどこへでも。
- **再開可能。** 写真 3 万枚でも大丈夫。いつ止めても、再実行すれば済んだ分は飛ばします。

### インストール・使い方

```bash
pip install "yamap-export[browser] @ git+https://github.com/akiyama709/yamap-export"

# アカウント全体（プロフィールURL https://yamap.com/users/<id> の id を指定）
yamap-export https://yamap.com/users/2486399 -o ./my-yamap-archive
```

写真と本文は**公開データ**なのでログイン不要で取得できます。

### GPS 軌跡（要ログイン）

軌跡（`points.xml`）だけはログインが必要です。ブラウザ（Chrome/Firefox 等）で
yamap.com にサインインし `browser-cookie3` を入れておけば、`yamap_token` クッキーを
**自動で読み取ります**（`YAMAP_TOKEN` 環境変数、`--token` 指定も可）。トークンは
**自分の軌跡取得のためだけ**に使い、表示・保存・外部送信は一切しません。トークンが
無ければ軌跡以外を書き出し、後から再実行して補完できます。

### ヤマレコへの移行

ヤマレコには個人向け公開 API が無いため、既存のブラウザ拡張
**[Yamareco Activity Import Tool](https://github.com/bunatree/yamareco-activity-import-tool)**
（メロンパン氏作）を使うのが実際的です。本ツールが書き出す `activity.json` は、その
拡張がそのまま読める形式にしてあります。①本ツールで全件を一括書き出し → ②各活動で
ヤマレコの記録作成画面に `activity.json` を渡し、`imageNN.jpg` をアップロード（写真
コメントは順番どおり自動流し込み）、③`track.gpx` を GPS ログ欄にアップロード、という
流れです。**自分の記録を、常識的なペースで**移行してください（ヤマレコ規約はサーバー
への過負荷を禁じています）。

### ライセンス

MIT。YAMAP・ヤマレコ・Strava・Garmin とは無関係の非公式ツールです。自分のアカウントの
バックアップ・移行にお使いください。
