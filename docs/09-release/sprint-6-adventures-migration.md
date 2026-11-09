# S6-T10 Adventures Compatibility Migration

## Purpose

S6-T10 provides an explicit, opt-in compatibility migration for the Mad Mallards Adventures main site. It stages safe legacy Site Builder data into canonical Sprint 6 creator records without publishing anything or changing the live site.

## Migration behavior

The migration is intentionally additive and non-destructive.

- The Adventures tenant/site is fixed to `adventures/main`; other tenants are never scanned or modified.
- A missing creator profile is staged as `draft` from existing Adventures branding values.
- Existing Site Builder navigation items with safe root-relative or credential-free HTTPS targets are staged as draft creator links.
- Existing non-archived Site Builder pages are represented by draft collection items that link back to their existing public page paths. Page bodies are not copied or parsed.
- Existing non-archived Site Builder media with safe root-relative or credential-free HTTPS sources are represented by draft collection items.
- Existing canonical creator profiles are preserved unchanged.
- A persistent legacy-to-canonical mapping prevents duplicate creation and ensures reruns do not overwrite owner edits.
- Unsafe HTTP, credential-bearing, protocol-relative, empty, or otherwise incompatible targets are reported and not migrated.
- Affiliate semantics are never inferred from labels or URLs. Records that look affiliate-related remain manual-review items because canonical affiliate records require an explicit disclosure and program/network metadata.
- Existing canonical collections that collide with reserved migration collection slugs are preserved and the corresponding legacy rows are reported as unmatched instead of being merged heuristically.

## No-cutover guarantee

Running the migration does **not**:

- publish the Adventures Site Builder site;
- publish creator profiles, links, or collections;
- create or change domains;
- change public routes;
- replace existing Site Builder pages/navigation/media;
- create payments, orders, subscriptions, invoices, entitlements, or checkout behavior.

A separate owner-reviewed publication/cutover decision is required after migration output is inspected.

## Operational use

Run `adventures_creator_migration.migrate_adventures_content()` only after reviewing the S6-T01 creator legacy audit. Review the returned counters and `issues` tuple before publishing any staged canonical record.

Repeated runs are safe: mapped canonical records are not updated, so subsequent owner edits remain authoritative.
