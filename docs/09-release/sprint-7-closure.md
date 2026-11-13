# Sprint 7 Closure Record — AI Assistance

- Status: Repository/CI closure candidate
- Sprint: Sprint 7 — AI Assistance
- Epic: EP-010 — AI Assistance
- Protected predecessor baseline: Sprint 6 at `ae3c1ba9f0a6e4959c69f617fec0d4ef3f368a35`
- S7-T09 merged baseline: `3f470840f3fec987314c256d18f4851e5c04cf34`

## Objective result

Sprint 7 delivers additive, tenant-safe AI assistance for staff and creator workflows without granting autonomous application authority to generated output.

The implementation now includes:

- canonical tenant/site-aware AI authorization and context boundaries;
- tenant-owned enablement and bounded usage controls;
- provider-neutral execution with explicit timeout/error handling;
- human-reviewed drafting assistance;
- authorized, non-authoritative summaries with source traceability;
- suggested customer replies that exclude internal-only content and require a separate human send action;
- tenant-safe lexical knowledge search with source references and no arbitrary external crawling;
- centralized AI capability RBAC and administration;
- append-only usage/audit metadata with explicit operational outcomes;
- an AI-only kill switch and content-free operational diagnostics;
- a focused Sprint 7 regression target and CI gate.

## Safety invariants preserved

Repository evidence verifies that:

1. authorization occurs before tenant/model context is assembled;
2. cross-tenant and cross-site record references fail closed;
3. customer-facing reply suggestions exclude internal-only conversation content;
4. generated drafts, summaries, and reply suggestions are not auto-saved, auto-sent, or auto-published;
5. provider failures, timeouts, disabled AI, quota limits, and the operational kill switch do not replace deterministic application workflows;
6. provider secrets, prompts, generated responses, session tokens, and unrelated tenant content are not persisted in usage metadata;
7. AI usage/configuration administration remains tenant-scoped and least privilege;
8. arbitrary public-web crawling, shared cross-tenant embeddings, and shared tenant memory remain out of scope.

## Regression gates

Sprint 7 adds:

`make test-sprint7`

and the Django GitHub Actions workflow now enforces it alongside:

- `make test`;
- `make test-sprint2`;
- `make test-sprint3`;
- `make test-sprint4`;
- `make test-sprint5`;
- `make test-sprint6`.

All provider behavior remains fake/mock based in repository CI. CI success does not constitute production-provider verification.

## Local verification evidence

Before this closure candidate:

- S7-T08 focused regression: 28 tests passed;
- S7-T08 full Python 3.15 regression: 457 tests passed;
- S7-T09 focused regression: 19 tests passed;
- S7-T09 full Python 3.15 regression: 462 tests passed;
- local Docker Compose application returned HTTP 200 at `http://127.0.0.1:8017`.

S7-T10 reruns the full and focused Sprint 7 gates from the closure branch before merge.

## Rollback evidence

If Sprint 7 must be disabled or rolled back:

1. set `MADMALLARD_AI_KILL_SWITCH=true` to stop provider execution before any provider call;
2. preserve deterministic CRM, Portal, Site Builder, Creator, messaging, and authentication workflows;
3. restore the previous application image/revision if application rollback is required;
4. preserve the expanded `ai_usage_events` ledger rather than copying prompts or responses into diagnostics;
5. verify tenant AI settings, provider health, and non-AI workflows before removing the kill switch;
6. generated content remains non-authoritative unless a human already accepted it through existing deterministic application paths.

## Known limitations

- no production provider implementation or provider credential lifecycle is validated by repository CI;
- no payment, subscription, invoice, or monetized AI credit behavior exists in Sprint 7;
- knowledge retrieval is deterministic lexical retrieval rather than vector/embedding search;
- no arbitrary internet crawling or external enrichment is included;
- no autonomous send, publish, or protected-record mutation exists;
- production/manual smoke verification remains deployment-time work.

## Exit criteria assessment

1. Tenant-safe, explicitly authorized, provider-neutral, bounded AI execution — met.
2. Human-reviewable drafting, summaries, replies, and knowledge search without autonomous actions — met.
3. Tenant enablement and usage controls — met.
4. Provider credentials/protected internal data excluded from persistence/audit/model context by default — met.
5. Existing protected non-AI product areas remain regression-gated — met.
6. AI can be disabled without disabling the underlying product workflow — met.
7. Full protected regression evidence — pending final S7-T10 branch/CI verification.
8. Release/rollback evidence and known limitations — met.

## Finalization rule

This closure record becomes final when the S7-T10 closure pull request is merged with all required CI checks green. The merge commit of that pull request is the Sprint 7 repository/CI closure baseline.
