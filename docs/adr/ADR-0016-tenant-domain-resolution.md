# ADR-0016: Resolve tenants by persisted host mappings

- **Status:** Accepted
- **Date:** 2026-07-14
- **Sprint:** Sprint 2 — Multi-tenant

## Context

The platform must host multiple Mad Mallard businesses without allowing requests, settings, or future business data to fall through to another tenant. The existing authentication schema already persists organizations, but it does not provide domain mappings or tenant-scoped configuration.

## Decision

Add a tenant foundation alongside the existing `auth_organizations` records:

- `tenant_domains` maps normalized host names to one organization.
- `tenant_settings` stores JSON-encoded configuration by organization and key.
- Tenant resolution accepts a request host, removes scheme, port, path, case differences, and a trailing dot, then performs an exact active-domain lookup.
- An unknown host resolves to no tenant. It must not silently fall back to the Solutions tenant or any other tenant.
- `pillar.madmallards.com` is seeded as the primary domain for the existing `solutions` organization.

## Consequences

- Domain and setting data remain isolated by organization ID.
- Future request routing can depend on one explicit tenant-resolution boundary.
- Additional domains can be registered without changing infrastructure code.
- Application routes are not made tenant-aware by this decision alone; that integration is a subsequent Sprint 2 step.
