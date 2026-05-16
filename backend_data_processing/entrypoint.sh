#!/bin/bash
set -e

# Run Django migrations and collect static files
echo "Running migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the Django development server
echo "Starting Django server..."
exec "$@"
