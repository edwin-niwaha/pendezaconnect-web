# Client and loan reports release — 29 September 2026

## Included changes

- Client profile fields, gender and Joint account type; full-width directory and profile preview.
- XLSX import creates clients or updates matching trimmed, case-insensitive Reg. No values. Blank cells preserve existing values; duplicates and invalid rows are reported.
- Seven-step registration with account-owned database drafts, including photos, step recovery, stale-write protection and draft removal after successful registration.
- Corrected logout forms and POST-based session termination.
- Loan aging, arrears, portfolio-at-risk, non-performing, due/overdue, defaulted and outstanding-balance reports and dashboard navigation.

## Database migrations

Commit the client migrations 0016 through 0019 with the application code. Local migrations are already applied. Production must apply these migrations before serving the updated pages. These migrations do not import a client workbook or assign sample genders to production clients.

The Procfile release command runs deployment checks, verifies there are no missing migration files, and applies migrations non-interactively. Configure the hosting service to run the release command before starting web, worker and beat services. If the platform does not execute Procfile release processes, configure the same command as its pre-deploy command:

```sh
python manage.py check --deploy && python manage.py makemigrations --check --dry-run && python manage.py migrate --noinput
```

## Configuration and assets

Use DJANGO_ENV=production, DEBUG=False, the existing production SECRET_KEY, DATABASE_URL, domain/CSRF settings and Cloudinary configuration. Retain MOMO_PAYMENT_INITIATION_ENABLED=False while the consent issue is unresolved. Do not copy local development database settings to production.

The existing web command rebuilds static files with collectstatic before starting Gunicorn. Rebuild on the host using its installed requirements; local collected third-party assets are not a substitute for that build. Include all new source CSS, JavaScript, templates, Python modules and migrations in the release.

HSTS preload remains intentionally disabled; Django reports security.W021 as an advisory. Do not enable it solely to silence the warning. The local production-settings check uses a temporary check-only secret and does not verify the hosting service's secret or environment values.

## Verification after deployment

- Open /client/list/, view a profile and open the update page.
- Start /client/add/, enter sample information, wait for Draft saved, refresh and confirm the same step and values return. Use the same staff account. Complete registration and confirm it appears once.
- Check Import / update clients with a small reviewed workbook. Confirm existing Reg. No values update the same client record and blank fields remain unchanged.
- Sign out from navigation and confirm the session ends; a direct visit to /logout/ should render a page rather than HTTP 405.
- Check the loan dashboard, date filters and CSV report totals.
- Confirm sponsorship payment initiation still shows the temporary pause page.

Take a production database backup before release. If an application rollback is needed, roll back application code while retaining these additive profile/draft migrations unless a separate reviewed data rollback is necessary.

No production deployment or workbook import was performed during preparation.

## Local verification results

- makemigrations: no changes; migrate: no pending migrations on the local PostgreSQL database.
- Django application checks passed; production-settings checks returned only the HSTS preload advisory above.
- 100 selected regression tests passed across client profiles/drafts/import, loan aging/risk reports, login/logout, policy uploads, mobile API security and the payment pause. Tests used an isolated SQLite database with model synchronization; they do not validate production PostgreSQL data or execute the production migration path.
- Current client and loan report assets match collected copies and have manifest entries with existing hashed files.
- Git whitespace check passed. Existing collected-asset line-ending notices are informational.
