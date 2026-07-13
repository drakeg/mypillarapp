# ADR-0011 — Shared S3 Remote State

- Status: Accepted
- Decision: use the existing shared S3 bucket with project-specific key prefixes.
- Consequence: state paths isolate projects while avoiding another bucket.
