# Pipeline Design

## Application Checks

```bash
python3 -m py_compile site/solutions/*.py
```

Future automated tests should use `pytest`.

## Terraform Checks

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

A production plan uses the configured remote backend and credentials.

## Security Checks

- secret scanning;
- dependency scanning when dependencies are introduced;
- static analysis;
- Terraform security checks;
- container image scanning when practical.

## Deployment

Production deployment remains explicit until automated promotion is proven safe.
