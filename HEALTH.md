# Health status

Result: **healthy**

Last checked: 2026-09-07 03:36 UTC

`scripts/healthcheck.py` probes the live YAMAP API and asserts the
fields, image CDN, and User-Agent behaviour that the exporter depends
on. This file is written by the scheduled healthcheck workflow.

```
yamap-export health check (UA: 'Mozilla/5.0 (compatible) yamap-export/0.1 (+https://github.com/akiyama709/yamap-export)')
  PASS  user activity listing — 337 activities listed
  PASS  activity detail shape — 77 photos, title present
  PASS  exporter transform — flat record OK
  PASS  photo CDN — HTTP 200, image/jpeg
  SKIP  GPS track download — set YAMAP_TOKEN to include it

HEALTHY — yamap-export works against the live YAMAP API.
```
