# Jarvis HVAC

Jarvis HVAC is a lead-conversion engine for residential and commercial HVAC companies. It is designed to answer new leads instantly, qualify service requests, book appointments, trigger follow-up reminders, and collect reviews after a completed job.

This repo is the MVP for an AI-powered HVAC business operating system that is built to sell to local HVAC contractors.

## Why this exists

The core problem in HVAC sales is not marketing alone. It is lead response speed and execution:

- missed calls lose business
- slow text responses lose urgency
- no follow-up kills conversion
- poor review automation hurts reputation
- no dashboard makes it hard to measure performance

Jarvis solves those issues with a structured workflow designed for HVAC leads.

## What is included in the MVP

- Lead intake API for website/form leads and calls
- AI lead qualification engine for residential vs commercial requests
- Booking workflow for service calls and estimates
- Priority scoring for emergency and high-value leads
- Follow-up automation hooks and reminder logic
- Review request workflow after service completion
- Simple dashboard for leads and conversion health
- Static web UI demo for testing the lead flow quickly

## Stack

- Python 3.11+
- FastAPI
- Pydantic
- Uvicorn
- OpenAI API integration (optional)
- Built-in fallback logic when no API key is configured

## Project structure

- `app/` — FastAPI app and core logic
- `static/` — simple frontend demo for the lead flow
- `tests/` — validator tests for lead qualification

## Local development

1. Create a virtual environment
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment
   ```bash
   cp .env.example .env
   ```

4. Run the API
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. Open the demo UI
   - http://localhost:8000

## Example API endpoints

- `GET /health`
- `GET /api/dashboard`
- `POST /api/leads`
- `POST /api/leads/{lead_id}/book`
- `POST /api/ai/qualify`

## Example lead payload

```json
{
  "customer_name": "Alicia Johnson",
  "phone": "(214) 555-0111",
  "email": "alicia@example.com",
  "service_type": "heating",
  "property_type": "residential",
  "emergency": true,
  "address": "1801 Elm Street, Dallas, TX",
  "preferred_date": "2026-10-21T15:00:00",
  "source": "website",
  "notes": "No heat in the house. Furnace not running."
}
```

## Business outcomes

This system is designed to help a local HVAC company: 

- respond to every inquiry within minutes
- capture more service calls from missed calls and texts
- avoid missing emergency calls during peak winter demand
- convert more leads into booked jobs
- follow up with estimates and reminders automatically
- collect Google reviews after each completed job

## Notes

This MVP intentionally prioritizes speed and business utility over complexity. It is built as a sellable HVAC business system that can later be expanded with live call handling, CRM integrations, Twilio SMS, or custom LLM orchestration.

## License

MIT
