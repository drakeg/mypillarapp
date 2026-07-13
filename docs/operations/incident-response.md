# Incident Response

## Severity

- SEV-1: outage, data loss, credential exposure.
- SEV-2: authentication, admin, messaging, or deployment failure.
- SEV-3: partial feature or notification failure.
- SEV-4: cosmetic/low impact.

## Process

1. Confirm impact and severity.
2. Stop risky deployments.
3. Preserve logs, current database, and state.
4. Restore last known-good release if appropriate.
5. Rotate credentials when exposure is possible.
6. Verify data integrity and customer/admin flows.
7. Record timeline, cause, remediation, and prevention.
8. Add tests or ADR updates.
