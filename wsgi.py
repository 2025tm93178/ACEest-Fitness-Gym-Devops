"""WSGI entry point used by gunicorn inside the container."""
from app import create_app

app = create_app()
