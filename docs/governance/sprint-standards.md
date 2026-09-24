# Sprint Standards

- Status: Approved
- Applies to: all planned product-development Sprints in this repository
- Reusable baseline: use this structure for other coding projects unless their repository documents a stricter process.

## Required Sprint structure

Every Sprint documents:

- Sprint number and name;
- objective and intended user/business outcome;
- entry criteria;
- locked in-scope work;
- explicit out-of-scope work;
- numbered implementation tasks;
- acceptance criteria;
- testing/evidence requirements;
- deployment or migration impact;
- rollback/recovery expectations;
- exit criteria.

## Task identifiers

Use stable identifiers such as `S2-T14`:

- `S2` means Sprint 2;
- `T14` means task 14 within that Sprint.

Use task identifiers in branch/PR titles, planning documents, tests/evidence where useful, and changelog/release notes when material.

## Scope control

- Only the active Sprint task changes implementation unless the owner explicitly authorizes an exception.
- New ideas discovered during implementation go to the backlog unless required for correctness, security, data integrity, or current acceptance criteria.
- If a prerequisite gap is discovered, create a narrowly scoped task before declaring the Sprint complete.
- Do not pull later-Sprint functionality forward merely because adjacent code is already being edited.
- Documentation/governance corrections explicitly requested by the owner may be handled as focused governance work without redefining product scope.

## Definition of Ready

A Sprint task must meet the repository Definition of Ready before implementation, including testable acceptance criteria, resolved dependencies, security/privacy review, migration impact, and rollback feasibility.

## Implementation cycle

For each task:

1. verify current `main` and open PR state;
2. create a focused branch;
3. implement the minimum complete scope;
4. add/update targeted tests;
5. update affected documentation and changelog;
6. open a PR identifying scope and intentional non-changes;
7. run required CI;
8. fix failures on the same branch;
9. merge only when required evidence is green.

Avoid stacking dependent feature PRs before the previous task merges unless there is a documented reason.

## Testing and evidence

Sprint evidence distinguishes:

- repository/CI evidence;
- local integration evidence;
- deployment evidence;
- production/manual evidence.

A green CI job proves only the commands that job actually executed. Sprint closure must not claim tests or deployment checks that were not run.

Each Sprint test plan should map major acceptance areas to specific automated or manual evidence.

## Sprint completion

A Sprint is complete only when:

- all required tasks are merged;
- acceptance criteria are satisfied;
- targeted and regression tests are green;
- security and tenant-isolation checks pass where applicable;
- documentation and changelog are current;
- release and rollback information is recorded;
- known limitations/deferred work are explicit;
- owner acceptance is recorded when required.

The next Sprint must not silently become active before the current Sprint is formally closed in the Sprint plan.

## CI or regression failures during closure

Do not waive a failing gate. Determine whether the failure is:

- a product defect;
- a stale/incorrect test;
- an environment/tooling defect.

Fix the actual cause in a focused change, rerun the affected gate, and record material findings when they change the engineering baseline.

## Closure record

A Sprint closure record includes:

- final merged commit or release-candidate SHA;
- relevant PR/task range;
- CI/test results;
- deployment/migration status;
- rollback point;
- known limitations and deferred items;
- whether production/manual smoke checks were performed or remain pending.
