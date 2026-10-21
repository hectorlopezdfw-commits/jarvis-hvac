# Jarvis HVAC

Jarvis HVAC is a sales-ready lead conversion system for residential and commercial HVAC companies. It helps contractors answer inbound leads faster, book more jobs, recover missed calls, and request reviews automatically.

## Business value

Most HVAC companies lose revenue not because they lack demand, but because they miss or delay responses to leads.

Jarvis solves that by combining:

- instant lead response
- structured qualification
- appointment booking flow
- follow-up reminders
- review request automation
- performance dashboard for lead conversion

## Project status

This repo is now positioned as a real business-facing MVP, not just a technical demo.

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Copy `.env.example` to `.env` and set `DASHBOARD_PASSWORD` to a password you choose. That password unlocks the demo dashboard and the lead-reading API. Leave it unset and those views stay locked. `POST /api/leads` still accepts public lead submissions.

Then open:

- http://localhost:8000/
- http://localhost:8000/sales

## Lead storage

Leads are stored with SQLAlchemy. Set `DATABASE_URL` to use Postgres. When `DATABASE_URL` is unset, the app uses a SQLite file at `data/jarvis.db`. A `postgres://` or `postgresql://` URL is rewritten to the psycopg v3 driver automatically.

On startup the app inserts 10 fictional Dallas-area HVAC leads (555 phone numbers) if those seed ids are not already present. Restarting does not duplicate them. A fresh database therefore shows a non-zero dashboard.

Persistence caveats:

- Render free web services have an ephemeral filesystem. SQLite data survives only as long as that disk does. A redeploy, restart, or free-tier spin-down can wipe the file, and Render does not offer a persistent disk on the free web plan. After a wipe, the sample leads are seeded again. Leads submitted since the last restart are not restored.
- Point `DATABASE_URL` at Postgres when leads must survive restarts and redeploys. Render's free or trial Postgres expires and is deleted at the end of that window, so a database you mean to keep has to be on a plan that does not expire.

## Dashboard login

The demo dashboard and lead-reading API require one shared password from `DASHBOARD_PASSWORD`. Sign in from the demo page, or `POST /api/login` with `{"password": "..."}`. A matching password sets an HttpOnly session cookie. `POST /api/logout` clears it.

These routes require that cookie:

- `GET /api/dashboard`
- `GET /api/leads`
- `GET /api/leads/{lead_id}`
- `POST /api/leads/{lead_id}/book`
- `POST /api/leads/{lead_id}/follow-up`
- `POST /api/leads/{lead_id}/review-request`

These stay public:

- `GET /health`
- `GET /sales`
- `GET /` (the page shell; lead counts load only after login)
- `POST /api/leads`
- `POST /api/ai/qualify`
- `GET /api/sales-offer`
- `GET /api/sales-pitch`

If `DASHBOARD_PASSWORD` is unset or blank, login returns 503 and the protected routes return 401. No password is stored in the repo. Do not commit a real password.

Phone numbers are stored as E.164. A US 10-digit number becomes `+1XXXXXXXXXX`. An 11-digit number that starts with `1` becomes `+1XXXXXXXXXX` as well, which is what Twilio expects.

## Deployment

The live app is [https://jarvis-hvac.onrender.com](https://jarvis-hvac.onrender.com). Render redeploys this repo from `main`.

### Render

`render.yaml` describes the web service.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```bash
APP_NAME=Jarvis HVAC
APP_ENV=production
PORT=10000
BUSINESS_NAME=Your HVAC Company
APP_URL=https://jarvis-hvac.onrender.com
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
DEFAULT_REVIEW_LINK=https://www.google.com/maps
DATABASE_URL=
DASHBOARD_PASSWORD=
```

Set `DASHBOARD_PASSWORD` in the Render dashboard (Environment). `render.yaml` declares it with `sync: false`, so blueprint deploys do not overwrite the value and the password is never committed. The dashboard and lead list stay locked until that variable is set.

`DATABASE_URL` is also `sync: false`. Leave it empty to use SQLite on the instance disk, or paste a Postgres connection string. Read the persistence caveats above before relying on SQLite on the free plan.

### Railway or other providers

Use the same runtime setup:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Core API endpoints

- `GET /health`
- `POST /api/login`
- `POST /api/logout`
- `GET /api/session`
- `GET /api/dashboard` (login required)
- `GET /api/leads` (login required)
- `GET /api/leads/{lead_id}` (login required)
- `POST /api/leads` (public)
- `POST /api/leads/{lead_id}/book` (login required)
- `POST /api/leads/{lead_id}/follow-up` (login required)
- `POST /api/leads/{lead_id}/review-request` (login required)
- `POST /api/ai/qualify`
- `GET /api/sales-offer`
- `GET /api/sales-pitch`

## Sales story

Jarvis HVAC is designed for residential and commercial HVAC businesses that want to:

- respond faster to leads
- capture more emergency calls
- reduce missed opportunities
- allocate follow-up automatically
- collect more reviews

## Offer

Starter package:

- $2,500 setup
- $800–$1,500/month retainer

Includes:

- instant lead response
- AI qualification
- appointment booking
- follow-up reminders
- review requests
- dashboard

## Sales pitch

“We help HVAC companies stop missing leads and book more jobs by responding instantly, qualifying service requests, booking appointments, following up with unbooked leads, and collecting Google reviews automatically.”

## Files of interest

- `app/main.py` — app entrypoint and public routes
- `app/api/routes.py` — API routes
- `app/auth.py` — dashboard password check and session cookie
- `app/db/store.py` — SQL lead store (`DATABASE_URL`, SQLite fallback)
- `app/db/seed.py` — idempotent sample leads
- `app/services/lead_service.py` — lead workflow logic
- `static/landing.html` — sales landing page
- `static/index.html` — live demo interface
- `docs/SALES_ONE_PAGER.md` — sales-focused summary
- `docs/OUTREACH_SCRIPT.md` — outreach message for HVAC owners
- `docs/DISCOVERY_CALL_SCRIPT.md` — discovery call script

## Notes

This repo intentionally prioritizes business utility and sales viability over deep internal complexity. It is structured to be a strong HVAC business-facing MVP that can later be expanded with live CRM integrations, Twilio automation, and real dispatch workflows.
