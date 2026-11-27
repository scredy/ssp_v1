"""Run full Playwright acceptance journeys on a disposable PostgreSQL schema over HTTPS."""
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import socket
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from psycopg import connect, sql
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "test-harness"
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
RUN_ID = uuid4().hex[:16]
SCHEMA = f"ssp_e2e_{RUN_ID}"
RUN_DIR = HARNESS / "artifacts" / f"csrf-https-e2e-{RUN_ID}"
SCHEMA_PATTERN = re.compile(r"ssp_e2e_[a-f0-9]{16}")


def require_test_database():
    env_file = HARNESS / ".env.test"
    if not env_file.is_file():
        raise SystemExit("Refused: test-harness/.env.test is missing.")
    load_dotenv(env_file, override=True)
    if (os.environ.get("POSTGRES_DB"), os.environ.get("POSTGRES_USER")) != ("ssp_playwright", "ssp_playwright"):
        raise SystemExit("Refused: only the dedicated ssp_playwright database and role may be used.")


def db_params():
    return {
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("POSTGRES_PORT", "5433"),
    }


def wait_for(url, *, allow_errors=()):
    context = __import__("ssl")._create_unverified_context()
    deadline = time.monotonic() + 60
    last_error = "not ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, context=context, timeout=3) as response:
                if response.status < 500 or response.status in allow_errors:
                    return
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as error:
            if error.code < 500 or error.code in allow_errors:
                return
            last_error = f"HTTP {error.code}"
        except Exception as error:
            last_error = type(error).__name__
        time.sleep(1)
    raise RuntimeError(f"Local test endpoint did not become ready ({last_error}).")


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def stop_test_port_listeners(ports):
    """Clear servers started by this runner if Windows detached them from a parent."""
    if os.name != "nt":
        return
    listing = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
    if listing.returncode:
        return
    pids = set()
    for line in listing.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[3] == "LISTENING":
            try:
                port = int(fields[1].rsplit(":", 1)[1])
                pid = int(fields[-1])
            except (ValueError, IndexError):
                continue
            if port in ports:
                pids.add(pid)
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    require_test_database()
    if not SCHEMA_PATTERN.fullmatch(SCHEMA):
        raise SystemExit("Refused: invalid generated schema name.")
    for port in (3101, 8101, 3144, 8444):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(f"Refused: test port {port} is already in use; no test processes were started.")
    RUN_DIR.mkdir(parents=True, exist_ok=False)
    certificate_tool = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not certificate_tool:
        raise SystemExit("PowerShell is required to create the ephemeral local HTTPS certificate.")
    certificate = subprocess.run(
        [certificate_tool, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(HARNESS / "create_local_tls_certificate.ps1"), "-OutputDirectory", str(RUN_DIR)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if certificate.returncode:
        raise SystemExit("Could not create the ephemeral localhost HTTPS certificate.")
    pfx = RUN_DIR / "localhost-test.pfx"
    pem = RUN_DIR / "localhost-test.pem"
    passfile = RUN_DIR / "localhost-test.passphrase"
    if not all(path.is_file() for path in (pfx, pem, passfile)):
        raise SystemExit("Run create_local_tls_certificate.ps1 first with this run directory.")
    password = passfile.read_text(encoding="ascii").strip()
    (RUN_DIR / "emails").mkdir(exist_ok=True)
    (RUN_DIR / "media").mkdir(exist_ok=True)
    (RUN_DIR / "private_payment_evidence").mkdir(exist_ok=True)
    (RUN_DIR / "private_handover_evidence").mkdir(exist_ok=True)
    Image.new("RGB", (32, 24), (186, 36, 36)).save(RUN_DIR / "vehicle-photo.png", format="PNG")

    with connect(**db_params()) as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, has_database_privilege(current_user, current_database(), 'CREATE')")
            database, user, can_create = cursor.fetchone()
            if (database, user) != ("ssp_playwright", "ssp_playwright") or not can_create:
                raise SystemExit("Refused: isolated database identity/schema permission did not verify.")
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
    print(f"Created isolated PostgreSQL schema {SCHEMA} in the dedicated Playwright test database.", flush=True)

    env = os.environ.copy()
    env.update({
        "PGOPTIONS": f"-c search_path={SCHEMA},pg_catalog",
        "SSP_TEST_SCHEMA": SCHEMA,
        "SSP_TEST_BASE_URL": "https://localhost:3144",
        "SSP_TEST_ARTIFACTS_DIR": str(RUN_DIR),
        "SSP_TEST_RESULTS_DIR": str(RUN_DIR / "test-results"),
        "SSP_TEST_REPORT_DIR": str(RUN_DIR / "html-report"),
        "SSP_TEST_ENV_FILE": str(RUN_DIR / ".env.e2e"),
        "SSP_TEST_EMAIL_DIR": str(RUN_DIR / "emails"),
        "MEDIA_ROOT": str(RUN_DIR / "media"),
        "PRIVATE_PAYMENT_EVIDENCE_ROOT": str(RUN_DIR / "private_payment_evidence"),
        "PRIVATE_HANDOVER_EVIDENCE_ROOT": str(RUN_DIR / "private_handover_evidence"),
    })

    sys.path.insert(0, str(HARNESS))
    sys.path.insert(0, str(API))
    os.environ.update(env)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection
    from accounts.models import User

    settings.DATABASES["default"]["OPTIONS"] = {"options": env["PGOPTIONS"]}
    connection.settings_dict.update(settings.DATABASES["default"])
    connection.close()
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema(), current_database(), current_user")
        if cursor.fetchone() != (SCHEMA, "ssp_playwright", "ssp_playwright"):
            raise SystemExit("Refused: Django connection did not select the unique test schema.")
    call_command("migrate", interactive=False, verbosity=1)
    username = "pw_admin"
    admin_password = "SSP!" + secrets.token_urlsafe(30)
    User.objects.create_superuser(
        username=username,
        email="admin@example.test",
        password=admin_password,
        role=User.Role.ADMIN,
        first_name="Nora",
        last_name="Perera",
        phone="+94 77 555 0101",
    )
    env_path = Path(env["SSP_TEST_ENV_FILE"])
    env_path.write_text(f"SSP_TEST_ADMIN_USERNAME={username}\nSSP_TEST_ADMIN_PASSWORD={admin_password}\n", encoding="utf8")
    print("Applied migrations and created an ephemeral Admin account only in the isolated test schema.", flush=True)

    # Keep the running HTTP services on localhost and use local TLS terminators to
    # exercise the production HTTPS cookie/CSRF path without Render or real users.
    node = shutil.which("node") or "node"
    python = str(ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe")
    if not Path(python).is_file():
        python = sys.executable
    api_process = web_process = api_tls = web_tls = None
    result = 1
    try:
        api_env = env.copy()
        api_env["SSP_TEST_EMAIL_DIR"] = str(RUN_DIR / "emails")
        api_process = subprocess.Popen([python, str(HARNESS / "serve_prodlike_api.py")], cwd=ROOT, env=api_env)
        api_tls = subprocess.Popen([node, str(HARNESS / "https-forwarder.mjs"), "8444", "8101", str(pfx), password], cwd=ROOT, env=env)
        web_env = env.copy()
        web_env.update({"API_UPSTREAM_URL": "https://localhost:8444", "NODE_EXTRA_CA_CERTS": str(pem), "NODE_ENV": "production"})
        web_process = subprocess.Popen(
            [node, str(WEB / "node_modules" / "next" / "dist" / "bin" / "next"), "start",
             "--hostname", "127.0.0.1", "--port", "3101"],
            cwd=WEB,
            env=web_env,
        )
        web_tls = subprocess.Popen([node, str(HARNESS / "https-forwarder.mjs"), "3144", "3101", str(pfx), password], cwd=ROOT, env=env)

        wait_for("https://localhost:8444/healthz")
        wait_for("https://localhost:3144/")
        playwright = HARNESS / "node_modules" / ".bin" / "playwright.cmd"
        if not playwright.is_file():
            raise SystemExit("Playwright is not installed under test-harness/node_modules.")
        completed = subprocess.run([str(playwright), "test"], cwd=HARNESS, env=env)
        result = completed.returncode
    finally:
        for process in (web_tls, web_process, api_tls, api_process):
            stop_process(process)
        stop_test_port_listeners({3101, 8101, 3144, 8444})
        connection.close()
        with connect(**db_params()) as cleanup:
            with cleanup.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                if cursor.fetchone() != ("ssp_playwright", "ssp_playwright"):
                    raise SystemExit("Refused: cleanup database identity changed.")
                cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", (SCHEMA,))
                if cursor.fetchone() is None:
                    raise SystemExit("Refused: generated E2E schema was not found during cleanup.")
                cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(SCHEMA)))
        print(f"Removed only isolated test schema {SCHEMA}; preserved ssp_playwright.public and all prior artifacts.", flush=True)
        print(f"HTTPS Playwright artifacts are isolated in {RUN_DIR}.", flush=True)
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise
