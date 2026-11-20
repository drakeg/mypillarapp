# S8-T09 Billing Administration and Onboarding

## Purpose

S8-T09 adds an owner/admin-only billing administration facade that consolidates the Sprint 8 plan, subscription, invoice, provider-customer, and checkout boundaries into one tenant-safe application service.

## Billing overview

`billing_admin.overview()` returns a bounded, tenant-scoped view containing:

- current plan assignment;
- current application subscription;
- recent invoices;
- active tenant-owned plans;
- provider customer reference.

The overview requires owner/admin billing scope. Staff and cross-tenant callers fail closed.

## Administrative actions

The facade currently exposes:

- plan assignment;
- provider-price configuration;
- checkout-session initiation.

Each action delegates to the existing tenant-safe Sprint 8 boundaries rather than duplicating provider or authorization logic.

## Authorization

All facade reads and mutations require `billing_boundary.authorize_billing_admin()`.

This preserves:

- active user/membership checks;
- active organization checks;
- owner/admin role requirements;
- tenant isolation.

Provider identifiers remain references only.

## Checkout onboarding

Checkout initiation through the admin facade still requires:

- same-tenant active plan;
- configured provider price;
- authorized owner/admin;
- allow-listed HTTPS success/cancel URLs.

A checkout response remains non-authoritative until authenticated webhook reconciliation.

## Billing history

The admin overview uses the S8-T07 invoice API, which:

- is tenant scoped;
- is owner/admin only;
- caps reads;
- stores no raw payment credentials.

## Regression evidence

`tests/test_sprint8_billing_admin.py` verifies:

- owner/admin billing overview access;
- staff read/mutation denial;
- cross-tenant denial;
- plan assignment reflected in overview;
- provider-price mapping remains tenant scoped;
- checkout initiation requires billing-admin scope.

This facade is ready to back the platform billing UI without exposing lower-level provider primitives directly.
