release: python manage.py migrate --noinput
web: gunicorn plec_project.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 60
