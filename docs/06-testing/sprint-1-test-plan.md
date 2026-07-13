# Sprint 1 Test Plan

## Scope

Validate the single-business MVP for Mad Mallard Solutions.

## Public Site

- Landing page loads over HTTPS.
- HTTP redirects to HTTPS.
- Static assets load.
- Contact form validates and stores a request.
- Async chat creates a private conversation.
- Customer conversation link can be reopened.
- Feedback can be submitted once permitted.

## Customer Authentication

- Registration accepts valid data.
- Duplicate email is rejected safely.
- Verification email is sent through SES.
- Verification token activates the account.
- Unverified accounts cannot authenticate if that policy is enabled.
- Login creates a secure session.
- Logout clears the session.
- Forgot-password response does not disclose account existence.
- Reset token changes the password and expires.
- Profile can be updated.
- Password change invalidates existing sessions.

## Customer Dashboard

- Requires authentication.
- Displays the authenticated user's data only.
- Shows request and conversation counts.
- Shows recent activity.
- Links open only authorized resources.

## Admin

- `/admin` redirects unauthenticated users to `/admin/login`.
- Valid credentials open the dashboard.
- Login redirects to the dashboard, not the inbox.
- All dashboard links retain authentication.
- Inbox, requests, leads, CRM, sites, and settings load.
- Admin can reply, update status, add notes, and close a conversation.
- Admin UI and CSS match the approved stable baseline.

## Infrastructure

- Terraform initializes with the S3 backend.
- Terraform validates.
- Plan does not unexpectedly replace EC2.
- SSM parameters are readable only by the required role.
- Caddy serves HTTPS.
- App and Caddy services restart successfully.
