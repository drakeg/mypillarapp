# S7-T02 AI Settings and Usage-Control Foundation

## Purpose

S7-T02 adds tenant-owned AI enablement and bounded usage-control configuration on top of the S7-T01 authorization boundary.

This task still introduces no model-provider calls, provider credentials, billing, paid credits, subscriptions, invoices, or autonomous actions.

## Tenant settings

Each organization may have one AI settings record containing:

- explicit enabled/disabled state;
- maximum input units per request;
- maximum output units per request;
- rolling usage limit units.

Organizations without a persisted settings record are treated as AI-disabled and receive conservative default limits.

## Authorization

Settings changes require:

- active application user;
- active organization;
- explicit active organization membership;
- owner or admin membership role.

Staff and viewer memberships may not change AI enablement or raise usage limits.

Cross-tenant changes require an explicit membership in the target organization. Home-organization identity does not grant implicit access.

## Boundaries

Configured limits are bounded to prevent unreasonably large values:

- max input units: 1 through 50,000;
- max output units: 1 through 10,000;
- rolling usage limit: 1 through 5,000,000.

The units are intentionally provider-neutral. S7-T03 may map provider token/unit accounting into this interface without changing tenant ownership or authorization.

## Usage admission check

Before future provider execution, `require_usage_allowed()` requires:

1. S7-T01 tenant authorization succeeds;
2. AI is enabled for the organization;
3. requested input is within the configured request limit;
4. requested output is within the configured request limit;
5. current rolling usage plus requested input/output does not exceed the configured rolling limit.

Invalid, negative, disabled, inactive-tenant, revoked-membership, and over-limit requests fail closed.

## No billing semantics

These usage controls are operational safety/cost controls only.

They do not represent:

- paid credits;
- subscription entitlements;
- pricing tiers;
- invoices;
- overage billing;
- payment-provider balances.

Billing remains Sprint 8 scope.

## Regression evidence

`tests/test_sprint7_ai_settings.py` verifies:

- AI is disabled by default;
- owner/admin configuration access;
- staff/viewer configuration denial;
- bounded configuration values;
- request input/output/rolling limit enforcement;
- cross-tenant denial without explicit membership;
- inactive tenant failure;
- staff may pass usage admission only after an authorized owner/admin enables AI.

## Handoff to S7-T03

S7-T03 may add provider-neutral execution and append-only usage accounting. Provider execution must call the S7-T01/S7-T02 authorization and admission boundaries before any network request is made.
