# ENTRYPOINT: SAGE Production WSGI
# Gunicorn/Waitress/Passenger can import `app` from this module.

from app import app

application = app
