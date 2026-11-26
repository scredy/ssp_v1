"""Create the single bootstrap administrator in the verified test database."""
import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "apps" / "api"))
from dotenv import load_dotenv

load_dotenv(root / "test-harness" / ".env.test", override=True)
if os.environ.get("POSTGRES_DB") != "ssp_playwright" or os.environ.get("POSTGRES_USER") != "ssp_playwright":
    raise SystemExit("Refused: test database identity configuration does not match.")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.db import connection
from accounts.models import User

with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user")
    if cursor.fetchone() != ("ssp_playwright", "ssp_playwright"):
        raise SystemExit("Refused: connected identity is not the isolated test DB and role.")

username = "pw_admin"
password = "SSP!Admin!" + secrets.token_urlsafe(18)
if User.objects.filter(username=username).exists():
    raise SystemExit("Refused: bootstrap account already exists; inspect test DB state.")
User.objects.create_superuser(
    username=username,
    email="admin@example.com",
    password=password,
    role=User.Role.ADMIN,
    first_name="Nora",
    last_name="Perera",
    phone="+94 77 555 0101",
)
env_file = root / "test-harness" / ".env.test"
with env_file.open("a", encoding="utf8") as handle:
    handle.write(f"\nSSP_TEST_ADMIN_USERNAME={username}\nSSP_TEST_ADMIN_PASSWORD={password}\n")
print("Bootstrap Admin created in verified ssp_playwright database; credentials stored in test-harness/.env.test")
