# S7-T08 AI Authorization and Administration

## Purpose

S7-T08 centralizes AI capability authorization and tenant administration so Sprint 7 AI features no longer rely on scattered role checks.

The authorization layer builds on the S7-T01 active-user, active-organization, explicit-membership, and optional site boundary.

## Capabilities

The central AI capability matrix defines:

- `view_status`: owner, admin, staff, viewer;
- `draft`: owner, admin, staff;
- `summary`: owner, admin, staff;
- `suggested_reply`: owner, admin, staff;
- `knowledge_search`: owner, admin, staff;
- `view_usage`: owner, admin;
- `manage_settings`: owner, admin.

Unknown capabilities fail closed.

## Viewer behavior

Viewer access is explicitly read-only.

A viewer may inspect tenant AI status and configured limits through the administration facade, but cannot:

- generate AI drafts;
- generate summaries;
- generate suggested replies;
- run knowledge search;
- view detailed usage records;
- change enablement or usage limits.

## Staff behavior

Staff may use approved AI assistance capabilities but may not:

- change tenant AI configuration;
- raise usage limits;
- access detailed tenant AI usage records.

## Owner/admin behavior

Owner and admin roles may:

- manage tenant AI enablement and operational limits;
- view tenant AI status;
- inspect bounded tenant-scoped usage records;
- use approved AI assistance features.

Administration functions enforce authorization server-side and do not rely on hidden UI controls.

## Site/resource state

Site-scoped AI capability checks fail closed for missing or archived sites.

Revoked memberships, disabled users, and suspended/inactive organizations fail closed through the canonical S7-T01 boundary.

## Administration facade

`ai_admin` exposes:

- `status_for()` for authorized read-only status;
- `update_settings()` for owner/admin configuration;
- `usage_records()` for owner/admin tenant-scoped usage inspection.

Provider credentials are not exposed by the administration facade.

## Feature integration

S7-T08 wires the centralized capability checks into:

- drafting;
- summarization;
- suggested customer replies;
- knowledge search.

Each feature still retains its feature-specific context/visibility safeguards.

## Regression evidence

`tests/test_sprint7_ai_auth_admin.py` verifies:

- least-privilege capability matrix;
- unknown capabilities fail closed;
- viewer read-only status access;
- viewer/staff administration denial;
- owner/admin settings and usage administration;
- staff use without administration;
- revoked membership denial;
- disabled-user denial;
- suspended-organization denial;
- archived-site denial.

Existing focused Sprint 7 feature tests remain green after the centralized authorization integration.

## Handoff to S7-T09

S7-T09 may add operational audit/diagnostic safeguards, status categorization, bounded failure summaries, and AI kill-switch documentation. It must use this centralized authorization/admin layer rather than reintroducing independent role checks.
