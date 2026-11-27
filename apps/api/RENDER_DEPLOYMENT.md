# Deploying the Django API on Render

Create a **Python Web Service** for this repository with root directory `apps/api`.

- Build command: `pip install -r requirements.txt && python manage.py collectstatic --no-input`
- Pre-deploy command: `python manage.py migrate` (use Render's pre-deploy command where available so migrations finish before the new instance receives traffic)
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health check path: `/healthz`

The build collects Django static files into `apps/api/staticfiles`; WhiteNoise serves them from the application. Uploaded files are not build artifacts and must not be committed. The API uses host-only CSRF and session cookies; do not configure `CSRF_COOKIE_DOMAIN` to `.onrender.com`.

## Environment variables

Set these in the Render service environment. Use the **internal** connection values shown by the Render PostgreSQL database; do not copy credentials into source control.

| Variable | Value |
| --- | --- |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | A newly generated, private Django secret |
| `DJANGO_ALLOWED_HOSTS` | Custom API hostnames, comma separated, without schemes |
| `POSTGRES_DB` | Render database name |
| `POSTGRES_USER` | Render database user |
| `POSTGRES_PASSWORD` | Render database password |
| `POSTGRES_HOST` | Render PostgreSQL internal hostname |
| `POSTGRES_PORT` | Render PostgreSQL internal port |
| `CORS_ALLOWED_ORIGINS` | Exact HTTPS origin(s) of the web app, comma separated |
| `CSRF_TRUSTED_ORIGINS` | Exact HTTPS origin(s) of the web app, comma separated |
| `ACCOUNT_PORTAL_URL` | `https://ssp-frontend-xrli.onrender.com` |
| `EMAIL_BACKEND` | `accounts.email_backend.BrevoEmailBackend` |
| `BREVO_API_KEY` | Private Brevo API key; set only in the backend Render service environment |
| `BREVO_TIMEOUT_SECONDS` | `10` (or another positive timeout in seconds) |
| `DEFAULT_FROM_EMAIL` | A sender name and address verified in Brevo, for example `SSP Motor Trading <no-reply@your-verified-domain.example>` |

The app retains the `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` interface. Render supplies `PORT` to the start command. Production uses Brevo's HTTPS Transactional Email API, so Render's blocked SMTP ports are not involved. Set the four email variables above on the **backend API service**. In the Brevo dashboard, generate an API key and verify the sender domain/address used by `DEFAULT_FROM_EMAIL`; keep the key out of GitHub, frontend variables, logs, and build arguments. `EMAIL_BACKEND` defaults to Django's console backend in development and the Brevo backend in production. `BREVO_TIMEOUT_SECONDS` defaults to `10`. Company details can be supplied through `COMPANY_LOCATION`, `COMPANY_PHONE`, and `COMPANY_EMAIL`. Financing defaults can be overridden with `NEXT_PUBLIC_FINANCE_36M_PER_100K`, `NEXT_PUBLIC_FINANCE_60M_PER_100K`, `NEXT_PUBLIC_FINANCE_72M_PER_100K`, and `NEXT_PUBLIC_FINANCE_OD_PER_100K`.

In Render, open the backend web service, choose **Environment**, and add:

```text
EMAIL_BACKEND=accounts.email_backend.BrevoEmailBackend
BREVO_API_KEY=<paste the private Brevo API key>
BREVO_TIMEOUT_SECONDS=10
DEFAULT_FROM_EMAIL=<verified sender name and email>
ACCOUNT_PORTAL_URL=https://ssp-frontend-xrli.onrender.com
```

Save and let Render restart the backend. Do not add `BREVO_API_KEY` to GitHub, the frontend service, or any `NEXT_PUBLIC_*` variable. The same backend handles employee and Admin invitations, secure password setup and resets, appointment confirmations, and the existing confirmation retry. The invitation transaction still rolls back if Brevo rejects a message or delivery fails; ambiguous timeouts are not automatically retried because Brevo may already have accepted the email.

Render's `RENDER_EXTERNAL_HOSTNAME` is appended automatically to `DJANGO_ALLOWED_HOSTS` when present. Keep custom API domains in `DJANGO_ALLOWED_HOSTS`; the Render hostname addition does not replace them. Rejected hostnames are written by the `django.security.DisallowedHost` logger to service logs without logging request query strings or credentials.

## HTTPS and cookies

With `DJANGO_DEBUG=0`, Django enables SSL redirects and secure session/CSRF cookies. Render terminates HTTPS at its proxy; Django trusts Render's `X-Forwarded-Proto: https` header so requests already served over HTTPS are not redirected repeatedly. The Next.js frontend proxies browser `/api/...` calls to Django, forwarding the browser Origin, Referer, CSRF header and cookies; Django's response cookies are returned host-only on the frontend origin. Set the frontend's exact HTTPS origin in `CSRF_TRUSTED_ORIGINS`. Keep CORS origins explicit for integrations that still call Django directly.

## Next.js frontend service and authentication proxy

The frontend must run as a **Node Web Service**, not a Static Site. Set root directory `apps/web`, build command `npm ci --include=dev && npm run build`, and start command `npm run start -- --hostname 0.0.0.0 --port $PORT`. Add this server-only variable to the frontend service:

| Variable | Value |
| --- | --- |
| `API_UPSTREAM_URL` | `https://<backend-render-hostname>` |

Remove `NEXT_PUBLIC_API_BASE_URL` from the frontend service; the browser uses same-origin API routes and must never receive the upstream URL. Do not put database or Django secrets in the frontend service. Keep `CSRF_TRUSTED_ORIGINS` on the backend set to the exact frontend URL (for example `https://ssp-frontend-xrli.onrender.com`). `CORS_ALLOWED_ORIGINS` may remain set to that exact origin; do not use wildcard origins. Never configure a shared `.onrender.com` cookie domain.

## Free instance database initialization

Render Free web services do not provide Dashboard Shell access or pre-deploy commands. The build command must not run migrations. If both services remain Free, a practical single-instance fallback is to run migrations in the backend start command before Gunicorn:

```sh
python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Migrations are designed to be repeatable, but this starts the service only after they finish and can delay/cause a failed restart if a migration fails. Use a single backend instance; review migration lock/runtime impact and take a database backup before schema changes. For a production-grade release, upgrade the API service to a plan with a pre-deploy command and run `python manage.py migrate --noinput` there before traffic switches.

Free services also lack a safe server shell for `createsuperuser` or database inspection. Do not add a public bootstrap endpoint or a default password. Temporarily upgrade the API service to enable Shell access, then verify account existence without printing personal data, for example:

```sh
python manage.py shell -c "from accounts.models import User; print({'count': User.objects.count(), 'roles': sorted(set(User.objects.values_list('role', flat=True)))})"
```

If no production Admin exists, run `python manage.py createsuperuser` through that authenticated Shell session and enter a unique, strong password interactively. Confirm the resulting role and sign-in through the frontend. Local development or test accounts are not production accounts. Do not run account creation against a local/test database by mistake; first confirm the Render service's internal `POSTGRES_*` configuration is attached. Free services are intended for evaluation rather than production workloads; persistent database and media backups remain necessary.

## Uploaded media persistence

Render's service filesystem is ephemeral unless a persistent disk is attached. Attach a persistent disk mounted at `/var/data` and set all three paths below to directories on that disk to retain vehicle photos and private payment/handover evidence across deploys:

```text
MEDIA_ROOT=/var/data/media
PRIVATE_PAYMENT_EVIDENCE_ROOT=/var/data/private_payment_evidence
PRIVATE_HANDOVER_EVIDENCE_ROOT=/var/data/private_handover_evidence
```

Private evidence remains outside the public media directory and is served only through the existing permission-checked API. Without the disk and these variables, uploaded files can be lost when Render replaces the instance. Back up the disk separately; a disk mounted by one instance also needs a deliberate storage design before scaling to multiple instances.
