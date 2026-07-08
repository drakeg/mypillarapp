# Sprint 1 — Customer Experience

## Sprint goal
A visitor can submit a service request, continue the conversation through a private request thread, track their requests, receive email notifications, and optionally leave feedback.

## In scope
1. Configurable contact/service request fields.
2. Service request creation with validation.
3. Private conversation thread for each request.
4. Customer-facing "My Requests" page.
5. Optional feedback on staff responses.
6. SES notification hooks already supported by the platform.
7. Tests covering request validation, conversation creation, customer request lookup, and feedback.

## Out of scope
- AI chat.
- Real-time WebSockets.
- File uploads.
- Billing/invoices.
- Admin portal expansion beyond existing inbox/reply capabilities.
- Multi-tenant productization.
- Any new paid AWS service.

Out-of-scope ideas go to Sprint 6+ backlog.

## Requirements and acceptance criteria

### R1 — Configurable request form
- The public form fields are defined in `site/solutions/form_config.py`.
- Required fields are enforced server-side.
- Select fields reject invalid values.

Acceptance: invalid submissions return a validation error; valid submissions create a request.

### R2 — Request creation
- A valid request creates a conversation.
- The first visitor message is stored.
- Request metadata is stored as lead JSON.
- Status starts as `new`.

Acceptance: a newly submitted request can be opened through its private conversation URL.

### R3 — Customer request tracking
- Visitors receive or can use a private `My Requests` link.
- The page lists all requests associated with the visitor email.
- Each request links to its conversation.

Acceptance: a customer with two requests sees both in `My Requests`.

### R4 — Messaging
- Visitor can reply from the private conversation page.
- Admin can reply from the existing admin conversation page.
- Status changes to `waiting_on_me` after visitor replies and `waiting_on_client` after staff replies.

Acceptance: replies persist and appear in chronological order.

### R5 — Feedback
- Visitor feedback is optional.
- Feedback can be saved from the conversation page or from email feedback links.
- Admin receives a notification when feedback is recorded if email is enabled.

Acceptance: feedback updates the conversation's last feedback fields.

## Automated test plan
Run:

```bash
python -m pytest tests
```

Tests cover:
- form validation
- request creation
- customer request dashboard lookup
- message status transitions
- feedback storage

## Manual QA checklist
- [ ] Open `https://pillar.madmallards.com/request`.
- [ ] Submit an invalid request and confirm validation appears.
- [ ] Submit a valid request.
- [ ] Confirm the success message includes conversation and My Requests links.
- [ ] Open the conversation link and send a visitor reply.
- [ ] Open `/admin/login`, then admin inbox.
- [ ] Reply as admin.
- [ ] Confirm the visitor receives an email when SES is enabled.
- [ ] Open the feedback link and submit feedback.
- [ ] Open the My Requests link and confirm the request appears.

## Definition of done
Sprint 1 is complete when all acceptance criteria pass, automated tests pass, and the manual QA checklist is complete on `pillar.madmallards.com`.
