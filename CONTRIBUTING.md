# Contributing

## Required standards

Before contributing, read:

- [Coding Standards](docs/governance/coding-standards.md)
- [Sprint Standards](docs/governance/sprint-standards.md)
- [Development Workflow](docs/governance/development-workflow.md)
- [Definition of Ready](docs/governance/definition-of-ready.md)
- [Definition of Done](docs/governance/definition-of-done.md)

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


## Repository badge validation

README badges follow the centralized standards in `drakeg/madmallard-repository-standards`. Before opening or updating a PR that changes dependencies, workflows, deployment configuration, licensing, or release state:

1. inspect the repository evidence supporting each badge;
2. run `python3 scripts/badges.py --mode dry-run`;
3. run `python3 scripts/badges.py --mode write` when the generated block should change;
4. review the README diff; and
5. run `python3 scripts/badges.py --mode check`.

The badge generator preserves all README content outside the bounded `madmallard-badges` block. Missing evidence means the badge should be omitted rather than guessed.


## Discussions and support

Use GitHub Discussions before opening an Issue when the topic is exploratory, a question, or an early product idea:

- Q&A: https://github.com/drakeg/mypillarapp/discussions/categories/q-a
- Ideas: https://github.com/drakeg/mypillarapp/discussions/categories/ideas
- General: https://github.com/drakeg/mypillarapp/discussions

Use Issues for confirmed bugs, accepted/scoped work, and concrete repository tasks.

Do not post secrets, credentials, tokens, private customer information, or vulnerability details in public Discussions or Issues.

## Sponsorship maintenance

The repository Sponsor button is configured through `.github/FUNDING.yml`. Keep it aligned with the repository owner's active GitHub Sponsors account. Sponsorship must not be presented as influencing merge decisions, security handling, technical conclusions, or roadmap truthfulness.
