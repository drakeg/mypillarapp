# S7-T05 Authorized Record Summarization

## Purpose

S7-T05 adds bounded AI summaries over explicitly authorized tenant-owned records.

Summaries are returned as non-authoritative suggestions with exact source references. They are not written back into CRM, Customer Portal, Site Builder, Creator, conversation, or customer history.

## Supported context

The summarization layer supports the S7-T01 allow-listed record types used by Sprint 7:

- Site Builder pages;
- CRM companies;
- Customer Portal projects;
- Creator profiles;
- Creator links;
- tenant conversations.

All references are validated through the S7-T01 tenant/site boundary before source content is assembled.

## Visibility preservation

Conversation context preserves each message's visibility label:

- customer-visible messages are marked `[customer]`;
- internal messages are marked `[internal]`.

The model is instructed to preserve these distinctions rather than flattening them into one customer-visible narrative.

## Cross-customer aggregation controls

S7-T05 fails closed when one summarization request attempts to combine:

- Customer Portal projects owned by different customer users; or
- conversations associated with different normalized customer email addresses.

This prevents a single model prompt from becoming a cross-customer aggregation channel inside an otherwise valid tenant.

Cross-tenant and cross-site references continue to fail through the S7-T01 boundary.

## Bounded context

- optional summary focus is limited to 1,000 characters;
- assembled source context is limited to 16,000 characters;
- provider execution still passes through S7-T02/S7-T03 request and rolling usage limits.

## Non-authoritative output

Every result returns:

- generated summary text;
- exact authorized source references;
- `untrusted_generated_text` output classification;
- `authoritative=False`;
- S7-T03 usage metadata.

The module has no persistence method for generated summaries.

## Failure behavior

Authorization, cross-customer aggregation, disabled AI, over-limit usage, provider timeout/error, and invalid provider output all fail without mutating canonical records.

## Regression evidence

`tests/test_sprint7_ai_summarization.py` verifies:

- non-authoritative summary output;
- source-reference traceability;
- internal/customer conversation visibility labels;
- cross-customer Customer Portal aggregation rejection;
- cross-customer conversation aggregation rejection;
- canonical project summaries remain unchanged after AI summarization.

## Handoff to S7-T06

S7-T06 may add customer-reply suggestions using conversation/project context. It must exclude internal-only content from customer-facing suggestions unless explicitly eligible, and sending must remain a separate human action through the existing protected messaging path.
