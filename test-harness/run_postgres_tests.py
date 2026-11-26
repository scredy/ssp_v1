"""Run the Django suite in a disposable schema inside the dedicated test DB.

The role intentionally does not have CREATEDB. This runner creates a unique
schema in ssp_playwright and restricts each test connection's search_path to
that schema, leaving the database's existing public schema untouched.
"""
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from psycopg import connect, sql

root = Path(__file__).resolve().parent.parent
api_dir = root / "apps" / "api"
test_env = Path(__file__).resolve().parent / ".env.test"
if not test_env.is_file():
    raise SystemExit("Refused: test-harness/.env.test is missing.")
load_dotenv(test_env, override=True)
if (os.environ.get("POSTGRES_DB"), os.environ.get("POSTGRES_USER")) != ("ssp_playwright", "ssp_playwright"):
    raise SystemExit("Refused: test environment must use the dedicated ssp_playwright database and role.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(api_dir))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
settings.CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3100"]
settings.CSRF_TRUSTED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3100"]
settings.ACCOUNT_PORTAL_URL = "http://localhost:3100"
settings.EMAIL_BACKEND = "ssp_test_email_backend.FileEmailBackend"
settings.DEFAULT_FROM_EMAIL = "SSP Playwright <noreply@example.com>"

schema = f"ssp_test_{uuid4().hex}"
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
    raise SystemExit("Refused: generated test schema name was invalid.")

with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user, has_database_privilege(current_user, current_database(), 'CREATE')")
    database, user, can_create_schema = cursor.fetchone()
if (database, user) != ("ssp_playwright", "ssp_playwright") or not can_create_schema:
    raise SystemExit("Refused: isolated test database identity or schema permission did not verify.")

database_settings = settings.DATABASES["default"]
database_settings["TEST"]["NAME"] = "ssp_playwright"
database_settings["OPTIONS"] = {"options": f"-c search_path={schema},pg_catalog"}
connection.settings_dict.update(database_settings)
connection.close()

created = False
try:
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute("SELECT current_schema(), current_database(), current_user")
        current_schema, database, user = cursor.fetchone()
        if (current_schema, database, user) != (schema, "ssp_playwright", "ssp_playwright"):
            raise SystemExit("Refused: isolated schema connection did not verify.")
    created = True
    print(f"Running Django tests in isolated PostgreSQL schema {schema} (database contents in public are preserved).")
    labels = ["accounts.tests", *(
        f"accounts.{path.stem}" for path in sorted((api_dir / "accounts").glob("*_tests.py"))
    )]
    call_command("test", *labels, keepdb=True, verbosity=2)
finally:
    connection.close()
    if created:
        connection_params = {
            "dbname": os.environ["POSTGRES_DB"],
            "user": os.environ["POSTGRES_USER"],
            "password": os.environ["POSTGRES_PASSWORD"],
            "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "port": os.environ.get("POSTGRES_PORT", "5433"),
        }
        with connect(**connection_params) as cleanup_connection:
            with cleanup_connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                if cursor.fetchone() != ("ssp_playwright", "ssp_playwright"):
                    raise SystemExit("Refused: refusing to clean up outside the isolated test database.")
                cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        print(f"Removed isolated test schema {schema}; preserved the existing test database and public schema.")
