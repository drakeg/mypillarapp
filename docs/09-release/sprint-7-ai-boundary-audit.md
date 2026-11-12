# S7-T01 AI Tenant Boundary, Data Classification, and Threat Audit

## Purpose

S7-T01 defines the authorization and data-classification boundary that every later Sprint 7 AI feature must cross before provider integration or prompt construction is allowed.

This task deliberately introduces **no model provider calls, credentials, prompt persistence, response persistence, usage accounting, autonomous actions, or billing behavior**.

## Canonical AI request ownership

Every AI request is owned by exactly one active organization.

The request boundary requires:

- an existing active application user;
- an active target organization;
- an explicit active membership for that user in that organization;
- when a site is supplied, a non-archived site owned by the same organization.

A user's home organization is not an authorization shortcut. A cross-tenant membership grants access only when that explicit membership exists. Platform/bootstrap administration remains a separate security scope and does not satisfy tenant AI authorization.

## Allow-listed context classes

S7-T01 permits only explicitly classified context references:

| Context class | Boundary |
| --- | --- |
| `site_page` | Must resolve through the authorized organization and authorized site scope |
| `crm_company` | Must resolve through the authorized organization |
| `portal_project` | Must resolve through the authorized organization |
| `creator_profile` | Must resolve through the authorized organization/site |
| `creator_link` | Must resolve through the authorized organization/site |
| `conversation` | Must resolve through the authorized tenant conversation namespace |

Unknown context classes fail closed.

The boundary validates references before later code is permitted to assemble model context. This prevents a caller from supplying an identifier from another tenant and relying on downstream prompt construction to filter it.

## Blocked context classes

The following classes are explicitly ineligible for model context in S7-T01:

- authentication material;
- provider secrets;
- session tokens;
- opaque storage keys;
- infrastructure state/configuration;
- internal-only portal data.

This list is intentionally conservative. Later tasks may add narrowly defined eligible context classes only with deterministic ownership/visibility checks and regression tests.

## Output trust boundary

All future model output is classified as:

`untrusted_generated_text`

Generated text cannot:

- grant authorization;
- change tenant/site/customer scope;
- directly mutate records;
- send customer messages;
- publish Site Builder or Creator content;
- override deterministic validation;
- be treated as authoritative history without an explicit later workflow.

Human review and existing protected mutation paths remain mandatory.

## Threat audit

### Cross-tenant object reference injection

Threat: a caller supplies a valid record identifier that belongs to another organization.

Control: record lookup is performed through organization-scoped repository functions before context assembly. Foreign IDs return no eligible record and fail closed.

### Cross-site context injection

Threat: an authorized tenant user scopes an AI request to one site but supplies a record from another site in the same organization.

Control: site-owned context must match the authorized site when a site scope is present.

### Prompt injection from tenant content

Threat: an authorized record contains text telling the model to ignore instructions, expose secrets, or retrieve unrelated data.

Control: tenant content is classified as untrusted data. Retrieval authorization is completed before content is exposed to future model code. Record text cannot expand authorization or select additional hidden records.

### Secret and credential exfiltration

Threat: provider keys, sessions, storage references, or infrastructure configuration are inserted into model context.

Control: secret/auth/storage/infrastructure context classes are explicitly blocked. Provider configuration does not exist in S7-T01.

### Internal-to-customer visibility leakage

Threat: internal portal records are included in a future customer-facing drafting/reply workflow.

Control: `portal_internal` is explicitly blocked at this boundary. Later customer-facing AI tasks must preserve the existing Customer Portal visibility rules before enabling narrower context types.

### Model-output authority confusion

Threat: generated text is treated as an authorization decision or directly persisted/sent.

Control: all output is designated untrusted generated text. No provider execution or mutation path exists in S7-T01.

### Platform-admin boundary confusion

Threat: a valid platform/bootstrap administrator session implicitly grants tenant AI access.

Control: tenant AI authorization requires an `auth_users` identity plus an active explicit organization membership. Platform administration remains separate.

## Regression evidence

`tests/test_sprint7_ai_boundary.py` covers:

- active tenant/site authorization;
- revoked membership, disabled-user, suspended-organization, and archived-site denial;
- explicit cross-tenant membership behavior;
- no implicit platform-admin/unknown-user access;
- allow-listed, blocked, and unknown context classification;
- same-tenant CRM/portal record acceptance;
- foreign CRM/portal record rejection;
- same-site Site Builder/Creator context acceptance;
- cross-site rejection;
- sensitive/unknown context rejection before record lookup;
- generated-output untrusted classification.

## Handoff to S7-T02

S7-T02 may add tenant-owned AI enablement and bounded usage-control settings. It must build on this boundary and must not weaken the active-user, active-organization, explicit-membership, site-scope, or context-classification rules documented here.
