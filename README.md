# Jarvis HVAC

Jarvis HVAC is a lead-conversion engine for residential and commercial HVAC companies. It is designed to answer new leads immediately, qualify service requests, book appointments, trigger follow-up reminders, and collect reviews after a completed job.

This repository contains the business-facing MVP for an AI-powered HVAC system built to sell to local HVAC contractors.

## Features in this version

- Website lead intake and call/text lead support
- AI-style qualification logic for HVAC urgency, type, and property type
- Lead priority scoring and response recommendations
- Follow-up automation flow for unbooked leads
- Review request generation for completed jobs
- Sales offer and pitch helpers for HVAC clients
- Dashboard summary for lead conversion performance
- Static demo frontend for testing the workflow locally

## Local development

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   ```bash
   cp .env.example .env
   ```

4. Run the app:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. Open the demo:
   - http://localhost:8000/
   - http://localhost:8000/sales

## Main API routes

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

## Business use case

This system is designed to help HVAC companies:

- answer every incoming lead quickly
- recover missed calls and texts
- record and prioritize emergency work
- reduce manual follow-up burden
- increase booked service calls
- request Google reviews after a completed job

## Notes

This version intentionally prioritizes a sellable business workflow over deep custom infrastructure. It is built to be a strong MVP for HVAC client acquisition and can later be expanded to real CRM integrations, active Twilio SMS, live call handling, and custom automations.
