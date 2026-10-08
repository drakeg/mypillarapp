from __future__ import annotations

from dataclasses import dataclass

import portal_files
import portal_notifications
import portal_projects
import portal_tenancy
import portal_tickets


HISTORY_KINDS = ('project', 'ticket', 'file', 'conversation', 'notification')


@dataclass(frozen=True)
class HistoryItem:
    kind: str
    record_id: str
    title: str
    status: str
    detail: str
    occurred_at: int


def list_customer_history(
    scope: portal_tenancy.CustomerScope,
    *,
    limit: int = 100,
) -> list[HistoryItem]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError('Customer history limit must be between 1 and 500.')

    # Revalidate the customer against current user/membership/tenant state.
    with portal_projects.tenant_auth.db() as conn:
        email = portal_projects._validate_customer(
            conn, scope.organization_id, scope.user_id
        )
    if email != scope.email:
        raise ValueError('Customer scope no longer matches the active customer.')

    items: list[HistoryItem] = []

    for project in portal_projects.list_projects(
        scope.organization_slug,
        customer_user_id=scope.user_id,
    ):
        items.append(HistoryItem(
            kind='project',
            record_id=str(project.id),
            title=project.title,
            status=project.status,
            detail=project.summary,
            occurred_at=project.updated_at,
        ))

    for ticket in portal_tickets.list_tickets(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        visibility='customer',
    ):
        items.append(HistoryItem(
            kind='ticket',
            record_id=str(ticket.id),
            title=ticket.subject,
            status=ticket.status,
            detail=ticket.description,
            occurred_at=ticket.updated_at,
        ))

    for file in portal_files.list_files(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        visibility='customer',
    ):
        items.append(HistoryItem(
            kind='file',
            record_id=str(file.id),
            title=file.name,
            status='available',
            detail=file.mime_type,
            occurred_at=file.updated_at,
        ))

    for conversation in portal_tenancy.list_customer_history(scope):
        items.append(HistoryItem(
            kind='conversation',
            record_id=str(conversation['token']),
            title=str(
                conversation['subject']
                or (
                    'Service request'
                    if conversation['kind'] == 'project_request'
                    else 'Website chat'
                )
            ),
            status=str(conversation['status']),
            detail=str(conversation['kind']),
            occurred_at=int(conversation['updated_at']),
        ))

    for delivery in portal_notifications.list_deliveries(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        limit=500,
    ):
        items.append(HistoryItem(
            kind='notification',
            record_id=str(delivery.id),
            title=delivery.subject or delivery.notification_type.replace('_', ' ').title(),
            status=delivery.status,
            detail=delivery.notification_type,
            occurred_at=delivery.created_at,
        ))

    # Deterministic newest-first ordering. record_id is stringified because
    # conversation tokens and numeric primary keys share the same timeline.
    items.sort(
        key=lambda item: (
            -item.occurred_at,
            item.kind,
            item.record_id,
        )
    )
    return items[:limit]
