# S7-T09 AI Auditability and Operational Safeguards

## Purpose

S7-T09 strengthens Sprint 7 runtime observability and failure handling without expanding AI authority.

The focus is bounded operational metadata, explicit pre-call rejection statuses, content-free diagnostics, and an AI-only emergency kill switch.

## Usage and audit statuses

The AI usage ledger now supports:

- `success`;
- `rejected_before_call`;
- `provider_error`;
- `timeout`;
- `quota_limit`;
- `invalid_response`.

Pre-call tenant disablement and the global operational kill switch are recorded as `rejected_before_call`.

Input/output/rolling limit rejections are recorded as `quota_limit`.

Provider exceptions and timeouts remain explicit and separate.

## Schema migration

Existing `ai_usage_events` tables are migrated in place to the expanded status constraint.

Existing rows are preserved and copied into the new schema before the legacy table is removed.

The ledger remains append-only through application APIs.

## AI-only kill switch

Set:

`MADMALLARD_AI_KILL_SWITCH=true`

to reject AI execution before any provider call.

The kill switch:

- does not disable login, CRM, Portal, Site Builder, Creator, or messaging workflows;
- records a bounded `rejected_before_call` usage event for an otherwise authorized tenant request;
- can be rolled back by removing or disabling the environment variable and restarting/reloading the service.

This is an operational safety control, not a tenant billing or entitlement flag.

## Content-free operational summaries

Owner/admin users may retrieve bounded operational summaries through `ai_admin.operational_summary()`.

Summaries include only:

- total event count;
- success/failure counts;
- total provider-reported usage units;
- failure rate;
- counts by status;
- counts by AI task type;
- counts by model identifier.

Operational summaries do not include:

- prompts;
- generated responses;
- CRM/customer content;
- provider credentials;
- session tokens;
- authorization secrets.

## Production verification

After deployment:

1. verify normal non-AI workflows still function;
2. verify AI calls succeed only for an enabled tenant;
3. set `MADMALLARD_AI_KILL_SWITCH=true`;
4. verify AI calls fail before provider invocation while non-AI workflows remain available;
5. verify the tenant usage ledger records `rejected_before_call`;
6. remove/disable the kill-switch variable;
7. verify AI returns to the tenant-configured state;
8. inspect owner/admin operational summary for expected status/model/task counts.

## Rollback

If the S7-T09 release must be rolled back:

- disable AI first with the kill switch;
- restore the previous application image/revision;
- preserve the expanded `ai_usage_events` table, because older valid statuses remain compatible data;
- do not copy prompts or provider responses into rollback diagnostics;
- re-enable AI only after tenant settings and provider health are verified.

## Regression evidence

`tests/test_sprint7_ai_operations.py` verifies:

- kill-switch rejection occurs before provider invocation;
- kill-switch rejection is auditable;
- quota/limit rejection is auditable;
- provider-error and timeout statuses remain distinct;
- usage schema contains no prompt/response/secret/session-token fields;
- operational summaries report task/model/status counts and failure rate;
- expanded usage status schema is present after migration.

## Handoff to S7-T10

S7-T10 closes Sprint 7 with a focused regression gate, rollback evidence, release candidate baseline, and sprint closure documentation.
