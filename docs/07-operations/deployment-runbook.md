# Deployment Runbook

## Preconditions

- Working tree is clean.
- `main` contains the intended release.
- AWS credentials are valid.
- Terraform backend is initialized.
- Required SSM parameters exist.
- The deployment has a documented rollback point.

## Standard Deployment

```bash
git switch main
git pull --ff-only
make tf-plan ENV=prod
make tf-apply ENV=prod
```

Optional intentional auto-approval:

```bash
make tf-applya ENV=prod
```

## Verification

```bash
curl -I http://pillar.madmallards.com
curl -I https://pillar.madmallards.com
```

On EC2:

```bash
systemctl status madmallard-app --no-pager
systemctl status madmallard-caddy --no-pager
docker ps
docker logs madmallard-app --tail=100
docker logs madmallard-caddy --tail=100
```

## Failure Rule

Do not manually patch production application files as the normal fix. Correct the source of truth and redeploy.
