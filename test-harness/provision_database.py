"""Create only the dedicated SSP Playwright database and login role."""
import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
api_dir = root / "apps" / "api"
sys.path.insert(0, str(api_dir))
os.environ["POSTGRES_DB"] = "postgres"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402
from psycopg import sql  # noqa: E402

name = "ssp_playwright"
with connection.cursor() as cursor:
    cursor.execute(
        "SELECT current_database(), inet_server_addr()::text, inet_server_port(), "
        "(SELECT rolcreatedb AND rolcreaterole FROM pg_roles WHERE rolname=current_user), "
        "EXISTS (SELECT 1 FROM pg_database WHERE datname=%s), "
        "EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)",
        [name, name],
    )
    db_name, address, port, can_provision, db_exists, role_exists = cursor.fetchone()

if db_name != "postgres" or not address or not can_provision:
    raise SystemExit("Refused: maintenance database identity or provisioning rights did not verify.")
if db_exists or role_exists:
    raise SystemExit("Refused: ssp_playwright database or role already exists; inspect before reuse.")

password = secrets.token_urlsafe(36)
raw = connection.connection
raw.autocommit = True
raw.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(name), sql.Literal(password)))
raw.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(name)))
raw.autocommit = False

test_env = root / "test-harness" / ".env.test"
secret_key = secrets.token_urlsafe(48)
test_env.write_text(
    "\n".join([
        "POSTGRES_DB=ssp_playwright",
        f"POSTGRES_USER={name}",
        f"POSTGRES_PASSWORD={password}",
        "POSTGRES_HOST=127.0.0.1",
        "POSTGRES_PORT=5433",
        "DJANGO_DEBUG=1",
        f"DJANGO_SECRET_KEY={secret_key}",
        "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1",
        "CORS_ALLOWED_ORIGINS=http://localhost:3100",
        "CSRF_TRUSTED_ORIGINS=http://localhost:3100",
        "ACCOUNT_PORTAL_URL=http://localhost:3100",
        "EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend",
        "DEFAULT_FROM_EMAIL=SSP Playwright <noreply@example.com>",
    ]) + "\n",
    encoding="utf8",
)
print(f"Created database {name} and dedicated login role; server={address}:{port}; credentials saved only in test-harness/.env.test")
