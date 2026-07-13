# Deployment Controls

- `main` must represent the intended release.
- Protected subsystems require regression testing.
- Infrastructure plans must be reviewed for replacement, deletion, and cost.
- Secrets must come from approved stores.
- Manual server edits are emergency-only and must be reconciled into source immediately.
- A rollback point must be identified before deployment.
- Post-deployment verification is mandatory.
