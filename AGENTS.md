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
