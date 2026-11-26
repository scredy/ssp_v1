# SSP Playwright acceptance harness

This folder is outside `apps/web` and `apps/api`. It contains the fail-closed
environment setup helpers, Playwright specs, and acceptance evidence. No
application source or existing local configuration was changed. The completed
test database and credentials were removed after the run; a future run needs a
new isolated database and test-only environment file.

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

See [report.md](report.md), [steps.jsonl](artifacts/steps.jsonl), screenshots,
and the Playwright trace under `artifacts/test-results` for the recorded run.
