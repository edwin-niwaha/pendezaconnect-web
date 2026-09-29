# Dashboard and report caching

Dashboard and report data uses the configured Django cache: shared Redis when
`REDIS_URL` is set, or a per-process local memory cache otherwise. No schema
migration is required. Set `REPORT_CACHE_TTL` in seconds (default: 300); setting
it to zero disables these snapshots.

Cached data includes:

- LMS dashboard totals, activity and charts, and the loan notification summary.
- Sponsorship dashboard totals and chart JSON.
- Inventory dashboard totals, monthly sales and annual sales charts.
- The sponsorship reports overview counts.
- Loan aging and risk cohorts (arrears, PAR, NPL, due/overdue, defaulted and
  outstanding balances), portfolio, disbursements, collections, closed loans,
  and officer/product performance rows.

Snapshots are keyed by source domain, date and data filters. Page size, page
number, export format and presentation-only arrears filters do not trigger a
fresh portfolio query. Aging and risk reports can share the same cohort.
Cached rows are copied before formatting to prevent one report's changes from
affecting another. HTML, authentication, permissions and user-specific context
are not cached. These may still perform small queries on each request.

Normal model saves/deletes invalidate the affected domain after the database
transaction commits. Rolled-back writes do not invalidate data. Loan/client/user
changes invalidate loan snapshots; sponsorship source changes invalidate
sponsorship snapshots; inventory/product/sales changes invalidate inventory
snapshots. Old snapshots expire naturally without clearing unrelated Redis keys.

`QuerySet.update()`, `bulk_create()`, `bulk_update()` and direct SQL bypass Django
save signals. Such changes appear within the TTL, or an import/job can request
immediate refresh after committing its batch:

```python
from django.db import transaction
from core.report_cache import invalidate_report_cache

transaction.on_commit(lambda: invalidate_report_cache("loans"))
```

Use `sponsorship` or `inventory` for those source domains. Cache outages fall
back to computing the data and log a warning. Simultaneous cold misses can each
build a snapshot; this cache does not serialize first-time requests.

Performance regressions are checked in `apps.dashboard.test_report_cache`:
warm data-builder calls perform zero database queries; monthly sales use one
grouped query on a cold cache; filters, expiry, invalidation, rollback, chart
authorization, and shared HTML/CSV report rows are tested. Existing accounting
tests disable the cache because their bulk-written fixtures bypass save signals.
