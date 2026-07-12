# Sprint 1 Authentication Navigation Delta

## Modified
- `site/solutions/index.html`
  - Adds an account-navigation insertion point to the public header.
- `site/solutions/server.py`
  - Renders Sign In/Register links for visitors.
  - Renders Dashboard/account name/Logout links for authenticated tenant users.

## Explicitly unchanged
- All `/admin/*` routes and admin authentication logic
- Admin dashboard markup and styling
- Terraform and AWS infrastructure
- Messaging, contact, SES, Caddy, and SSM behavior
