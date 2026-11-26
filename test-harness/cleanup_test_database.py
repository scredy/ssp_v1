"""Fail-closed cleanup for only the isolated SSP Playwright database/role."""
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
TEST_ENV_PATH = ROOT / "test-harness" / ".env.test"
if not TEST_ENV_PATH.is_file():
    raise SystemExit("Refused: test-harness/.env.test is missing.")

repository_env = {
    **dotenv_values(ROOT / ".env"),
    **dotenv_values(ROOT / "apps" / "api" / ".env"),
}
test_env = dotenv_values(TEST_ENV_PATH)
target = "ssp_playwright"
if test_env.get("POSTGRES_DB") != target or test_env.get("POSTGRES_USER") != target:
    raise SystemExit("Refused: test environment does not name the dedicated database and role.")

admin_config = {
    "host": repository_env.get("POSTGRES_HOST", "127.0.0.1"),
    "port": int(repository_env.get("POSTGRES_PORT", "5433")),
    "user": repository_env.get("POSTGRES_USER"),
    "password": repository_env.get("POSTGRES_PASSWORD"),
}
test_config = {
    "host": test_env.get("POSTGRES_HOST"),
    "port": int(test_env.get("POSTGRES_PORT", "5433")),
    "user": test_env.get("POSTGRES_USER"),
    "password": test_env.get("POSTGRES_PASSWORD"),
}
if not admin_config["user"] or not admin_config["password"]:
    raise SystemExit("Refused: repository maintenance credentials are unavailable.")

# This probe is explicitly against database postgres, regardless of the
# repository's configured database name. It does not connect to ssp_dev.
with psycopg.connect(dbname="postgres", **admin_config, autocommit=True) as admin:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port(), "
            "(SELECT rolcreatedb AND rolcreaterole FROM pg_roles WHERE rolname=current_user), "
            "EXISTS (SELECT 1 FROM pg_database WHERE datname=%s), "
            "(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s), "
            "EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)",
            [target, target, target],
        )
        db, actor, address, port, provision_rights, db_exists, owner, role_exists = cursor.fetchone()
    if db != "postgres" or not address or actor != admin_config["user"] or not provision_rights:
        raise SystemExit("Refused: maintenance connection identity or limited cleanup rights did not verify.")
    if not db_exists or not role_exists or owner != target:
        raise SystemExit(f"Refused: expected database and role ownership was not verified: db={db_exists}, role={role_exists}, owner={owner!r}.")
    print(f"Maintenance identity verified: database={db}, role={actor}, server={address}:{port}; isolated DB owner={owner}.")

# The dedicated login owns the target database. Connect as that owner to the
# maintenance database and drop only ssp_playwright after checking no clients
# remain. Application servers have been stopped before this script is run.
with psycopg.connect(dbname="postgres", **test_config, autocommit=True) as test_owner:
    with test_owner.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), current_user, "
            "(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s), "
            "(SELECT COUNT(*) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid())",
            [target, target],
        )
        db, actor, owner, connections = cursor.fetchone()
    if (db, actor, owner, connections) != ("postgres", target, target, 0):
        raise SystemExit(f"Refused: test-owner cleanup check failed: db={db}, role={actor}, owner={owner}, sessions={connections}.")
    with test_owner.cursor() as cursor:
        cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(target)))
    print(f"Dropped only database {target} from maintenance database postgres.")

with psycopg.connect(dbname="postgres", **admin_config, autocommit=True) as admin:
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), current_user, "
            "EXISTS (SELECT 1 FROM pg_database WHERE datname=%s), "
            "EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)",
            [target, target],
        )
        db, actor, db_exists, role_exists = cursor.fetchone()
    if db != "postgres" or actor != admin_config["user"] or db_exists or not role_exists:
        raise SystemExit("Refused: target database removal was not confirmed from maintenance database postgres.")
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(target)))
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), EXISTS (SELECT 1 FROM pg_database WHERE datname=%s), "
            "EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)",
            [target, target],
        )
        db, db_exists, role_exists = cursor.fetchone()
    if db != "postgres" or db_exists or role_exists:
        raise SystemExit("Cleanup verification failed: target database or role still exists.")
    print(f"Cleanup verified from {db}: {target} database absent; {target} role absent.")
