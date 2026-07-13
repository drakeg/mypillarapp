# Operations Runbook

## Standard deployment

```bash
git switch main
git pull --ff-only
make tf-plan ENV=prod
make tf-apply ENV=prod
```

Intentional auto-approval:

```bash
make tf-applya ENV=prod
```

## Verify

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

## Credential update

1. Run `scripts/set-admin-parameters.sh`.
2. Confirm with `scripts/show-admin-parameter-status.sh`.
3. Trigger/apply the deployment configuration.
4. Verify admin login.
5. Do not expose parameter values in logs.

## Failure rule

Correct source and redeploy. Manual production edits are emergency-only and must be reconciled immediately.
