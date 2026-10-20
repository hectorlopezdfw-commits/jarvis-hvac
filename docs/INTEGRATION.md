# Consolidation record — October 20, 2026

## Sources

- Original implementation: https://github.com/hectorlopezdfw-commits/jarvis-hvac
- Source commit inspected: `a69ae6719c0f2eb4f2eb019cb110a20f71b24954`.
- User-supplied Copilot history: https://github.com/copilot/share/822a031c-00c0-8e62-8950-8c0c440e6039
- Local Texas HVAC developer pack, corrected after comparison with the 41-page PDF.
- Local `hvac_core` controls: jobs, proposals, independent holds, invoice replay,
  payment records, persisted memberships and session gateway.

The Copilot history establishes product direction: a residential/commercial HVAC
lead-conversion business, with intake, qualification, missed-call recovery, booking,
follow-up, review requests, reporting and a sales-facing presence. It is historical
context, not fresh authorization to contact customers, spend or deploy.

## Implementation decisions

Continue the existing FastAPI app and static interface rather than replacing it
with another unrelated system. Retain its routes where possible. Replace duplicate
package-level implementations with the authoritative services. Replace volatile
lead dictionaries with tenant-scoped SQLite records and local audit events. Integrate
the control library inside this repo so the project runs without importing files
from the parent pack.

Booking is now honestly labeled `booking_requested`; datetime requires a future
explicit timezone. No capacity engine or scheduler is connected. Follow-up remains
a draft and no longer marks a customer contacted automatically. Review drafts need
recorded completion and no longer overwrite the lifecycle as if a review was sent.
Messages are draft-only independent of configured transport credentials.

Completed lead handoff maps deterministically to one local job. Finance controls
require exact proposal approval, separate staff identities, no active independent
holds and unchanged job/evidence versions. A payment is a record, not a charge.

The read-only owner assistant uses the existing authorized key. It has no tool
permissions or credentials in its prompt. Only per-tenant/staff recent memory and
sanitized pipeline descriptions/counts are used. Memory is locally retained without
a pruning/deletion UI; production retention remains open. It is not a deployed
CEO/CFO/multi-agent runtime. Voice, retrieval over uploaded manuals, automatic
missed-call capture and recurring outreach are not implemented here.

## Blueprint alignment

The blueprint and machine-readable contracts are copied under `docs/blueprint`.
Their four technical corrections remain: canonical closeout event naming,
reviewer-specific hold release, executive tool-list alignment and acquisition
cost deducted once. They remain specifications; their presence does not mean
all twelve agent roles, integrations or compliance rules are running.

## Validation record

The integrated suite tests the original lead flow and the new handoff/control
boundary. A synthetic lead can move from intake through booking request, recorded
completion, one job, proposal, separate review, one replay-safe invoice and a
recorded payment. No test sends messages or invokes a payment processor.

Desktop browser verification covers the actual lead desk, role session, successful
live read-only AI answer and completed-lead handoff into operations. Mobile browser
QA and real third-party integration tests remain unperformed. Dependencies were
retained from the original repo with an explicit HTTP client compatibility pin;
security/version modernization is a separate pre-production task.
