# Health status

Result: **healthy**

Last checked: 2026-10-05 05:02 UTC

`scripts/healthcheck.py` probes the live YAMAP API and asserts the
fields, image CDN, and User-Agent behaviour that the exporter depends
on. This file is written by the scheduled healthcheck workflow.

```
yamap-export health check (UA: 'Mozilla/5.0 (compatible) yamap-export/0.1 (+https://github.com/akiyama709/yamap-export)')
  PASS  user activity listing — 346 activities listed
  PASS  activity detail shape — 77 photos, title present
  PASS  exporter transform — flat record OK
  PASS  photo CDN — DEGRADED — the largest 1 URL(s) are down (HTTP 503); falling back to a smaller size, image/jpeg
  SKIP  GPS track download — set YAMAP_TOKEN to include it

HEALTHY — yamap-export works against the live YAMAP API.
```
