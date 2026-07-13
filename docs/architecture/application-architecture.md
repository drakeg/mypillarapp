# Application Architecture

## Runtime

The application is a lightweight Python HTTP service packaged in Docker. It uses server-rendered HTML and JSON endpoints.

## Main modules

- `server.py` — route dispatch, public/admin rendering, HTTP handling.
- `messaging.py` — conversation, request, message, feedback, and notification behavior.
- `tenant_auth.py` — customer organizations/users/sessions/tokens/profile behavior.
- `form_config.py` — structured form options.
- static HTML/CSS/JS assets.

## Boundary rules

- `server.py` orchestrates HTTP behavior.
- authentication logic belongs in the relevant auth module.
- message persistence belongs in messaging/database helpers.
- secrets enter through runtime configuration, not source.
- future module extraction must preserve route contracts and tests.

## Known technical debt

- `server.py` is large.
- SQL migrations are lightweight.
- automated test coverage needs expansion.
- SQLite backup automation is required before external production use.

These are backlog items, not permission for unrelated refactoring.
