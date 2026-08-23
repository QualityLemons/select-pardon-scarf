release: python manage.py repair_auth && python manage.py migrate_legacy_users && python -c "import create_db; create_db.ensure()"
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
