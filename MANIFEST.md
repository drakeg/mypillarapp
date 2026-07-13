# Sprint 1 Customer Dashboard and Profile Completion

## Active scope

- Sprint: 1 — Single-Business MVP
- Stories: US-007 Customer Dashboard, US-008 Manage Profile
- Requirements: PRD-R05, PRD-R06
- Acceptance tests: S1-T09, S1-T10

## Patch changes

- `site/solutions/server.py`
  - Adds authenticated `GET /profile`.
  - Adds authenticated `POST /profile`.
  - Keeps all `/admin/*` routes unchanged.
- `site/solutions/tenant_auth.py`
  - Adds dashboard counts and recent customer activity.
  - Adds profile updates.
  - Adds authenticated password changes.
  - Invalidates all customer sessions after password changes.
- `CHANGELOG.md`
  - Records the Sprint 1 completion work.

## Intentionally unchanged

- Admin routes, admin login, dashboard, and CSS.
- Public homepage and public navigation.
- Terraform and AWS infrastructure.
- Caddy, SSM, SES configuration.
- Database schema.

## Apply

From the repository root:

```bash
git apply --check sprint1-customer-dashboard-profile.patch
git apply sprint1-customer-dashboard-profile.patch
```

## Validate

```bash
python3 -m py_compile site/solutions/server.py site/solutions/tenant_auth.py
git diff --check
git status --short
```

Expected changed files:

```text
M CHANGELOG.md
M site/solutions/server.py
M site/solutions/tenant_auth.py
```

## Rollback

Before committing:

```bash
git restore CHANGELOG.md site/solutions/server.py site/solutions/tenant_auth.py
```

After committing, revert the focused commit.
