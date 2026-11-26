"""Run a Django management command only after the isolated DB identity check."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
api_dir = root / "apps" / "api"
test_env = Path(__file__).resolve().parent / ".env.test"
if not test_env.is_file():
    raise SystemExit("Refused: test-harness/.env.test is missing.")

from dotenv import load_dotenv

load_dotenv(test_env, override=True)
if os.environ.get("POSTGRES_DB") != "ssp_playwright" or os.environ.get("POSTGRES_USER") != "ssp_playwright":
    raise SystemExit("Refused: test environment does not name the dedicated DB and role.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(api_dir))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection

settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
settings.CORS_ALLOWED_ORIGINS = ["http://localhost:3100"]
settings.CSRF_TRUSTED_ORIGINS = ["http://localhost:3100"]
settings.ACCOUNT_PORTAL_URL = "http://localhost:3100"
settings.EMAIL_BACKEND = "ssp_test_email_backend.FileEmailBackend"
settings.DEFAULT_FROM_EMAIL = "SSP Playwright <noreply@example.com>"

with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user")
    database, user = cursor.fetchone()
if (database, user) != ("ssp_playwright", "ssp_playwright"):
    raise SystemExit(f"Refused: connected identity {(database, user)!r} is not the isolated test DB and role.")
if len(sys.argv) < 2:
    raise SystemExit("Usage: manage_test_db.py <django-command> [arguments]")

call_command(sys.argv[1], *sys.argv[2:])
