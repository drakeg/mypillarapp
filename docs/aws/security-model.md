# AWS Security Model

## Identity

- operators authenticate through their own AWS credentials;
- EC2 uses an IAM role;
- IAM policies are least privilege;
- multiple SSH public keys may be installed through the approved mechanism;
- SSM is preferred for operational access where practical.

## Network

- only required ports are open;
- HTTPS is public;
- SSH exposure is a documented temporary tradeoff due to changing operator locations;
- fail2ban and host hardening are expected;
- database is not exposed publicly.

## Secrets

- bootstrap admin data lives in SSM;
- secrets are read at deployment/runtime;
- secrets are not embedded in Docker command lines, Git, or Terraform state;
- rotation is documented.

## Application

- Caddy handles TLS;
- customer/admin cookies are secure and isolated;
- passwords use PBKDF2-SHA256;
- administrative operations require authentication.
