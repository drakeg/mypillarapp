# Regression Test Plan

## Protected Areas

The following are regression-critical:

- admin login;
- admin dashboard route and appearance;
- admin navigation;
- customer/admin session separation;
- messaging persistence;
- SES notifications;
- SSM-backed credentials;
- Caddy proxying;
- Terraform file organization.

## Minimum Regression Suite

Run after every application change:

1. `python3 -m py_compile` on changed Python files.
2. Public homepage returns 200.
3. `/admin` redirects when logged out.
4. Admin login succeeds.
5. `/admin` returns dashboard after login.
6. `/admin/inbox` remains accessible in the same session.
7. Customer login remains separate.
8. Contact and chat submissions succeed.
9. Existing conversations remain readable.
10. No protected CSS or admin files changed unless explicitly in scope.
