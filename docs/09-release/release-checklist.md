# Release Checklist

## Before

- [ ] Scope approved
- [ ] Working tree clean
- [ ] Tests pass
- [ ] Admin regression suite passes
- [ ] `make test-sprint2` passes
- [ ] Full `make test` passes
- [ ] Terraform plan reviewed when applicable
- [ ] Secrets and configuration verified
- [ ] Backup/recovery readiness confirmed
- [ ] Changelog updated
- [ ] Rollback point identified

## After

- [ ] HTTP redirects to HTTPS
- [ ] Homepage returns 200
- [ ] Configured tenant domains resolve correctly
- [ ] Unknown tenant host is rejected
- [ ] Customer authentication works
- [ ] Tenant membership authorization/revocation works
- [ ] Admin dashboard works
- [ ] Platform tenant administration requires platform-super-admin access
- [ ] Messaging works
- [ ] Notifications work
- [ ] Logs show no new errors
- [ ] Release tagged
- [ ] Release notes published
