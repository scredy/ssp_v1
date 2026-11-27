"""Start Django with production HTTPS/cookie settings on an isolated test schema."""
import os
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
api_dir = root / "apps" / "api"
sys.path.insert(0, str(api_dir))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env.test", override=True)
schema = os.environ.get("SSP_TEST_SCHEMA", "")
if os.environ.get("POSTGRES_DB") != "ssp_playwright" or os.environ.get("POSTGRES_USER") != "ssp_playwright":
    raise SystemExit("Refused: only the dedicated Playwright PostgreSQL database is allowed.")
if not re.fullmatch(r"ssp_e2e_[a-f0-9]{16}", schema):
    raise SystemExit("Refused: missing or invalid isolated E2E schema.")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT current_schema(), current_database(), current_user")
    if cursor.fetchone() != (schema, "ssp_playwright", "ssp_playwright"):
        raise SystemExit("Refused: isolated E2E database/schema identity did not verify.")

frontend_origin = "https://localhost:3144"
settings.DEBUG = False
settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
settings.CSRF_TRUSTED_ORIGINS = [frontend_origin]
settings.CSRF_COOKIE_DOMAIN = None
settings.CSRF_COOKIE_SECURE = True
settings.SESSION_COOKIE_SECURE = True
settings.SECURE_SSL_REDIRECT = True
settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
settings.ACCOUNT_PORTAL_URL = frontend_origin
settings.CORS_ALLOWED_ORIGINS = [frontend_origin]
settings.EMAIL_BACKEND = "ssp_test_email_backend.FileEmailBackend"
settings.DEFAULT_FROM_EMAIL = "SSP Playwright <noreply@example.test>"
settings.MEDIA_ROOT = Path(os.environ["MEDIA_ROOT"])
settings.PRIVATE_PAYMENT_EVIDENCE_ROOT = Path(os.environ["PRIVATE_PAYMENT_EVIDENCE_ROOT"])
settings.PRIVATE_HANDOVER_EVIDENCE_ROOT = Path(os.environ["PRIVATE_HANDOVER_EVIDENCE_ROOT"])
os.environ.setdefault("SSP_TEST_EMAIL_DIR", str(Path(os.environ["SSP_TEST_ARTIFACTS_DIR"]) / "emails"))

print(f"Serving production-like HTTPS API against isolated schema {schema}.", flush=True)
call_command("runserver", "127.0.0.1:8101", use_reloader=False)
