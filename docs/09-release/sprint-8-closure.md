# Sprint 8 Closure Record — Billing and Commercialization

- Status: Closed at repository/CI level
- Sprint: Sprint 8 — Billing and Commercialization
- Epic: EP-011 — Billing and Commercialization
- Protected predecessor baseline: Sprint 7 at `ddddd495795d3c3b9de84191acb2cf9aa48167e8`
- S8-T10 merged baseline: `e975db9496b23270a17e6c639a85d466b3ff4963`
- Sprint 8 repository/CI closure baseline: `0751ac4c5cd3049473bada3c620052dbdad9ec88`

## Objective result

Sprint 8 delivers tenant-safe commercialization foundations without making payment-provider state authoritative for application access.

The implementation includes:

- canonical tenant billing ownership and prohibited payment-data boundaries;
- tenant-owned plans with deterministic boolean/quota entitlements;
- application-owned subscription lifecycle and transition history;
- provider-neutral billing integration and a bounded Stripe adapter;
- authorized Stripe customer/checkout onboarding with allow-listed return URLs;
- authenticated, idempotent, replay-safe webhook reconciliation;
- tenant-scoped invoice/payment-history metadata without raw payment credentials;
- server-side site and AI commercialization enforcement;
- owner/admin billing administration and onboarding helpers;
- billing maintenance mode, secret-free operational diagnostics, and safe rejected-event retry;
- dedicated Sprint 8 regression gating in CI.

## Safety invariants preserved

Repository evidence verifies that:

1. every billing plan, assignment, subscription, checkout, and invoice is tenant scoped;
2. provider IDs are opaque references and never replace tenant authorization;
3. raw card, CVC/CVV, bank-account, routing, payment-method payloads, and provider secrets are excluded from application persistence;
4. legacy quote/catalog/service pricing cannot directly authorize a charge or entitlement;
5. checkout responses do not activate application access before verified reconciliation;
6. webhook signatures are verified before processing, duplicate event IDs are idempotent, and stale/out-of-order events cannot overwrite newer state;
7. invoice ownership resolves through application-owned subscription records rather than untrusted provider metadata;
8. commercial quotas are enforced server-side while unassigned/internal tenants retain an explicit compatibility policy;
9. provider writes can be disabled with `MADMALLARD_BILLING_MAINTENANCE` without deleting tenant data;
10. CI performs no real chargeable provider actions.

## Regression gates

Sprint 8 adds:

`make test-sprint8`

and the Django GitHub Actions workflow enforces it alongside:

- `make test`;
- `make test-sprint2`;
- `make test-sprint3`;
- `make test-sprint4`;
- `make test-sprint5`;
- `make test-sprint6`;
- `make test-sprint7`.

All Stripe/provider behavior remains fake/mock based in repository CI. CI success does not constitute production payment-provider verification.

## Local verification evidence

S8-T10 focused billing operations/recovery verification passed 73 tests.

S8-T11 closure verification passed on the repository's Python 3.15 GitHub Actions baseline: badge validation, the full regression suite, focused Sprint 2–8 suites, Docker image build, non-root runtime verification, Docker Compose configuration validation, and Terraform validation all completed successfully.

The macOS system Python 3.9 is not valid closure evidence for this repository because several protected modules use syntax supported by the configured Python 3.15 runtime.

## Rollback evidence

If Sprint 8 provider behavior must be contained or rolled back:

1. set `MADMALLARD_BILLING_MAINTENANCE=true` to stop provider write operations before transport;
2. preserve signed webhook processing so already-created provider state can continue to reconcile;
3. inspect tenant-safe billing operational summaries without copying secrets or raw payloads into diagnostics;
4. restore the previous application image/revision when application rollback is required;
5. retain billing/subscription/invoice audit records rather than deleting tenant history;
6. verify tenant plan assignments, subscription state, invoice state, and non-billing workflows before disabling maintenance mode;
7. canceled/past-due tenants retain their data and recover only through deterministic application/provider reconciliation rules.

## Known limitations

- repository CI uses fakes/mocks and does not validate production Stripe credentials, account configuration, tax behavior, or live-money movement;
- marketplace payouts, split payments, connected-account payouts, refunds/credits, and cryptocurrency remain out of scope;
- no raw payment credentials or card/bank data are stored, so payment-method management remains provider-hosted;
- plan enforcement currently covers selected product seams (site count and AI feature/rolling quota), not every possible future product limit;
- production webhook endpoint deployment and live Stripe redelivery remain deployment-time verification;
- billing UI surfaces can continue to evolve on top of the S8-T09 administration facade.

## Exit criteria assessment

1. Tenant-safe plans/subscriptions/invoices exist — met.
2. Stripe integration is bounded, secret-safe, and replay-safe — met at repository/CI level.
3. Entitlements/quotas are deterministic and server-side — met.
4. Commercial onboarding does not reinterpret legacy tenant data — met.
5. Existing non-billing product workflows remain compatibility-protected — met.
6. Full protected regression evidence is green — met.
7. Release/rollback evidence and known limitations are recorded — met.

## Finalization rule

S8-T11 / PR #117 merged with all required repository/CI validation green at `0751ac4c5cd3049473bada3c620052dbdad9ec88`. This commit is the final Sprint 8 repository/CI closure baseline.
