release: python manage.py migrate

web: python manage.py collectstatic --noinput && gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 4 --max-requests 1000 --max-requests-jitter 100 --log-level info --access-logfile - --error-logfile -

worker: celery -A core worker --loglevel=INFO --pool=solo --concurrency=1 --prefetch-multiplier=1 --without-gossip --without-mingle

beat: celery -A core beat --loglevel=INFO