# S8-T03 Subscription Lifecycle Foundation

S8-T03 adds application-owned subscriptions with explicit tenant ownership, same-tenant plan references, deterministic lifecycle rules, optional opaque provider references, and append-only transition history.

Supported states: `trialing`, `active`, `past_due`, `suspended`, and `canceled`.

Allowed transitions are explicit:
- trialing → active/canceled/suspended
- active → past_due/canceled/suspended
- past_due → active/canceled/suspended
- suspended → active/canceled
- canceled → terminal

New subscriptions may start only as trialing or active.

Each organization may have one non-canceled current subscription. Canceled subscriptions are retained as history and a new subscription may later be created.

Cancellation does not delete tenant data or remove the tenant plan assignment. Provider customer/subscription references are optional opaque identifiers only and cannot authorize application access.

All lifecycle mutations require owner/admin billing scope. Staff cannot administer subscriptions. Cross-tenant lookups and plan references fail closed.

Transition history records the actor, previous state, new state, reason, and timestamp. This history is application-owned and does not imply provider authority.

No Stripe calls, webhooks, charges, invoices, or payment credentials are introduced in S8-T03.
