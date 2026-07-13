# Git Workflow

## Source of Truth

GitHub `main` is the stable source of truth.

## Code Changes

- Create a focused feature branch.
- Modify only files required by the active Sprint step.
- No unrelated cleanup.
- Protect admin, CSS, Terraform, and infrastructure unless explicitly in scope.
- Review the exact changed-file list.
- Merge only after validation.

## Documentation Changes

Documentation may be committed directly to `main` when explicitly requested.

## Recovery

Tag known-good milestones. Never reconstruct a stable subsystem from mismatched historical files.
