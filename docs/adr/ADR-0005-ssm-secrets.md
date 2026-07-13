# ADR-0005 — SSM Parameter Store for Bootstrap Secrets

- Status: Accepted
- Decision: store bootstrap admin username, password hash, session secret, and emergency token in SSM.
- Rationale: consistent deployments across workstations without secrets in Terraform state.
