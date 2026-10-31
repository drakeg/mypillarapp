# Sprint 6 Plan — Creator and Commerce Tools

- Status: Active
- Epic: EP-009 — Creator Tools
- Protected baselines: Sprint 1 Single-Business MVP, Sprint 2 Multi-Tenant Foundation, Sprint 3 Site Builder, Sprint 4 CRM, Sprint 5 Customer Portal
- Sprint 5 repository/CI baseline: `474fa941cca5f092d748479aeeef8e90bafdbc4c`

## Objective

Support Mad Mallards Adventures and other creator businesses with tenant-safe public creator pages, affiliate/link management, content collections, digital-download metadata, storefront foundations, and creator analytics without introducing payment processing before Sprint 8.

## Entry criteria

- Sprint 5 is closed at repository/CI level.
- `make test`, `make test-sprint2`, `make test-sprint3`, `make test-sprint4`, and `make test-sprint5` are protected regression gates.
- Tenant/site/domain resolution and Site Builder publishing are established.
- Customer/CRM boundaries remain protected.
- No Sprint 6 story may introduce subscription billing, payment capture, or invoice processing.

## Locked scope

Sprint 6 covers:
- tenant-owned creator profiles and public link pages;
- affiliate-link records and disclosure metadata;
- content collections and ordered content items;
- digital-download catalog metadata and entitlement-ready foundations;
- storefront/product catalog foundations without payment capture;
- creator click/view/download analytics;
- tenant membership authorization for creator administration;
- public creator/storefront rendering through resolved sites/domains;
- non-destructive compatibility with existing Mad Mallards Adventures links/content where applicable;
- focused Sprint 6 regression and closure evidence.

## Explicit non-scope

- Stripe or any other payment provider;
- subscriptions, invoices, taxes, licensing, or paid tenant plans;
- AI-generated content or recommendations;
- DRM or generalized binary asset delivery;
- marketplace/vendor settlement;
- destructive replacement of existing public Site Builder pages;
- uncontrolled third-party script injection.

## Task sequence

### S6-T01 — Creator tenant/site boundary and legacy audit
Define canonical ownership for creator records and audit existing Site Builder pages, external links, Adventures content, and any legacy affiliate/storefront configuration.

Acceptance:
- creator records are owned through canonical organization and site identifiers;
- authoring scope requires an active organization, non-archived same-tenant site, and active organization membership;
- public creator scope requires an active domain resolving to the same active organization and a published site;
- cross-tenant/site authoring attempts fail closed;
- the read-only audit inventories sites, published sites, active domains, external navigation links, and external media sources;
- legacy plain-HTTP external URLs and credential-bearing URLs are explicitly reported as unsafe Sprint 6 migration inputs;
- domain-to-site organization mismatches are reported;
- published sites without active domains are reported for operational review;
- arbitrary Site Builder page bodies are not parsed into creator/affiliate/commerce records;
- legacy service `price_text` is not treated as structured commerce pricing or payment behavior;
- no creator, affiliate, product, collection, download, storefront, analytics, or payment persistence is introduced in this boundary step;
- migration constraints are documented in [S6-T01 Creator Tenant/Site Boundary and Legacy Audit](../09-release/sprint-6-creator-boundary-audit.md).

### S6-T02 — Creator profile and link-page foundation
Add tenant/site-owned creator profile metadata and ordered public links.

Acceptance:
- exactly one creator profile may exist per site;
- profile display name is required/bounded, bio is bounded, and optional avatar URLs require credential-free HTTPS;
- profile lifecycle is draft, published, or archived;
- archived profiles are immutable;
- creator links are site-scoped with bounded labels, safe targets, nonnegative positions, and draft/published/archived lifecycle;
- external links require credential-free HTTPS URLs;
- internal links are restricted to root-relative targets and protocol-relative targets are rejected;
- archived links are immutable and hidden by default;
- published-only reads expose only published links;
- duplicate positions remain deterministic by creation ID;
- cross-site and cross-tenant reads/updates fail closed;
- archived sites cannot be modified;
- no affiliate disclosure, analytics, storefront, download, or payment behavior is introduced in this task.

### S6-T03 — Affiliate-link metadata and disclosure controls
Add affiliate records with destination URLs, network/program metadata, labels, and disclosure behavior.

Acceptance:
- affiliate links are tenant/site-owned;
- destination URLs are validated HTTPS;
- disclosure text is explicit and configurable within bounded limits;
- public rendering can visibly distinguish affiliate links;
- tracking parameters may be stored but arbitrary script injection is prohibited;
- inactive/archived records are not public;
- cross-tenant mutation/read attempts fail closed.

### S6-T04 — Content collections
Add tenant/site-owned collections for videos, articles, travel guides, gear lists, or other creator content.

Acceptance:
- collection title/slug/description/status/order are validated;
- collection slugs are unique per site;
- items are ordered deterministically;
- item references may be safe internal URLs or validated HTTPS external URLs;
- draft/archived collections are not public;
- cross-site/cross-tenant isolation is enforced.

### S6-T05 — Digital-download catalog metadata
Add metadata for downloadable creator products without implementing payment capture or generalized binary storage.

Acceptance:
- download catalog records are tenant/site-owned;
- title/description/status/version and optional file metadata are validated;
- source references use safe external HTTPS URLs or opaque storage keys;
- customer/public visibility is explicit;
- storage keys are never exposed directly by public rendering;
- no payment entitlement is inferred from catalog presence;
- binary storage/delivery provider remains outside this task.

### S6-T06 — Storefront/product catalog foundations
Add creator product/storefront records for free or future-paid offerings without payment processing.

Acceptance:
- products are tenant/site-owned;
- product type is explicitly enumerated;
- price metadata, when present, uses integer cents and ISO currency but does not trigger payment behavior;
- product publication lifecycle is explicit;
- optional digital-download linkage is same-tenant/site;
- storefront ordering is deterministic;
- no checkout, invoice, subscription, tax, or payment-provider behavior is introduced.

### S6-T07 — Creator analytics event foundation
Add bounded first-party analytics events for creator page views, link clicks, collection opens, and download/storefront interactions.

Acceptance:
- analytics events are tenant/site-owned;
- supported event types are explicitly enumerated;
- target references remain same-tenant/site when applicable;
- event payloads are bounded and do not accept arbitrary executable content;
- analytics reads are tenant-scoped and bounded;
- public event creation cannot probe another tenant/site;
- no ad-tech profile building or cross-tenant tracking is introduced.

### S6-T08 — Creator authorization and administration
Add reusable creator-management authorization and an administration facade.

Acceptance:
- owner/admin may administer creator configuration;
- staff may manage creator content according to least privilege;
- viewer is read-only or denied mutation;
- platform-admin identity does not implicitly grant tenant creator mutation rights;
- revoked memberships and inactive/suspended tenants fail closed;
- all mutations pass through tenant/site authorization.

### S6-T09 — Public creator and storefront rendering
Expose published creator profiles, link pages, collections, affiliate disclosures, download/catalog metadata, and storefront foundations through resolved public sites.

Acceptance:
- public rendering is hostname/site aware;
- only published/visible records appear;
- HTML is escaped;
- affiliate disclosure is visible where required;
- hidden storage keys and internal metadata are not exposed;
- unsafe links/scripts are not rendered;
- existing protected Site Builder public behavior remains compatible.

### S6-T10 — Adventures compatibility migration
Stage existing Mad Mallards Adventures creator/link/affiliate/content configuration into canonical Sprint 6 records where safe.

Acceptance:
- migration is explicit, non-destructive, and idempotent;
- existing public content is not overwritten automatically;
- unsafe/unmatched legacy records are reported rather than guessed;
- owner edits to canonical records are preserved on rerun;
- no live cutover occurs merely because migration ran.

### S6-T11 — Sprint 6 regression and closure
Add `make test-sprint6`, enforce the focused CI gate, record rollback evidence, and formally close Sprint 6.

## Testing requirements

- `make test` remains the complete regression gate.
- `make test-sprint2` through `make test-sprint5` remain protected focused gates.
- Sprint 6 adds `make test-sprint6`.
- Every tenant/site-owned read and mutation requires positive and negative isolation coverage.
- Public rendering tests must cover publication state, escaping, unsafe-link rejection, and hidden metadata.
- Migration tests must prove idempotence and non-destructive behavior.
- CI success is not production/manual-smoke evidence.

## Exit criteria

1. Creator profiles, links, affiliate records, collections, download metadata, product catalog, and analytics are tenant/site-safe.
2. Public rendering exposes only safe published records through resolved sites/domains.
3. Creator administration follows active-membership least privilege.
4. Payment processing remains absent and clearly deferred to Sprint 8.
5. Existing protected Site Builder, CRM, and Customer Portal behavior remains compatible.
6. Adventures compatibility migration is non-destructive and documented.
7. Full protected regression evidence is green.
8. Release/rollback evidence and known limitations are recorded.
