# Background client imports

Client uploads now create a database-backed job and redirect to its status page.
Celery receives only the job ID; workbook bytes are stored in the database so
web and worker services do not need a shared filesystem. Completed and failed
jobs discard the uploaded bytes and retain counts and row errors.

Deployment requires the web and worker services to use the same database and
Celery broker. Apply migrations, including client migration 0020, before serving
the new page. The existing Procfile release command applies migrations. Run the
existing worker process (`celery -A core worker --loglevel=INFO --pool=solo
--concurrency=1 --prefetch-multiplier=1 --without-gossip --without-mingle`) with
the same application revision. Deploying only the web service is insufficient.

The importer uses two streaming passes, first checking duplicate registration
numbers and then validating and saving rows. Matching uses an index on
`LOWER(TRIM(reg_number))`. Valid rows commit separately; invalid rows are skipped.
Uploads are limited to 10 MB, 25,000 rows and 100 MB of expanded ZIP contents.
Progress is saved every 100 rows and on completion. The status page checks every
five seconds without holding an HTTP request open for the import.

If the broker rejects submission, the job shows a queue error. If a job stays
queued, check that the worker is running and consuming the same broker. If a
worker is forcibly killed, a job may remain in processing; inspect worker logs
before re-uploading. Normal application exceptions mark the job failed. Retrying
the workbook matches existing registration numbers and preserves blank fields,
so already-saved rows are updated or left unchanged. Do not run overlapping
uploads for the same registration numbers concurrently.

Validation: client tests cover background submission, results, duplicate task
delivery, queue failure, invalid workbooks, private status pages, streaming
progress, and existing field/duplicate/blank-value rules. The local tests use
SQLite and direct task execution; verify worker delivery and the migration on
production PostgreSQL during deployment.
