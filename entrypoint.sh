#!/usr/bin/env sh
set -e

# Apply DB schema, gather static files, then start the app server.
echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
