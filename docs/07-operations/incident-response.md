# Incident Response

## Severity

| Severity | Example |
|---|---|
| SEV-1 | Site unavailable, data loss, credential exposure |
| SEV-2 | Authentication, messaging, or admin failure |
| SEV-3 | Partial feature failure or degraded notifications |
| SEV-4 | Cosmetic or low-impact defect |

## Response

1. Confirm and classify.
2. Preserve logs and evidence.
3. Stop further damaging deployments.
4. Restore the last known-good release when appropriate.
5. Validate data integrity.
6. Document timeline, cause, and corrective action.
7. Add or update tests and ADRs.

## Security Incident

Rotate affected credentials, revoke sessions, review AWS activity, preserve logs, and notify affected parties as required.
