# ADR-0008 — Membership-Based Tenant Authorization

- Status: Accepted target
- Decision: organization authorization uses memberships and roles, not a global `is_admin`.
- Consequence: one user may administer multiple organizations with different roles.
