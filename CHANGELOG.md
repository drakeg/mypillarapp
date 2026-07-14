# Changelog

All notable changes to the product and its engineering system are recorded here.

The format follows Keep a Changelog principles. Formal releases will use Semantic Versioning.

## Unreleased

### Added

- Sprint 1 automated regression suite for customer authentication, profile management, session invalidation, dashboard counts, and conversation authorization.
- One-command regression test runner through `make test`.

- Authenticated customer conversation and service-request history pages.
- Customer-owned conversation detail pages with chronological message history.
- Customer conversation authorization by signed-in account email.
- Dashboard links to complete request and conversation history.

- Sprint 1 customer dashboard activity counts and recent activity.
- Customer profile editing.
- Authenticated customer password changes.
- Customer-session invalidation after password changes.

- Complete SDLC documentation baseline.
- Product vision, PRD, roadmap, epics, stories, and sprint plan.
- Architecture, AWS, API, testing, operations, CI/CD, and release documentation.
- Architecture Decision Record set.
- Development workflow and repository governance rules.

### Current implementation baseline

- Public Mad Mallard Solutions site.
- Contact and service-request intake.
- Async customer conversations and response feedback.
- Customer authentication foundation and dashboard.
- Bootstrap admin dashboard and inbox.
- Terraform-managed AWS deployment.
- S3 remote state, SES, Caddy, Docker, and SSM-backed admin secrets.
