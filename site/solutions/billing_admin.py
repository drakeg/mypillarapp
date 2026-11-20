from __future__ import annotations

from dataclasses import dataclass

import billing_boundary
import billing_checkout
import billing_invoices
import billing_plans
import billing_subscriptions


@dataclass(frozen=True)
class BillingAdminOverview:
    organization_slug: str
    assignment: billing_plans.TenantPlanAssignment | None
    current_subscription: billing_subscriptions.BillingSubscription | None
    recent_invoices: tuple[billing_invoices.BillingInvoice, ...]
    available_plans: tuple[billing_plans.BillingPlan, ...]
    provider_customer: billing_checkout.ProviderCustomer | None


def overview(
    user_id: int,
    organization_slug: str,
    *,
    invoice_limit: int = 20,
    provider_name: str = 'stripe',
) -> BillingAdminOverview:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    assignment = billing_plans.get_assignment(scope.organization_slug)
    subscription = billing_subscriptions.current_subscription(
        scope.organization_slug
    )
    invoices = billing_invoices.list_invoices(
        user_id,
        scope.organization_slug,
        limit=invoice_limit,
    )
    plans = billing_plans.list_plans(scope.organization_slug)
    customer = billing_checkout.get_provider_customer(
        scope.organization_slug,
        provider_name,
    )
    return BillingAdminOverview(
        organization_slug=scope.organization_slug,
        assignment=assignment,
        current_subscription=subscription,
        recent_invoices=tuple(invoices),
        available_plans=tuple(plans),
        provider_customer=customer,
    )


def assign_plan(
    user_id: int,
    organization_slug: str,
    plan_slug: str,
) -> BillingAdminOverview:
    billing_plans.assign_plan(
        user_id,
        organization_slug,
        plan_slug,
    )
    return overview(user_id, organization_slug)


def configure_provider_price(
    user_id: int,
    organization_slug: str,
    *,
    plan_slug: str,
    provider_name: str,
    price_ref: str,
) -> BillingAdminOverview:
    billing_checkout.configure_plan_price(
        user_id,
        organization_slug,
        plan_slug=plan_slug,
        provider_name=provider_name,
        price_ref=price_ref,
    )
    return overview(
        user_id,
        organization_slug,
        provider_name=provider_name,
    )


def create_checkout(
    user_id: int,
    organization_slug: str,
    *,
    provider,
    plan_slug: str,
    customer_email: str,
    customer_name: str,
    success_url: str,
    cancel_url: str,
    allowed_return_hosts: set[str] | None = None,
) -> billing_checkout.CheckoutSession:
    billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    return billing_checkout.create_checkout_session(
        user_id,
        organization_slug,
        provider=provider,
        plan_slug=plan_slug,
        customer_email=customer_email,
        customer_name=customer_name,
        success_url=success_url,
        cancel_url=cancel_url,
        allowed_return_hosts=allowed_return_hosts,
    )
