# Repository Guidance

## Source of truth

Treat this repository as the authoritative Mad Mallard Platform  project record. Do not rely on an uncommitted chat summary when repository documentation exists.

## Scope discipline

- Work only within the active, approved sprint.
- Do not silently expand requirements.
- Preserve approved sprint wording.
- Propose scope changes through a documented change request.
- Keep unrelated changes out of a sprint branch or pull request.

## Delivery discipline

Every implementation change must identify:

- the sprint and requirement it satisfies
- the acceptance tests used
- the validation result
- any known limitation or deferred work

## Repository workflow

- During the initial documentation-only phase, focused documentation commits may be made directly to `main`.
- Once application code or infrastructure implementation begins, use feature branches and pull requests.
- Prefer small, reviewable commits.
- Update documentation with the behavior or decision it describes.
- Record material architecture choices as ADRs under `docs/adr/`.
- Do not mark work complete until its acceptance tests pass.


## README badge maintenance

- `drakeg/madmallard-repository-standards` is the source of truth for repository badge policy.
- Keep the bounded `madmallard-badges` block immediately below the root README H1.
- Inspect manifests, dependency declarations, Docker/Compose files, Terraform/deployment configuration, GitHub Actions, releases, and license files before adding or changing a badge.
- Technology badges require repository evidence. Never claim an unverified version.
- GitHub Actions, releases, licenses, issues, and pull-request status must use dynamic badges; never hardcode passing status.
- Omit unsupported claims rather than adding speculative badges. In particular, do not add license, release, or security-status badges unless corresponding repository evidence exists.
- When supported technologies, workflows, licensing, deployment configuration, or release state change, update the badges in the same normal development PR.
- Run `python3 scripts/badges.py --mode dry-run`, then `--mode write` when changes are expected, and always finish with `python3 scripts/badges.py --mode check`.


## Community configuration maintenance

- Keep GitHub Sponsors configuration in `.github/FUNDING.yml`.
- Keep discussion category forms in `.github/DISCUSSION_TEMPLATE/` aligned with the enabled GitHub Discussions categories.
- Route exploratory questions and ideas to Discussions; use Issues for confirmed defects and actionable work.
- Preserve `SUPPORT.md` and README community links when repository structure changes.
- Never place secrets, tokens, private customer data, or vulnerability details in public community templates.
