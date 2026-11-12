# S7-T03 Provider-Neutral AI Execution and Usage Accounting

## Purpose

S7-T03 introduces the execution seam used by later Sprint 7 AI features while keeping provider choice, credentials, and tenant authorization separate.

The application depends on a narrow provider interface rather than a vendor SDK. Repository tests use a fake provider and make no network calls.

## Provider contract

A provider supplies:

- a bounded provider name;
- a bounded model identifier;
- a `generate()` operation accepting prompt text, an output-unit ceiling, and an explicit timeout;
- a result containing generated text plus provider-reported input/output units.

Provider implementations are responsible for honoring the passed timeout at the transport/client layer. The execution facade converts provider `TimeoutError` and other failures into controlled application errors.

No provider API key or credential is accepted by or persisted through this interface.

## Pre-execution admission

Before `generate()` is called, execution requires:

1. S7-T01 active user/organization/explicit-membership authorization;
2. S7-T02 explicit tenant AI enablement;
3. per-request input/output limits;
4. the tenant rolling usage limit.

The rolling window is currently 24 hours and counts successful provider input + output units. This is an operational cost/safety limit, not a billing balance.

If admission fails, the provider is not called.

## Task types

S7-T03 permits only the planned Sprint 7 task families:

- `draft`;
- `summary`;
- `suggested_reply`;
- `knowledge_search`.

Later tasks may add narrower subtypes only with plan/acceptance updates.

## Append-only usage metadata

Each provider attempt records bounded metadata:

- tenant/organization;
- task type;
- provider name;
- model identifier;
- input units;
- output units;
- status;
- timestamp.

Statuses introduced here are:

- `success`;
- `provider_error`;
- `timeout`;
- `invalid_response`.

The usage table has no prompt, response, provider-secret, session-token, or customer-content column.

Raw prompts and generated responses are intentionally not required for usage accounting.

## Failure behavior

Provider timeout, provider error, or invalid provider result:

- returns a controlled `AIExecutionError`;
- records bounded status metadata;
- does not persist generated content;
- does not mutate CRM, Portal, Site Builder, Creator, conversation, or customer records.

AI-disabled and limit-rejected requests fail before provider invocation.

## Tenant isolation

Usage reads:

- require the same S7-T01 active membership boundary;
- query by the authorized organization ID;
- are bounded to 1–500 records;
- cannot infer access from a user's home organization.

An explicit membership in another tenant authorizes only that tenant's usage namespace.

## Provider credentials

Provider credentials remain deployment configuration/secret-manager concerns. They must never be placed in:

- `ai_tenant_settings`;
- `ai_usage_events`;
- prompts;
- usage audit metadata;
- API responses.

## Regression evidence

`tests/test_sprint7_ai_execution.py` verifies:

- successful provider-neutral execution;
- explicit timeout and output ceiling propagation;
- append-only usage metadata;
- raw prompt/response/provider-secret absence from persistence;
- controlled timeout/provider-error handling;
- invalid provider response rejection;
- rolling limit enforcement before a subsequent provider call;
- cross-tenant usage-read denial;
- AI-disabled failure before provider invocation;
- bounded task/provider/model/timeout inputs.

## Handoff to S7-T04

S7-T04 may build human-reviewed drafting on this execution facade. Draft output must remain separate from canonical persisted content and must never be auto-saved, auto-sent, or auto-published.
