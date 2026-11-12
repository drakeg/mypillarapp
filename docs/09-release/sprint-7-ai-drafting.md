# S7-T04 Human-Reviewed Drafting Assistance

## Purpose

S7-T04 adds drafting assistance on top of the S7-T01 tenant/context boundary and S7-T03 provider-neutral execution layer.

Generated text is returned only as an editable suggestion. It is not written to CRM, Customer Portal, Site Builder, Creator, conversation, or customer records.

## Supported drafting context

Drafting accepts only explicitly selected S7-T01 context references. The current context assembler supports:

- Site Builder pages;
- CRM companies;
- Customer Portal projects;
- Creator profiles;
- Creator links;
- conversation metadata only.

Conversation message bodies are intentionally excluded from S7-T04. Customer-facing reply context and internal/customer visibility handling remain S7-T06 scope.

## Human-review boundary

Every result is returned as a `DraftSuggestion` containing:

- generated draft text;
- the exact authorized source references used;
- the S7-T01 `untrusted_generated_text` classification;
- the associated S7-T03 usage record.

There is no save, send, publish, update, or mutation method in the drafting module.

Existing deterministic application mutation paths remain the only way to change canonical records after a human reviews or edits the draft.

## Prompt construction

The prompt explicitly instructs the provider that:

- source content is untrusted data rather than instructions;
- the output is for human review;
- it must not claim the content was saved, sent, published, or approved.

Drafting instructions are bounded to 2,000 characters and assembled context is bounded to 12,000 characters.

Provider-neutral requested input units are estimated from the final bounded prompt and still pass through S7-T02/S7-T03 tenant limits before provider invocation.

## Authorization and isolation

Before prompt construction:

1. the user/organization/site scope is authorized by S7-T01;
2. every selected record is validated by `validate_context_set()`;
3. cross-tenant and cross-site references fail closed;
4. only then is text extracted from the authorized records.

AI-disabled or over-limit requests fail before provider invocation.

## No persistence or publication

S7-T04 does not:

- write generated text to canonical data;
- auto-save edits;
- send messages or email;
- publish Site Builder pages;
- publish Creator profiles or links;
- change CRM or Portal records;
- add an approval state.

The caller may later present the suggestion to a human, who can use the existing protected non-AI editing workflow.

## Regression evidence

`tests/test_sprint7_ai_drafting.py` verifies:

- authorized multi-source drafting;
- generated text is marked untrusted;
- canonical CRM and Site Builder records are unchanged;
- draft Creator profiles remain unchanged and unpublished;
- cross-tenant references fail before provider invocation;
- disabling AI prevents provider invocation while leaving canonical records intact;
- drafting instructions are bounded.

## Handoff to S7-T05

S7-T05 may add authorized record summarization using the same pre-context authorization and provider-neutral execution boundaries. Summaries must remain non-authoritative by default and preserve source references for human verification.
