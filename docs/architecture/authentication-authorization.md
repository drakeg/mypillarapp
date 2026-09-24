# Authentication and Authorization

## Current customer authentication

- database-backed account;
- PBKDF2-SHA256 password hashing;
- email verification token;
- password-reset token;
- opaque customer session cookie;
- session revocation on logout;
- session invalidation after password change.

## Current admin authentication

- separate bootstrap admin identity;
- username, password hash, and session secret loaded from SSM;
- separate signed admin cookie;
- optional emergency token for controlled use;
- no customer cookie grants admin access.

## Current Sprint 2 authorization model

```text
User
  ├── Membership: Mad Mallard Solutions / Owner
  ├── Membership: Mad Mallard Personal Training / Viewer
  └── Membership: Mad Mallards Adventures / Admin

Platform Role
  └── Platform Super Administrator
```

## Role principles

- permissions are scoped to an organization;
- one user can have multiple memberships;
- platform administration is explicit and separate;
- tenant login requires an active organization membership;
- authenticated tenant request context requires an active organization membership;
- the effective tenant role is read from the membership, not the legacy user role;
- revoked or missing memberships are denied;
- the bootstrap platform admin remains a separate authentication boundary;
- tenant identifiers are derived from trusted server context, not blindly accepted from clients.
