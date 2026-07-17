# ADR-0017: Reversible Tenant Lifecycle

## Status

Accepted

## Context

The platform needs operational controls for temporarily disabling a tenant and for retiring a tenant without destroying customer, conversation, configuration, or audit data. Hard deletion would make accidental recovery difficult and would create unnecessary risk before formal retention and deletion policies exist.

## Decision

Tenant lifecycle changes are represented through organization status and domain activation state.

- **Suspend** changes the organization status to `inactive`, disables all tenant domains, and revokes active sessions and authentication tokens.
- **Reactivate** changes the organization status to `active` and re-enables the tenant's existing domains.
- **Archive** changes the organization status to `archived`, disables all tenant domains, and revokes active sessions and authentication tokens.
- The primary `solutions` tenant cannot be suspended or archived through this service.
- Lifecycle actions preserve tenant users, conversations, settings, branding, and domain records.
- Hard deletion is deferred until retention, export, recovery, and legal deletion requirements are defined.

## Consequences

- Tenant access can be stopped immediately without destructive data changes.
- Existing sessions and password or verification tokens cannot remain usable after suspension or archival.
- Reactivation is straightforward because domain and tenant records remain available.
- Archived data continues to consume storage until a future retention process is implemented.
- Administration UI and audit-event persistence remain separate follow-up work.
