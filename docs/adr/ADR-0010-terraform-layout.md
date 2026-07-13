# ADR-0010 — Terraform File Layout

- Status: Accepted
- Decision: variables are declared only in `variables.tf`; outputs only in `outputs.tf`.
- Consequence: duplicate declarations in `main.tf` are defects.
