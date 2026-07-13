# Test Strategy

## Objectives

Testing must protect the stable admin experience, customer authentication, messaging, notifications, and Terraform deployment.

## Test Layers

1. **Static checks** — syntax, formatting, configuration validation.
2. **Unit tests** — password hashing, tokens, validation, data access.
3. **Integration tests** — SQLite, SES calls, SSM configuration, routing.
4. **HTTP smoke tests** — public, customer, and admin routes.
5. **Infrastructure tests** — `terraform fmt`, `validate`, and reviewed plans.
6. **Acceptance tests** — end-to-end user and admin workflows.
7. **Regression tests** — protected admin and deployment behavior.

## Quality Gates

A change is releasable only when:

- affected tests pass;
- protected workflows pass;
- no unexpected files changed;
- Terraform replacement is reviewed if infrastructure is touched;
- rollback instructions are known;
- documentation and changelog are updated.
