# Development Workflow

- Status: Approved
- Applies to: all future coding sessions

## Source of truth

The current `main` branch is the source of truth.

Before every implementation:

1. verify that the repository contains the expected baseline;
2. proceed silently when it matches;
3. stop and report only when it does not match.

## Change rules

- Targeted changes only for the active Sprint step.
- Delta ZIPs contain changed files and a manifest.
- No full-project replacements.
- No unrelated cleanup.
- No admin dashboard, admin routes, admin authentication, CSS, Terraform, or infrastructure changes unless directly required.
- Terraform variables stay in `variables.tf`.
- Terraform outputs stay in `outputs.tf`.

## Delivery content

Every delivery identifies:

- active requirement/story;
- changed files;
- intentional non-changes;
- tests performed;
- deployment or migration steps;
- rollback consideration.

## Protected baseline

The stable admin architecture is protected. Historical files must never be used to reconstruct it piecemeal.
