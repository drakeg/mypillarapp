# Test Strategy

## Objectives

- prove each requirement;
- prevent admin regressions;
- protect authentication and tenant boundaries;
- verify deployment and rollback;
- keep testing proportional to risk.

## Layers

1. Static/syntax checks
2. Unit tests
3. Database integration tests
4. HTTP route tests
5. Authentication/security tests
6. Terraform validation/security checks
7. Deployment smoke tests
8. End-to-end acceptance tests
9. Regression suite

## Release gates

- changed Python files compile;
- targeted tests pass;
- admin regression suite passes;
- changed-file list matches scope;
- Terraform plan reviewed when applicable;
- documentation/changelog updated;
- rollback point identified.
