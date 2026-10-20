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

Then open:

- http://localhost:8000/
- http://localhost:8000/sales

## Deployment

This app is ready to be deployed to public hosting providers.

### Render

Create a new Web Service and point it to this repository.

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
APP_URL=https://your-app-url.onrender.com
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
DEFAULT_REVIEW_LINK=https://www.google.com/maps
```

### Railway or other providers

Use the same runtime setup:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Core API endpoints

- `GET /health`
- `GET /api/dashboard`
- `GET /api/leads`
- `POST /api/leads`
- `POST /api/leads/{lead_id}/book`
- `POST /api/leads/{lead_id}/follow-up`
- `POST /api/leads/{lead_id}/review-request`
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
- `app/services/lead_service.py` — lead workflow logic
- `static/landing.html` — sales landing page
- `static/index.html` — live demo interface
- `docs/SALES_ONE_PAGER.md` — sales-focused summary
- `docs/OUTREACH_SCRIPT.md` — outreach message for HVAC owners
- `docs/DISCOVERY_CALL_SCRIPT.md` — discovery call script

## Notes

This repo intentionally prioritizes business utility and sales viability over deep internal complexity. It is structured to be a strong HVAC business-facing MVP that can later be expanded with live CRM integrations, Twilio automation, and real dispatch workflows.
