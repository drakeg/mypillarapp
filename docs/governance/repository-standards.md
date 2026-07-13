# Repository Standards

## Required root content

- README
- CONTRIBUTING
- CHANGELOG
- Makefile
- application source
- Terraform source
- scripts
- docs

## Terraform

Each module uses:

- `main.tf` for resources and data;
- `variables.tf` for variables;
- `outputs.tf` for outputs;
- optional `locals.tf`, `versions.tf`, and provider-specific files.

Duplicate declarations across files are prohibited.

## Documentation

Approved decisions and Sprint specifications live on `main`. Superseded documents remain in history and link to replacements.

## Delivery archives

Delta ZIPs preserve repository-relative paths and include `MANIFEST.md`.
