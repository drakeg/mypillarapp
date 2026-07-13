# Coding Standards

## Python

- use type hints for new public functions;
- validate all external input;
- isolate persistence operations;
- never log secrets or raw passwords;
- use secure comparisons for secrets;
- use parameterized SQL;
- keep customer and admin authentication separate;
- add tests for security-sensitive behavior.

## HTML and UI

- preserve accessible labels and keyboard behavior;
- maintain responsive layouts;
- avoid changing stable admin UI outside scope;
- escape user-provided values.

## Shell

- use `set -euo pipefail`;
- quote variables;
- avoid printing secrets;
- validate required tools and environment.

## Terraform

- format and validate;
- avoid embedded secrets;
- review replacements and deletions;
- include cost impact;
- preserve separate variable/output files.
