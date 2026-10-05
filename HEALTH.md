# Health status

Result: **BROKEN**

Last checked: 2026-10-05 04:23 UTC

`scripts/healthcheck.py` probes the live YAMAP API and asserts the
fields, image CDN, and User-Agent behaviour that the exporter depends
on. This file is written by the scheduled healthcheck workflow.

```
yamap-export health check (UA: 'Mozilla/5.0 (compatible) yamap-export/0.1 (+https://github.com/akiyama709/yamap-export)')
  PASS  user activity listing — 346 activities listed
  PASS  activity detail shape — 77 photos, title present
  PASS  exporter transform — flat record OK
  FAIL  photo CDN — CheckFailed: HTTP 503, content-type 'text/html'
  SKIP  GPS track download — set YAMAP_TOKEN to include it

BROKEN — yamap-export needs an update; see failures above.
```
