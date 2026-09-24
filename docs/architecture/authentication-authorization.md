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
- separate signed admin cookie carrying the explicit `platform_super_admin` scope;
- optional emergency token for controlled platform recovery;
- tenant lifecycle, managed sites, and platform settings require platform-super-admin authorization;
- no customer or tenant-membership cookie grants platform access.

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
- request handlers consume the resolved tenant context rather than re-reading a legacy home-organization session;
- the effective tenant role is read from the membership, not the legacy user role;
- revoked or missing memberships are denied;
- the bootstrap platform admin is an explicit `platform_super_admin` boundary;
- tenant membership roles never imply platform administration;
- tenant identifiers are derived from trusted server context, not blindly accepted from clients.
