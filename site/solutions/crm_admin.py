from __future__ import annotations

from dataclasses import dataclass

import crm_auth
import crm_companies
import crm_contacts
import crm_opportunities
import crm_tasks
import crm_activities
import crm_quotes
import crm_conversation_links


@dataclass(frozen=True)
class CrmSummary:
    organization_slug: str
    companies: int
    contacts: int
    opportunities: int
    tasks: int
    activities: int
    quotes: int
    conversation_links: int


def summary_for(user_id: int, organization_slug: str) -> CrmSummary:
    crm_auth.require(user_id, organization_slug, 'view')
    return CrmSummary(
        organization_slug=organization_slug,
        companies=len(crm_companies.list_companies(organization_slug)),
        contacts=len(crm_contacts.list_contacts(organization_slug)),
        opportunities=len(crm_opportunities.list_opportunities(organization_slug)),
        tasks=len(crm_tasks.list_tasks(organization_slug)),
        activities=len(crm_activities.list_activities(organization_slug)),
        quotes=_count_quotes(organization_slug),
        conversation_links=len(crm_conversation_links.list_links(organization_slug)),
    )


def create_company(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'companies')
    return crm_companies.create_company(organization_slug, **kwargs)


def create_contact(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'contacts')
    return crm_contacts.create_contact(organization_slug, **kwargs)


def create_opportunity(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'opportunities')
    return crm_opportunities.create_opportunity(organization_slug, **kwargs)


def create_task(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'tasks')
    return crm_tasks.create_task(organization_slug, **kwargs)


def add_activity(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'activities')
    return crm_activities.add_activity(organization_slug, **kwargs)


def create_quote(user_id: int, organization_slug: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'quotes')
    return crm_quotes.create_quote(organization_slug, **kwargs)


def link_conversation(user_id: int, organization_slug: str, token: str, **kwargs):
    crm_auth.require(user_id, organization_slug, 'conversation_links')
    return crm_conversation_links.link_conversation(
        organization_slug, token, **kwargs
    )


def _count_quotes(organization_slug: str) -> int:
    crm_quotes.ensure_schema()
    organization_id = crm_quotes._org_id(organization_slug)
    import tenant_auth
    with tenant_auth.db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM crm_v2_quotes "
            "WHERE organization_id=? AND status!='archived'",
            (organization_id,),
        ).fetchone()
    return int(row['n'] or 0)
