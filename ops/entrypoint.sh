#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py bootstrap_storage
exec daphne -b 0.0.0.0 -p 8000 relay.asgi:application
