# Deploying the Django API on Render

Create a **Python Web Service** for this repository with root directory `apps/api`.

- Build command: `pip install -r requirements.txt && python manage.py collectstatic --no-input`
- Pre-deploy command: `python manage.py migrate` (use Render's pre-deploy command where available so migrations finish before the new instance receives traffic)
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health check path: `/healthz`

The build collects Django static files into `apps/api/staticfiles`; WhiteNoise serves them from the application. Uploaded files are not build artifacts and must not be committed.

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
| `ACCOUNT_PORTAL_URL` | Public web app URL used in account emails |

The app retains the `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` interface. Render supplies `PORT` to the start command. Configure working SMTP values for `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL`; production defaults to Django's SMTP backend. `EMAIL_BACKEND` can be set when intentionally using another backend. Company details can be supplied through `COMPANY_LOCATION`, `COMPANY_PHONE`, and `COMPANY_EMAIL`. Financing defaults can be overridden with `NEXT_PUBLIC_FINANCE_36M_PER_100K`, `NEXT_PUBLIC_FINANCE_60M_PER_100K`, `NEXT_PUBLIC_FINANCE_72M_PER_100K`, and `NEXT_PUBLIC_FINANCE_OD_PER_100K`.

Render's `RENDER_EXTERNAL_HOSTNAME` is appended automatically to `DJANGO_ALLOWED_HOSTS` when present. Keep custom API domains in `DJANGO_ALLOWED_HOSTS`; the Render hostname addition does not replace them. Rejected hostnames are written by the `django.security.DisallowedHost` logger to service logs without logging request query strings or credentials.

## HTTPS and cookies

With `DJANGO_DEBUG=0`, Django enables SSL redirects and secure session/CSRF cookies. Render terminates HTTPS at its proxy; Django trusts Render's `X-Forwarded-Proto: https` header so requests already served over HTTPS are not redirected repeatedly. Configure the frontend and API on compatible same-site domains for the existing `SameSite=Lax` session cookies, and list the frontend's exact origin in both CORS and CSRF settings.

## Uploaded media persistence

Render's service filesystem is ephemeral unless a persistent disk is attached. Attach a persistent disk mounted at `/var/data` and set all three paths below to directories on that disk to retain vehicle photos and private payment/handover evidence across deploys:

```text
MEDIA_ROOT=/var/data/media
PRIVATE_PAYMENT_EVIDENCE_ROOT=/var/data/private_payment_evidence
PRIVATE_HANDOVER_EVIDENCE_ROOT=/var/data/private_handover_evidence
```

Private evidence remains outside the public media directory and is served only through the existing permission-checked API. Without the disk and these variables, uploaded files can be lost when Render replaces the instance. Back up the disk separately; a disk mounted by one instance also needs a deliberate storage design before scaling to multiple instances.
