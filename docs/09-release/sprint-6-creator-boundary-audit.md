# S6-T01 Creator Tenant/Site Boundary and Legacy Audit

## Purpose

Define the ownership and public-resolution boundary for Sprint 6 creator records before introducing creator-commerce persistence.

## Canonical ownership

Creator records introduced after this audit must be owned through:

`auth_organizations → site_builder_sites → creator record`

Organization slug or hostname text alone is not sufficient ownership. Canonical organization/site identifiers remain authoritative.

## Authoring boundary

Creator authoring requires:

- an active organization;
- a non-archived site owned by that organization;
- an active membership for the authoring user in that same organization.

Role-specific creator permissions are deferred to S6-T08. S6-T01 only establishes that creator authoring can never occur without an active tenant membership.

## Public boundary

Public creator reads require:

- an active domain;
- an active organization;
- a domain mapped to a site owned by that organization;
- a published site.

This is intentionally stricter than the generic Site Builder resolver, which may resolve non-archived draft sites for internal compatibility.

## Existing content reviewed

Sprint 6 can potentially reuse or migrate metadata from:

- Site Builder pages;
- Site Builder navigation;
- Site Builder media references;
- Site Builder services and their legacy display-only `price_text`;
- existing domain-to-site assignments.

No canonical affiliate-link, creator-profile, collection, digital-product, storefront-product, or creator-analytics tables exist before Sprint 6.

## URL compatibility risk

Existing Site Builder navigation and media validation permits `http://` external URLs. It also does not explicitly reject URLs with embedded credentials.

Those records are valid legacy Site Builder data but are not automatically safe Sprint 6 creator-commerce migration inputs.

The S6-T01 audit therefore reports:

- external navigation links;
- external media sources;
- plain-HTTP URLs;
- credential-bearing URLs;
- active domain/site ownership mismatches;
- published sites without an active domain.

Sprint 6 creator/affiliate records will require stricter safe-link behavior. Unsafe legacy records must be reported for review rather than silently normalized or migrated.

## Content-body compatibility

Existing Site Builder page bodies are stored as content and public rendering escapes them. S6-T01 does not parse page-body text into creator links, affiliate records, products, or executable content.

Migration must never infer commerce metadata from arbitrary page body text.

## Commerce boundary

Legacy Site Builder `price_text` is presentation text only. It must not be interpreted as a canonical product price, currency, entitlement, or payment instruction.

Sprint 6 product foundations may introduce structured integer-cent price metadata, but payment capture, invoices, subscriptions, taxes, and licensing remain Sprint 8 work.

## Migration rules

Future S6-T10 compatibility migration must:

1. remain explicit and non-destructive;
2. require a clean or reviewed S6-T01 audit;
3. preserve owner edits to canonical Sprint 6 records;
4. reject or report unsafe external URLs rather than guessing replacements;
5. preserve current Site Builder public content until an explicit cutover decision;
6. never auto-create payment behavior from legacy services or price text.
