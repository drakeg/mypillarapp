from __future__ import annotations

from dataclasses import dataclass

import portal_auth
import portal_files
import portal_messaging
import portal_notifications
import portal_projects
import portal_tickets


@dataclass(frozen=True)
class PortalStaffSummary:
    organization_slug: str
    projects: int
    tickets: int
    files: int
    conversation_links: int


def summary_for(
    staff_user_id: int,
    organization_slug: str,
) -> PortalStaffSummary:
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'view'
    )
    return PortalStaffSummary(
        organization_slug=organization_slug,
        projects=len(portal_projects.list_projects(organization_slug)),
        tickets=len(portal_tickets.list_tickets(organization_slug)),
        files=len(portal_files.list_files(organization_slug)),
        conversation_links=len(
            portal_messaging.list_links(organization_slug)
        ),
    )


def create_project(
    staff_user_id: int,
    organization_slug: str,
    **kwargs,
):
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'projects'
    )
    return portal_projects.create_project(organization_slug, **kwargs)


def create_ticket(
    staff_user_id: int,
    organization_slug: str,
    **kwargs,
):
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'tickets'
    )
    return portal_tickets.create_ticket(organization_slug, **kwargs)


def create_file(
    staff_user_id: int,
    organization_slug: str,
    **kwargs,
):
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'files'
    )
    return portal_files.create_file(organization_slug, **kwargs)


def create_notification_delivery(
    staff_user_id: int,
    organization_slug: str,
    **kwargs,
):
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'notifications'
    )
    return portal_notifications.create_delivery(
        organization_slug, **kwargs
    )


def link_conversation(
    staff_user_id: int,
    organization_slug: str,
    conversation_token: str,
    **kwargs,
):
    portal_auth.require_staff(
        staff_user_id, organization_slug, 'messaging'
    )
    return portal_messaging.link_conversation(
        organization_slug, conversation_token, **kwargs
    )
