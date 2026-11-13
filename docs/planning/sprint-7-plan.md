# Sprint 7 Plan — AI Assistance

- Status: Closed at repository/CI level
- Epic: EP-010 — AI Assistance
- Protected baselines: Sprint 1 Single-Business MVP, Sprint 2 Multi-Tenant Foundation, Sprint 3 Site Builder, Sprint 4 CRM, Sprint 5 Customer Portal, Sprint 6 Creator and Commerce Tools
- Sprint 6 repository/CI baseline: `ae3c1ba9f0a6e4959c69f617fec0d4ef3f368a35`

## Objective

Add measurable AI assistance for tenant staff and creator workflows while preserving tenant isolation, requiring human review for consequential output, and preventing uncontrolled model usage or cost.

## Entry criteria

- Sprint 6 is closed at repository/CI level.
- `make test` and `make test-sprint2` through `make test-sprint6` are protected regression gates.
- Tenant/site/customer/CRM/portal/creator ownership boundaries are established.
- Active organization membership is the source of tenant application authorization.
- AI features are additive; protected non-AI workflows remain functional when AI is disabled or unavailable.
- No Sprint 7 story may introduce billing/subscription enforcement, autonomous external actions, or automatic publication/sending of model output.

## Locked scope

Sprint 7 covers:

- canonical tenant/site-aware AI request context and data-classification boundaries;
- provider-neutral AI execution with explicit configuration and fail-closed behavior;
- tenant-level enablement, usage limits, and bounded usage accounting;
- staff drafting assistance for supported CRM/portal/creator text workflows;
- bounded summarization of authorized tenant-owned records;
- suggested customer-reply generation that always requires human review before sending;
- tenant-safe knowledge retrieval over explicitly eligible repository/application records;
- reusable AI authorization and administration controls;
- append-only AI usage/audit metadata without storing provider secrets;
- focused Sprint 7 regression and closure evidence.

## Explicit non-scope

- autonomous sending of email, portal messages, social posts, or customer replies;
- autonomous record mutation based solely on model output;
- automatic publication of generated creator/site content;
- model training or fine-tuning on tenant data;
- cross-tenant retrieval, shared tenant embeddings, or shared conversational memory;
- scraping arbitrary external websites for model context;
- voice/image/video generation or processing;
- payment capture, subscription billing, invoices, plan enforcement, or monetized AI credits;
- storing provider API keys in the application database;
- hidden prompt injection of secrets, credentials, storage keys, session tokens, or infrastructure configuration;
- replacing deterministic authorization/business rules with model decisions.

## Safety and cost principles

1. Authorization is evaluated before any model context is assembled.
2. Only the minimum authorized context required for a task is included.
3. Model output is untrusted text until validated by deterministic application code.
4. Generated content cannot bypass existing tenant/site/customer visibility rules.
5. Human review is mandatory before any generated text is sent or published.
6. Provider credentials remain environment/secret-manager configuration, never tenant content.
7. Usage is bounded by explicit per-request limits and tenant-level controls.
8. AI failure, timeout, quota exhaustion, or disabled configuration must degrade to the existing non-AI workflow.
9. Prompts, model responses, and usage metadata must not create a new cross-tenant data channel.
10. CI success is not production/provider verification.

## Task sequence

### S7-T01 — AI tenant boundary, data classification, and threat audit

Define canonical ownership and authorization for AI requests before integrating a model provider.

Acceptance:

- every AI request is owned by one active organization and, when applicable, one same-tenant site/customer/CRM/portal/creator scope;
- request authorization requires an active user, active organization, and active explicit membership;
- platform-admin/bootstrap identity does not implicitly grant tenant AI access without tenant membership;
- cross-tenant/site/customer record references fail closed before prompt construction;
- supported context classes are explicitly enumerated;
- secrets, authentication material, provider keys, storage keys, infrastructure state, internal-only portal content, and unrelated tenant data are excluded by default;
- model output is classified as untrusted text and cannot directly authorize or mutate protected records;
- prompt-injection and data-exfiltration risks are documented;
- no provider calls, model credentials, or usage persistence are introduced in this boundary step.

### S7-T02 — AI settings and usage-control foundation

Add tenant-owned AI enablement and bounded usage-control configuration.

Acceptance:

- AI is disabled by default for tenants without explicit configuration;
- tenant settings include explicit enablement plus bounded per-request and rolling usage limits;
- configuration is tenant-scoped and may be changed only by authorized owner/admin roles;
- staff/viewer users cannot raise tenant AI limits;
- usage-control checks fail closed when configuration is invalid or tenant state is inactive;
- no billing, subscription, invoice, or paid-credit behavior is introduced.

### S7-T03 — Provider-neutral AI execution and usage accounting

Add a provider-neutral request executor with deterministic limits, explicit timeouts, and append-only usage metadata.

Acceptance:

- application code depends on a narrow provider interface rather than provider-specific calls;
- provider configuration is loaded only from environment/secret-manager inputs;
- provider secrets are never returned by application APIs, persisted to tenant tables, or written to audit metadata;
- request input/output sizes are bounded before/after provider execution;
- timeouts/provider failures return controlled errors without breaking the non-AI workflow;
- append-only usage records capture tenant, task type, model identifier, bounded token/unit counts, status, and timestamps;
- raw prompts/responses are not required for usage accounting;
- cross-tenant usage reads fail closed.

### S7-T04 — Drafting assistance

Add human-reviewed drafting for supported tenant staff and creator text fields.

Acceptance:

- drafting is available only to authorized users and enabled tenants;
- source context is restricted to explicitly selected authorized records;
- generated drafts are returned separately from canonical persisted content;
- generated drafts are never auto-saved, auto-sent, or auto-published;
- callers may accept/edit/reject output using existing deterministic mutation paths;
- unsafe or oversized context is rejected before provider execution;
- protected non-AI editing remains available when AI is disabled/unavailable.

### S7-T05 — Authorized record summarization

Add bounded summaries for supported CRM, portal, conversation, and creator records.

Acceptance:

- summaries may include only records the requesting user is already authorized to read;
- internal-only/customer-visible distinctions are preserved;
- cross-customer, cross-site, and cross-tenant aggregation fails closed;
- summary inputs are bounded and deterministic;
- generated summaries are labeled as AI-generated and are not persisted as authoritative history by default;
- source record identifiers remain available to the caller for human verification.

### S7-T06 — Suggested customer replies

Add AI-generated reply suggestions for authorized conversation/portal contexts.

Acceptance:

- suggestion context is restricted to the authorized customer/conversation/ticket/project scope;
- internal-only messages or files are excluded from customer-facing suggestions unless explicitly eligible and authorized;
- suggestions cannot be sent automatically;
- sending still uses the existing protected messaging mutation path and requires a human action;
- generated text cannot change customer identity, tenant scope, recipient, visibility, or authorization metadata;
- AI/provider failure leaves manual reply behavior intact.

### S7-T07 — Tenant-safe knowledge search

Add AI-assisted knowledge retrieval over explicitly eligible tenant records.

Acceptance:

- searchable sources are allow-listed and tenant/site scoped;
- indexing/retrieval never mixes tenant namespaces;
- records hidden by existing visibility/authorization rules remain non-retrievable;
- retrieval returns source references sufficient for human verification;
- prompt content from retrieved records is treated as untrusted data rather than executable instructions;
- no arbitrary internet crawling or hidden external enrichment is introduced;
- the first implementation may use deterministic lexical retrieval; vector/embedding storage is optional and must preserve the same tenant boundary.

### S7-T08 — AI authorization and administration

Add reusable AI capabilities and an administration facade.

Acceptance:

- owner/admin may manage tenant AI configuration and view usage/audit summaries;
- staff may use approved AI assistance capabilities but may not raise limits or change provider configuration;
- viewer access is read-only where explicitly allowed and otherwise denied;
- unknown AI capabilities fail closed;
- revoked membership, disabled user, inactive/suspended organization, and archived scoped resources fail closed;
- administration operations enforce authorization rather than relying on UI hiding.

### S7-T09 — AI auditability and operational safeguards

Add operational views/helpers for usage, errors, limits, and provider-independent diagnostics.

Acceptance:

- usage/audit reads are tenant-scoped and bounded;
- audit records distinguish success, rejected-before-call, provider error, timeout, and quota/limit outcomes;
- provider secrets and full authentication/session material are never logged;
- operators can identify model/task usage and failure rates without reading unrelated tenant content;
- kill-switch behavior can disable AI while preserving non-AI application functionality;
- known production verification steps and rollback behavior are documented.

### S7-T10 — Sprint 7 regression and closure

Status: implemented on the closure candidate branch. Adds `make test-sprint7`, enforces the focused CI gate, records rollback evidence, and formally closes Sprint 7 when the closure PR merges green.

## Testing requirements

- `make test` remains the complete regression gate.
- `make test-sprint2` through `make test-sprint6` remain protected focused gates.
- Sprint 7 adds `make test-sprint7`.
- Every AI tenant/site/customer/record boundary requires positive and negative authorization coverage.
- Tests must prove provider-disabled/failure/timeout behavior leaves protected non-AI workflows usable.
- Tests must prove generated drafts/replies are not automatically persisted, sent, or published.
- Usage-limit and usage-accounting tests must be deterministic and provider-independent.
- Provider network calls must be mocked/faked in repository CI unless a separate explicitly configured integration job is introduced.
- CI success is not production/provider verification.

## Exit criteria

1. AI execution is tenant-safe, explicitly authorized, provider-neutral, and bounded.
2. Drafting, summaries, suggested replies, and knowledge search provide human-reviewable assistance without autonomous actions.
3. Tenant enablement and usage controls prevent uncontrolled model use.
4. Provider credentials and protected internal data are not exposed through persistence, audit metadata, or model context.
5. Existing Site Builder, CRM, Customer Portal, Creator Tools, customer authentication, and non-AI workflows remain compatible.
6. AI can be disabled without disabling the underlying product workflow.
7. Full protected regression evidence is green.
8. Release/rollback evidence and known limitations are recorded.
