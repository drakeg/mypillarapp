# ADR-0003 — SQLite for MVP

- Status: Accepted
- Decision: use SQLite for the single-instance MVP.
- Rationale: zero additional AWS service cost and adequate current concurrency.
- Consequence: automated backup and restore are required; multi-instance deployment requires migration.
