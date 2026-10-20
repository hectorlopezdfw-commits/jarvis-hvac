# Jarvis HVAC — unified local pilot

This continues the original Jarvis HVAC GitHub project. The lead-conversion app
is the main experience; completed leads connect to the approval and finance
controls developed in the companion Texas HVAC developer pack.

## Run

Requires Python 3.10+ (verified with 3.12):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m app.seed_demo
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
```

Open http://127.0.0.1:8766 and start the Office owner pilot session. The optional
seed command adds three labeled synthetic inquiries only when the pipeline is
empty. Local data persists at `data/jarvis.sqlite`; `JARVIS_DB` overrides the path.
Stop the server with Ctrl-C. Keep the database private; it contains local records,
sessions, approvals, audit events and assistant conversation memory.

The authorized existing key is read from the parent workspace `.env.local` without
copying it. A standalone checkout can use environment variables or its own ignored
`.env`; `OPENAI_MODEL` overrides the original repo model default. Never add keys to
Git, frontend code or Docker images. The key is used only by the Ask Jarvis endpoint.

## One connected experience

- **Lead desk:** capture residential/commercial inquiries; original rule-based
  qualification; priority and source tracking; booking requests; explicit recorded
  contact/completion; follow-up and review drafts.
- **Ask Jarvis:** real OpenAI-backed, read-only owner assistant with the last three
  exchanges scoped to tenant/staff. Sends workspace counts and up to 30 sanitized
  lead descriptions/states plus the question/history. Never executes tools.
- **Operations & finance:** hand off a completed lead once; attach synthetic evidence;
  draft invoice costs/tax in integer cents; require a different finance approver;
  enforce independent quality/compliance/finance holds, source freshness and expiry;
  execute one local invoice; record partial/full payments with reference deduplication.
- **Build roadmap:** separates implemented local behavior, live-customer gates and
  the broader operating-system expansion.
- **Original sales page:** retained at `/sales` as historical product collateral.
  Its pricing and product claims have not been validated as current/live capabilities.

## Pilot roles

The staff selector is simulated local identity, not production authentication.
Sessions are hashed at rest, HttpOnly and SameSite=Strict, expire after one hour,
and are revoked when switching staff or signing out. Persisted membership determines
permissions; request bodies cannot select a tenant or role. Membership administration
is an internal library, not a public endpoint. All current staff belong to one fixed
pilot tenant; persistence and controls also have tests for separate tenant scopes.

- Office owner: lead workflow, completed-lead handoff, closeout fixture, invoice draft/execution, assistant.
- Dispatcher: lead workflow; cannot perform finance operations.
- Invoice preparer: invoice proposals and approved invoice execution.
- Finance reviewer: separate approval, finance holds and payment recording.
- Quality/compliance reviewer: place and release only their own category of hold.

A scheduled request is **not** an authoritative appointment. A message draft is
**not** a delivery. Recorded payment is **not** a processor settlement. Absent holds
are **not** positive technical/compliance clearance. No real messages are sent even
if Twilio credentials happen to exist. Keyword-based hazard detection is an incomplete
triage aid, not a safety system; applicable scripts and routing require expert review.

## Verification

```sh
.venv/bin/python -m pytest -q
```

Integration coverage includes lead capture, honest draft state, appointment time
validation, completion/review gates, hazard blocking, linked lead-to-payment flow,
independent approval, invoice replay, tenant persistence, logout/revocation, origin/
host checks and read-only AI memory using a mocked model. Live synthetic assistant
request and desktop browser flow were also verified separately; tests do not call
paid APIs. Additional control tests are retained from the original local core.

## What still blocks production

The app refuses `APP_ENV=production`. The original Render config is retained for
reference and will intentionally fail this gate; do not use it to publish the pilot.
The host allowlist permits loopback plus the testing host only. No public deployment,
customer outreach, GitHub merge, SMS delivery or payment processing is implied.

Before live use: verified identity/MFA; tenant/branch/resource grants; database-enforced
isolation; consent/opt-out/suppression and reviewed safety/credential/jurisdiction
rules; real scheduler capacity and confirmation; transport delivery/unknown-outcome
reconciliation; positive QA/compliance sign-off; deterministic reviewed tax/price
rules; accounting and settlements; backups/restore, audit retention and monitoring.
The pilot API is not hardened against hostile concurrent or oversized streaming
traffic. SQLite service file access remains a trusted boundary. No invoice may be
created against a real account with these incomplete gates.

See [the integration record](docs/INTEGRATION.md), [the copied blueprint](docs/blueprint/BLUEPRINT.md)
and [the original README](docs/ORIGINAL_README.md) for provenance and remaining scope.

## Supervised pilot simulation

Open **Supervised pilot** after selecting a lead. Use **Dispatcher** to record
synthetic service-SMS permission with evidence and prepare the exact message or
booking packet. Switch to **Office owner** to review and approve. The requester
cannot approve their own packet. Execution rechecks expiry, current lead state,
permission version and simulated calendar capacity inside a database transaction.

Booking requests now require simulated provider confirmation before the UI can
record service completion. The result is explicitly `booking_confirmed_simulated`,
never a real confirmed appointment. The simulated calendar models one technician
and one-hour visits; cancellation/rescheduling and real capacity are not modeled.

You can test normal acceptance, rejection or a timeout after provider acceptance.
Unknown outcomes block replay until reconciliation reads the synthetic provider
receipt. Replay returns one receipt and does not reserve a second visit. Opt-out
cancels unexecuted messages across leads for the same phone; an already accepted
unknown action stays uncertain until reconciled, without sending again. Recorded
permission is pilot evidence, not a legal determination or a complete consent
system. Marketing purposes, provider opt-out webhooks and contact normalization
still require scoped implementation.

The suite now has **34 passing tests**. Metrics distinguish simulated outcomes
from real messages/appointments (zero); staff time saved remains unknown. Identity
is still simulated. Google Calendar and Twilio are suggested future adapters,
not connected accounts. No provider account, phone number or paid plan was created.
