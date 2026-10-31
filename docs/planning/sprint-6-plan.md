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
- affiliate links are canonical site-owned records and inherit tenant ownership through the Site Builder site;
- labels, network names, program names, disclosure text, tracking metadata, and positions are bounded/validated;
- destination URLs require credential-free HTTPS and reject HTTP, JavaScript, FTP, and embedded credentials;
- disclosure text is required for every affiliate record and is stored separately from destination/tracking metadata;
- disclosure/tracking/network/program fields reject executable script content rather than accepting arbitrary markup;
- tracking metadata remains inert data and does not execute third-party scripts;
- lifecycle is draft, published, or archived;
- archived affiliate records are immutable and hidden by default;
- published-only reads expose only published records;
- duplicate positions remain deterministically ordered by record ID;
- cross-site and cross-tenant reads/updates fail closed;
- archived sites cannot be modified;
- no public rendering, click analytics, storefront, payment, tax, invoice, or subscription behavior is introduced in this task.

### S6-T04 — Content collections
Add tenant/site-owned collections for videos, articles, travel guides, gear lists, or other creator content.

Acceptance:
- collections are canonical site-owned records and inherit tenant ownership through the Site Builder site;
- collection slugs use normalized lowercase letters/numbers/hyphens and are unique per site;
- collection title/description/position/status are bounded and validated;
- lifecycle is draft, published, or archived;
- archived collections are immutable and hidden by default;
- published-only reads expose only published collections;
- duplicate collection positions are deterministic by record ID;
- collection items belong to the same site and collection;
- item titles/positions are validated;
- item targets may be safe root-relative internal paths or credential-free HTTPS external URLs only;
- HTTP, protocol-relative, credential-bearing, JavaScript, FTP, and empty targets are rejected;
- item ordering is deterministic by position then record ID;
- items cannot be added, changed, or deleted after their collection is archived;
- cross-site and cross-tenant collection/item reads and mutations fail closed;
- archived sites cannot be modified;
- no public rendering, affiliate inference, analytics, storefront, download, or payment behavior is introduced in this task.

### S6-T05 — Digital-download catalog metadata
Add metadata for downloadable creator products without implementing payment capture or generalized binary storage.

Acceptance:
- download records are canonical site-owned records and inherit tenant ownership through the Site Builder site;
- title/description/version/file-name/MIME metadata are bounded and validated;
- source type is explicitly either `external_url` or `storage_key`;
- external URLs require credential-free HTTPS;
- storage keys are opaque metadata and reject absolute paths, traversal, empty path segments, and `file:` URIs;
- visibility is explicitly `public`, `customer`, or `internal`;
- lifecycle is draft, published, or archived;
- archived records are immutable and hidden by default;
- published/visibility filters are tenant/site scoped;
- public source exposure returns an external URL only for published public records and never returns storage keys;
- cross-site and cross-tenant reads/updates fail closed;
- archived sites cannot be modified;
- catalog presence creates no pricing, payment-provider, or entitlement state;
- generalized binary storage/delivery remains outside this task.

### S6-T06 — Storefront/product catalog foundations
Add creator product/storefront records for free or future-paid offerings without payment processing.

Acceptance:
- products are canonical site-owned records and inherit tenant ownership through the Site Builder site;
- product type is explicitly one of `service`, `digital_download`, `physical`, or `external`;
- title/description/position/status are bounded and validated;
- optional price metadata uses a non-negative integer number of cents plus a three-letter ISO currency code;
- zero-price products are valid and price metadata remains catalog-only;
- digital-download products require a same-site download record and other product types may not link downloads;
- external products require a credential-free HTTPS URL and non-external product types may not define one;
- lifecycle is draft, published, or archived;
- archived products are immutable and hidden by default;
- published-only reads expose only published records;
- duplicate storefront positions remain deterministically ordered by record ID;
- cross-site and cross-tenant reads/updates fail closed;
- archived sites cannot be modified;
- no checkout, payment provider, invoice, subscription, tax, licensing, order, or entitlement behavior is introduced.

### S6-T07 — Creator analytics event foundation
Add bounded first-party analytics events for creator page views, link clicks, collection opens, and download/storefront interactions.

Acceptance:
- analytics events are append-only canonical site-owned records and inherit tenant ownership through the Site Builder site;
- supported event types are explicitly enumerated for creator page views, creator link clicks, affiliate clicks, collection opens, download views/interactions, and product views/interactions;
- each targeted event type accepts only its matching target type;
- referenced creator links, affiliates, collections, downloads, and products must belong to the same site;
- cross-site and cross-tenant target probes fail closed;
- event metadata is an inert bounded string-to-string object with key/value/count/total-size limits;
- executable script content is rejected from metadata;
- analytics reads are tenant/site scoped, newest-first, optionally event-type filtered, and bounded to 1-500 records;
- archived sites cannot accept new analytics events;
- event records intentionally contain no email, user/customer identifier, advertising identifier, IP address, or cross-site identity field;
- no third-party ad-tech profile building, fingerprinting, or cross-tenant tracking is introduced.

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
