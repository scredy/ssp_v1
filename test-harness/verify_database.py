"""Read-only identity probe restricted to the local maintenance/test DB names."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

root = Path(__file__).resolve().parent.parent
api_dir = root / "apps" / "api"
target = sys.argv[1] if len(sys.argv) == 2 else ""
if target not in {"postgres", "ssp_playwright"}:
    raise SystemExit("Allowed verification targets: postgres, ssp_playwright")

# Use the dedicated test credentials for the app database. The maintenance
# probe deliberately uses only the repository role against database postgres.
if target == "ssp_playwright":
    test_env = root / "test-harness" / ".env.test"
    if not test_env.exists():
        raise SystemExit("Refused: dedicated test environment is missing.")
    load_dotenv(test_env, override=True)
    if os.environ.get("POSTGRES_DB") != target or os.environ.get("POSTGRES_USER") != target:
        raise SystemExit("Refused: test environment does not name the dedicated DB and role.")
else:
    load_dotenv(root / ".env", override=False)
    os.environ["POSTGRES_DB"] = "postgres"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(api_dir))
import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402

with connection.cursor() as cursor:
    cursor.execute(
        "SELECT current_database(), inet_server_addr()::text, inet_server_port(), "
        "current_user, (SELECT rolcreatedb FROM pg_roles WHERE rolname=current_user), "
        "(SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user), "
        "pg_is_in_recovery(), (SELECT COUNT(*) FROM pg_database WHERE datname=%s)",
        ["ssp_playwright"],
    )
    result = cursor.fetchone()
    if result[0] != target:
        raise SystemExit(f"Refused: connected database identity was {result[0]!r}.")
    print("database_probe=" + repr(result))
