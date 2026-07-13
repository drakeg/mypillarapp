# Security Test Plan

## Authentication

- Reject incorrect passwords.
- Reject expired verification/reset tokens.
- Prevent token reuse.
- Verify secure cookie attributes.
- Confirm customer cookie cannot authenticate admin routes.
- Confirm admin cookie cannot impersonate a customer.

## Input Handling

- Test HTML/script injection in every text field.
- Test SQL metacharacters.
- Test oversized requests.
- Test invalid JSON and malformed form data.
- Test path traversal attempts.
- Test unauthorized conversation tokens.

## Infrastructure

- Confirm only required inbound ports are open.
- Confirm SSH can be disabled through configuration.
- Confirm fail2ban and host protections remain active.
- Confirm SSM secrets are not in Terraform state or logs.
- Confirm the EC2 role has least-privilege access.
- Confirm TLS certificate and redirect behavior.
