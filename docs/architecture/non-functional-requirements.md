# Non-Functional Requirements

## Availability

Sprint 1 targets practical single-instance availability. Multi-AZ is not required.

## Performance

- ordinary HTML/API responses should normally complete in under 500 ms excluding external email delivery;
- database queries must remain indexed and bounded;
- page assets should remain modest.

## Security

- HTTPS only;
- adaptive password hashing;
- secure cookies;
- least-privilege IAM;
- secrets outside source/Terraform state;
- input validation and output escaping.

## Privacy

- collect only needed business/customer information;
- do not expose private conversations publicly;
- avoid logging message bodies unless operationally necessary;
- define retention/deletion before external SaaS launch.

## Cost

The baseline should remain within the low single-digit to low double-digit monthly range where AWS pricing and usage allow.

## Recoverability

Source, Terraform state, secrets, database, and uploads must have documented recovery paths.
