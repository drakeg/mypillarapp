# Regression Checklist

## Admin protected baseline

- [ ] `/admin` redirects to `/admin/login` when logged out
- [ ] valid username/password works
- [ ] successful login redirects to `/admin`
- [ ] dashboard, not inbox-only page, is displayed
- [ ] dashboard navigation links remain authenticated
- [ ] inbox/request/conversation actions work
- [ ] approved admin CSS and layout remain intact

## Customer

- [ ] registration
- [ ] verification
- [ ] login/logout
- [ ] reset
- [ ] dashboard
- [ ] profile/password

## Public

- [ ] homepage
- [ ] contact form
- [ ] chat
- [ ] conversation
- [ ] feedback

## Deployment

- [ ] Terraform fmt/validate
- [ ] no duplicate variable/output
- [ ] no unexpected EC2 replacement
- [ ] Caddy and app containers healthy
- [ ] HTTPS works
