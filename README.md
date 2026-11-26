# ssp_v1

## Monorepo structure

- `apps/web/` is the Next.js and TypeScript browser application. It calls the API over HTTP and contains no database credentials or database client.
- `apps/api/` is the Django REST Framework backend. It is the only app that reads PostgreSQL credentials and connects to the database.
- The root `compose.yaml` runs the local PostgreSQL service; its existing setup is kept separate from application code.

## Run locally (PowerShell)

Requirements: Docker Compose, Python 3.10+, and Node.js 20.9+.

Start PostgreSQL from the repository root:

```powershell
docker compose up -d db
```

In a backend terminal, from the repository root:

```powershell
if (-not (Test-Path apps/api/.env)) { Copy-Item apps/api/.env.example apps/api/.env }
Set-Location apps/api
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver localhost:8000
```

The API loads PostgreSQL settings from the ignored repository-root `.env`; Django-only settings come from `apps/api/.env`. The database-aware readiness endpoint is `http://localhost:8000/healthz` (the existing `api/health/` endpoint remains available).

In a separate frontend terminal, from the repository root:

```powershell
if (-not (Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
Set-Location apps/web
npm install
npm run dev
```

Open `http://localhost:3000`. The browser reads only `NEXT_PUBLIC_API_BASE_URL` and sends an HTTP request to the backend. Do not put database credentials in the web app or its environment files.

## Authentication foundation

The Django REST API owns users, role checks, audit events, commission rule configuration, vehicle inventory, and all persistence. The Next.js app owns the public website and staff portal UI. Public pages remain available without signing in; `/cars` and `/cars/[reference]` browse published stock, and `/staff/inventory` is the role-aware inventory workspace.

### Roles and initial capabilities

Every account has one distinct role. MD and Manager use the single `manager` role.

| Role | Initial API capabilities |
| --- | --- |
| Admin | Create/list/update/deactivate internal and external accounts; view the latest account activity and audit events. |
| CEO | Review MD/Manager activity, sales, payments, handovers, and inventory; finalize reviewed handovers; manage commission brackets. |
| MD/Manager | Manage sales, payments, representative accounts, and handover finalization; review inventory and CEO-controlled commission brackets. |
| Staff | Manage inventory, reservations, imports, quotations, enquiries, and handover preparation; sales confirmation and handover finalization remain leadership-controlled. |
| Rep | Read-only access to own assigned sales and commission ledger entries, including private paid totals. |

API permissions default to authenticated-only; role-specific endpoints require a named capability and unknown or missing capabilities are denied. Inventory reads require Staff, CEO, or MD/Manager; every inventory write is restricted server-side to Staff. Admin and Rep cannot read or write the staff inventory API. Handovers support Staff and MD/Manager preparation/submission; MD/Manager or CEO can finalize complete reviewed handovers. Evidence stays private. The CEO alone manages effective-dated commission brackets; MD/Manager can review them. A unique commission ledger entry is created only on finalized handover, and reps can read only entries assigned to their own Rep account. CEO and MD/Manager can record auditable manual approval, payout, and reversal states. Paid totals and the management leaderboard include only non-reversed paid entries; no money transfer is initiated.

### Audit history

The Admin activity screen reads `/api/activity/recent/` and can review all recorded account and system events. The CEO leadership-oversight screen reads `/api/oversight/managers/` and is restricted server-side to events whose actor currently has the MD/Manager role. MD/Manager access remains limited to existing policy-history reads; they do not receive general audit history. Staff and Rep have no management audit-history access. The API requires the `activity.view` capability (Admin) or `manager_oversight.view` capability (CEO), and applies these filters before pagination.

Both screens support search across action, actor username, and affected record; exact action, actor username, role, and inclusive `date_from` / `date_to` filters (`YYYY-MM-DD`); and limit/offset pagination. The API returns 25 rows by default and caps `limit` at 100. Only action-specific reviewed fields are returned from event details; free-text reasons, notes, evidence paths, tracking credentials, payout references, passwords, and raw invitation/reset tokens are excluded. Actor role is read from the current account because the existing audit model does not store a role snapshot for each event.
### In-app notifications

The role-aware staff portal provides a private inbox at `/staff/notifications`, backed by authenticated `/api/notifications/` endpoints. From `apps/api`, apply its additive migration with `python manage.py migrate accounts 0018_notification_inbox`. Do not expose or send these notifications by email; the inbox is the in-app channel.

Notifications are created in the same database transaction as the successful workflow action, and each recipient/event pair is unique so retries do not create duplicates. Handover submission notifies active CEO and MD/Manager reviewers other than the submitter. A handover returned for updates or finalized notifies the latest submitting user (read from the existing submission audit event, falling back to the preparer for older records) and active CEO/MD/Manager reviewers other than the acting reviewer. Assigning a Rep to a sale notifies that active Rep. A newly recorded payment notifies active CEO and MD/Manager reviewers; verification or rejection notifies the recorder. A BL approval request notifies active CEOs; an approval or rejection notifies the user who requested it. Messages use workflow references and avoid customer details. The inbox shows unread count and newest-first records; each user can only list or change the read state of their own notifications.

### Public appointment requests

The public `/book-appointment` form uses the existing enquiry API and model; it creates a `new` appointment or test-drive request rather than a confirmed booking. The visitor receives a reference and sees that SSP must confirm availability. Preferred date/time is interpreted in the configured `Asia/Colombo` timezone. A visitor may select a published available vehicle or leave it blank. Public POSTs are limited to five per hour per anonymous client and use an idempotency key; invalid or unavailable vehicle references are rejected server-side.

Staff, CEO, and MD/Manager can search and review requests in the existing `/staff/enquiries` queue. These roles are enforced by the `enquiries.manage` API capability; public users cannot read the queue or change status. Authorized staff can mark a request contacted, schedule it with a confirmed time, complete it, or cancel it. A successful appointment or test-drive request notifies active queue roles through the in-app inbox using only the request kind and reference. When an email address is supplied, SSP sends a confirmation that the submission is a request, not a booking. In local `DEBUG` mode this uses Django's console email backend by default; read the message in the API terminal. Production delivery uses the configured email backend. Email delivery is best effort and does not undo a saved request.

### Import sales and handover

MD/Manager can create a draft sale from a customer import once its import order is `Ready for Collection`, has a linked registered vehicle that remains available, and does not already have a sale. Staff can link the newly registered available vehicle in the import edit form if it was not known when the order was first created. Customer and vehicle are taken from the import order; they cannot be substituted in the sale request. The unique sale-to-import link prevents duplicates. Verified payments recorded against the import before sale are included in the sale balance and price ceiling. Sale confirmation still requires the existing MD/Manager permission; handover preparation/review/finalization uses the existing role boundary. Finalizing that handover adds the protected final-handover milestone and changes the import status to `Handed Over`, visible in the import timeline and customer tracking response. It does not change the commission eligibility rule: the existing finalized-handover workflow creates the ledger entry from the agreed sale price and active CEO policy snapshot.

The sale-to-import relationship and terminal import status are additive in accounts migration `0019_import_sale_link`. From `apps/api`, apply pending migrations with `python manage.py migrate accounts 0019_import_sale_link` after the preceding accounts migrations, or `python manage.py migrate` when setting up the development database.
### Vehicle inventory

Staff vehicle records contain an automatically generated unique reference; make, model, variant/grade, manufacture year, mileage in km, fuel type, transmission, color, condition, private chassis/VIN/stock identifier, LKR asking price, description, draft/published visibility, created/updated timestamps, and associated photos. Money uses decimal precision. The API validates year, mileage, positive price, and enum values. Fuel choices are petrol, diesel, hybrid, electric, and other; transmission is automatic, manual, or other; condition is new, used, or reconditioned.

The chassis/VIN/stock identifier is returned only by the authenticated staff inventory API. It is omitted from all public serializers and public vehicle responses. Public endpoints expose only published vehicles and their image links. Draft photo bytes are also protected by the image endpoint; only authenticated Staff, CEO, and MD/Manager can retrieve them. Uploaded photos must be valid JPEG, PNG, or WebP images, no larger than 8 MB each, with at most 10 photos per vehicle. Names are generated by the API. Local development stores images under `apps/api/media/` and serves them through Django's access-checked photo endpoint; no cloud storage is configured.

| Endpoint | Methods / access |
| --- | --- |
| `/api/staff/inventory/` | GET for Staff, CEO, MD/Manager; POST for Staff |
| `/api/staff/inventory/<reference>/` | GET for Staff, CEO, MD/Manager; PATCH for Staff |
| `/api/staff/inventory/<reference>/photos/` | POST multipart `photos` for Staff |
| `/api/staff/inventory/<reference>/photos/<photo_id>/` | DELETE for Staff |
| `/api/cars/` | Public GET; published vehicles only. Filters: `search` (make/model), `year`, `fuel`, `transmission`, `min_price`, `max_price` |
| `/api/cars/<reference>/` | Public GET; published vehicle only |
| `/api/vehicle-photos/<photo_id>/` | Public GET for published vehicles; authenticated Staff/CEO/MD/Manager for draft photos |

Vehicle schema is added by `accounts` migration `0002_vehicle_inventory`, which depends on the existing `0001_initial` custom-user/authentication migration. This task creates the migration file but does not apply it. From `apps/api`, apply it with `python manage.py migrate accounts 0002_vehicle_inventory` (or run `python manage.py migrate` for all pending migrations). The normal first-start instructions above already run all migrations before creating the first account.

### Sign-in and session security

The browser first requests `GET /api/auth/csrf/`, then posts credentials to `POST /api/auth/login/` with the CSRF cookie echoed in `X-CSRFToken`. Django establishes an HttpOnly session cookie. The browser uses `credentials: "include"` for `GET /api/auth/me/` and `POST /api/auth/logout/`; logout also requires CSRF. No authentication token is stored in browser storage. The API uses a login throttle, password validation (12 character minimum plus Django's common-password checks), credentialed CORS for the configured local web origins, SameSite=Lax cookies, and secure cookies/HTTPS redirect when `DJANGO_DEBUG` is disabled. Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` for the deployment environment; production refuses the development-only fallback secret.

### First setup

Keep the web app and API on the same local hostname so browser cookie rules work. The defaults use `http://localhost:3000` for Next.js and `http://localhost:8000` for Django. If you choose `127.0.0.1`, set `NEXT_PUBLIC_API_BASE_URL`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` to matching origins in your local configuration.

For the first account, enter `admin` for the role when `createsuperuser` prompts; no demo users or passwords are seeded. Before using invitation and password-reset links, apply the additive account-token migration from `apps/api` with `python manage.py migrate accounts 0017_account_action_tokens`. Admins can create internal CEO, MD/Manager, Staff, or Rep accounts through the protected `/api/accounts/` endpoint. New accounts remain inactive until the recipient follows a single-use password-setup invitation; invitation links expire after 24 hours and only token hashes are stored. Account creation does not accept plaintext passwords, and there is no public self-registration. In local `DEBUG` mode Django uses its console email backend by default, so the invitation/reset email (and link) appears only in the API terminal output, never in the API response. Open the link there in the browser. Set `ACCOUNT_PORTAL_URL` if the web app is not at `http://localhost:3000`. For SMTP, configure `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL`; with `DEBUG` disabled, SMTP is the default backend. The repository defines `accounts/0001_initial.py` for the custom user/auth foundation and `accounts/0002_vehicle_inventory.py` for vehicle inventory. If your local database was migrated against another version of the project, back it up and review its existing users before applying the custom user model migration: Django does not automatically transfer rows from the default auth user table.

Other API examples are `/api/accounts/`, `/api/activity/recent/`, `/api/oversight/managers/`, `/api/commission-rules/`, `/api/manager/reps/`, `/api/manager/sales/`, `/api/staff/imports/`, `/api/staff/reservations/`, `/api/rep/dashboard/`, `/api/rep/sales/`, `/api/rep/commissions/`, and `/api/staff/handovers/`. Representative sales and commission reads are scoped server-side to the authenticated Rep. External integrations and deployment configuration remain out of scope.
