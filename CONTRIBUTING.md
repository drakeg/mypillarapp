# Contributing

## Working agreement

- `main` is the stable source of truth.
- Verify the current repository before every implementation.
- Implement only the active Sprint step.
- Modify only files directly required by that step.
- Do not perform unrelated cleanup.
- Do not change admin routes, authentication, dashboard, CSS, Terraform, or infrastructure unless explicitly in scope.
- Terraform variables belong in `variables.tf`.
- Terraform outputs belong in `outputs.tf`.
- Every code delivery must identify changed files and validation performed.

## Code workflow

1. Read the active Sprint specification.
2. Confirm the requirement, acceptance test, and deliverable identifiers.
3. Verify the repository baseline.
4. Create a focused branch unless the owner explicitly authorizes direct-to-main work.
5. Implement the minimum complete change.
6. Run targeted and regression tests.
7. Update documentation and changelog.
8. Review the exact changed-file list.
9. Merge only after acceptance evidence is available.

## Documentation workflow

Documentation-only phases may be committed directly to `main` when explicitly authorized.
