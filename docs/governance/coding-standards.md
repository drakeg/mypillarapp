# Coding Standards

- Status: Approved
- Applies to: all implementation work in this repository
- Reusable baseline: use these principles for other coding projects unless that repository documents a stricter standard.

## General principles

- Prefer the smallest complete change that satisfies the active requirement.
- Preserve existing behavior unless the requirement explicitly changes it.
- Do not mix feature work, refactoring, formatting churn, dependency changes, and unrelated cleanup in one change.
- Favor clear, explicit code over clever abstractions.
- Comments explain intent, constraints, or non-obvious decisions rather than obvious syntax.
- Keep commits and pull requests cohesive and reviewable.

## Python

- Follow standard Python naming and formatting conventions.
- Use type hints for new public functions and complex internal interfaces where they improve correctness.
- Keep functions focused; extract helpers when a function performs multiple independent jobs.
- Avoid mutable default arguments.
- Validate external input before persistence or security-sensitive decisions.
- Use parameterized SQL; never interpolate untrusted values into SQL.
- Close database connections deterministically with context managers or equivalent lifecycle handling.
- Avoid broad exception handling unless the failure is intentionally converted into a safe fallback.
- Never silently swallow authorization, security, or data-integrity failures.
- Never log passwords, session/reset/verification tokens, API keys, secrets, or sensitive payloads.

## Multi-tenant and authorization code

- Every tenant-owned read and write must be scoped by trusted tenant context or tenant identifier.
- User identity alone is not authorization; active membership and effective role must be checked where required.
- Platform administration and tenant authorization remain separate boundaries.
- Cross-tenant behavior requires positive and negative regression tests.
- Request handlers use tenant-aware request/session helpers rather than legacy home-organization assumptions.
- Tenant lifecycle operations preserve data unless destructive behavior is explicitly required and approved.

## HTML and HTTP

- Preserve accessible labels, semantic controls, and keyboard behavior.
- Maintain responsive layouts.
- Escape user-provided values before rendering.
- Use appropriate HTTP status codes and deterministic redirect behavior.
- Treat public identifiers and tokens as untrusted input.
- Preserve established HttpOnly, Secure, and SameSite cookie protections unless an approved requirement changes them.
- Avoid changing stable admin UI/routes outside approved scope.

## Shell

- Use `set -euo pipefail` for non-trivial scripts unless a documented compatibility reason prevents it.
- Quote variables.
- Validate required tools and environment.
- Do not print secrets.
- Make failure states explicit and non-zero.

## Terraform and infrastructure

- Terraform variables belong in `variables.tf`.
- Terraform outputs belong in `outputs.tf`.
- Avoid duplicate resource, variable, provider, or output declarations.
- Run formatting and validation for Terraform changes.
- Review plans before apply and review replacements/deletions carefully.
- Record cost impact when infrastructure changes can affect recurring spend.
- Secrets remain in approved secret/configuration systems, never source control.
- Infrastructure changes include rollback/recovery considerations.

## Dependencies

- Add a dependency only when it provides clear value not reasonably available from the standard library or existing dependencies.
- Keep dependency upgrades separate from unrelated feature work when practical.
- Record compatibility-impacting upgrades in the changelog.
- Never weaken security controls to preserve an obsolete dependency.

## Testing

Every behavior change requires evidence proportional to risk:

- bug fixes should include a regression test that would have failed before the fix when practical;
- tenant/security changes require positive and negative tests;
- migrations require compatibility and rollback consideration;
- new business rules require focused unit/integration coverage;
- protected baseline behavior remains covered by the regression suite.

Prefer behavior tests over incidental source-text assertions. Source-text/AST assertions are appropriate only for intentional architectural invariants.

## Documentation

A change is not complete until affected documentation is updated. At minimum consider:

- Sprint/task status;
- architecture or ADRs;
- test plan;
- changelog;
- deployment/migration steps;
- rollback guidance.

Do not claim production verification unless a production/deployed check was actually performed.

## Merge checklist

Before merge:

1. changed files match approved scope;
2. no secrets or sensitive values were added;
3. targeted tests pass;
4. required regression/CI gates pass;
5. tenant/security boundaries were reviewed where applicable;
6. documentation and changelog are current;
7. deployment/migration/rollback effects are understood;
8. no unrelated cleanup is included.


## Docker configuration convention

- Docker Compose solutions must expose user-configurable host ports through environment variables loaded from a local `.env` file.
- Commit a safe `.env.example` documenting every Docker-related variable required for local startup.
- Never commit the real `.env`; it remains ignored.
- Prefer changing the host-side published port while keeping the container's internal service port stable unless the application itself requires an internal-port override.
- CI should validate that Compose resolves the documented environment variables correctly.
