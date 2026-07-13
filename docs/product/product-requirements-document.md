# Product Requirements Document

- Status: Approved baseline
- Product: Mad Mallard Platform
- Current release objective: Single-Business MVP
- Future target: Multi-tenant small-business platform

## 1. Executive summary

The current product must prove that one small business can use the platform end to end. A visitor discovers Mad Mallard Solutions, submits a service request or async message, receives notifications, creates a customer account, and views their activity. An administrator signs in through a separate protected admin experience and manages the resulting work.

Multi-tenancy, site building, CRM expansion, creator tools, AI, and billing remain later roadmap items.

## 2. Users

- Visitor
- Prospective customer
- Registered customer
- Business owner
- Business staff member
- Platform super administrator

## 3. Current MVP requirements

### PRD-R01 — Public presence

The platform shall serve a professional Mad Mallard Solutions public site over HTTPS.

### PRD-R02 — Customer intake

Visitors shall be able to submit a structured project request and initiate an async conversation.

### PRD-R03 — Conversation continuity

A customer shall receive a private conversation URL and be able to continue the conversation.

### PRD-R04 — Feedback

A customer may optionally rate or comment on a response without being forced to do so.

### PRD-R05 — Customer identity

A customer shall be able to register, verify email ownership, sign in, sign out, request a password reset, and update their profile.

### PRD-R06 — Customer dashboard

Authenticated customers shall have a dashboard showing their requests, conversations, and recent activity.

### PRD-R07 — Administration

A bootstrap administrator shall authenticate separately and access the approved dashboard, inbox, conversations, requests, leads, CRM, sites, and settings views.

### PRD-R08 — Notifications

Configured transactional notifications shall use AWS SES.

### PRD-R09 — Secrets

Bootstrap admin credentials and session secrets shall be loaded from AWS SSM Parameter Store rather than mutable local Terraform variables.

### PRD-R10 — Deployment

The application shall deploy reproducibly through Terraform, Docker, Caddy, and the existing AWS environment.

### PRD-R11 — Cost control

New AWS services must include a cost rationale and default to the lowest practical operating cost.

### PRD-R12 — Scope protection

No Sprint 2 or later capability shall be introduced into Sprint 1 merely because it is architecturally desirable.

## 4. Quality requirements

- All public traffic uses HTTPS.
- Customer and admin sessions are isolated.
- Passwords are hashed using an approved adaptive password hash.
- Secrets are excluded from source control and ordinary logs.
- The application remains deployable from the repository.
- Admin behavior must not regress during unrelated changes.
- Documentation, tests, and changelog remain synchronized.

## 5. Success criteria

Sprint 1 is successful when:

1. A new customer completes registration and verification.
2. The customer signs in and sees their dashboard.
3. The customer submits or views a request/conversation.
4. The administrator signs in and manages the interaction.
5. Email notification behavior works.
6. Deployment requires no undocumented manual server edits.
7. Regression tests protect the stable admin experience.
