# SSP Playwright acceptance harness

This folder is outside `apps/web` and `apps/api`. It contains the fail-closed
environment setup helpers, Playwright specs, and acceptance evidence. Keep
`test-harness/.env.test` local; it is ignored by Git and must name only the
dedicated `ssp_playwright` database and role.

Run the preflight from the repository root with:

```powershell
node test-harness/preflight.mjs
```

The preflight confirms that a read-only database identity query reaches the
dedicated test database, verifies Playwright is installed under this folder,
and probes the test web/API ports. It does not write database records.

The test runner used API port `8100` and Next.js port `3100`. Django commands
were wrapped by `manage_test_db.py`, which verifies both `current_database()`
and `current_user` are exactly `ssp_playwright` before running the command.
Outbound mail was replaced with a file-only backend under `artifacts/emails`
during the run.

Run the full Django suite against PostgreSQL with:

```powershell
apps\api\.venv\Scripts\python.exe test-harness\run_postgres_tests.py
```

The runner does not require the application role to create databases. It creates
a unique temporary schema in `ssp_playwright`, sets PostgreSQL `search_path` to
that schema only, runs all account tests (including row-lock concurrency tests),
and removes only the temporary schema afterward. The existing `public` schema
and its contents are not used or changed.

See [report.md](report.md), [steps.jsonl](artifacts/steps.jsonl), screenshots,
and the Playwright trace under `artifacts/test-results` for the recorded run.
