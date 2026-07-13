# Authentication and Sessions

## Customer Authentication

Customer accounts are database-backed. Passwords are stored as PBKDF2-SHA256 hashes. Email verification and password reset use expiring, single-use tokens.

Customer sessions:

- use a dedicated customer cookie;
- are unrelated to admin sessions;
- are invalidated on logout;
- should be invalidated after a password change;
- must use `Secure`, `HttpOnly`, and `SameSite=Lax`.

## Bootstrap Admin Authentication

The bootstrap admin remains separate from customer authentication during the MVP.

Credentials are loaded from AWS Systems Manager Parameter Store:

- username;
- password hash;
- session signing secret;
- optional emergency token.

Admin sessions use their own signed cookie.

## Future Authorization

Sprint 2 introduces:

- organizations;
- users;
- organization memberships;
- organization-scoped roles;
- a platform-wide super-administrator role.

A global `is_admin` boolean is not sufficient for the multi-tenant design.
