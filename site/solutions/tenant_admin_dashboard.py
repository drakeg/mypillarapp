from __future__ import annotations

from dataclasses import dataclass
import html

import tenant_auth
import tenant_branding
import tenant_context
import tenant_conversations
import tenant_lifecycle
import tenant_organizations


@dataclass(frozen=True)
class TenantAdminSummary:
    slug: str
    name: str
    status: str
    primary_domain: str
    site_name: str
    primary_color: str
    user_count: int
    conversation_count: int
    project_request_count: int


def list_tenant_summaries() -> list[TenantAdminSummary]:
    tenant_context.ensure_schema()
    tenant_conversations.ensure_schema()
    organizations = tenant_organizations.list_organizations(include_inactive=True)
    summaries: list[TenantAdminSummary] = []

    with tenant_auth.db() as conn:
        for organization in organizations:
            slug = str(organization['slug'])
            branding = tenant_branding.get_branding(slug)
            counts = conn.execute(
                '''SELECT
                       (SELECT COUNT(*) FROM auth_users
                         WHERE organization_id = ?) AS user_count,
                       (SELECT COUNT(*) FROM conversations
                         WHERE organization_slug = ?) AS conversation_count,
                       (SELECT COUNT(*) FROM conversations
                         WHERE organization_slug = ?
                           AND kind = 'project_request') AS project_request_count''',
                (organization['id'], slug, slug),
            ).fetchone()
            summaries.append(
                TenantAdminSummary(
                    slug=slug,
                    name=str(organization['name']),
                    status=str(organization['status']),
                    primary_domain=str(organization['primary_domain'] or ''),
                    site_name=branding.site_name if branding else str(organization['name']),
                    primary_color=branding.primary_color if branding else '#1f6f5f',
                    user_count=int(counts['user_count'] or 0),
                    conversation_count=int(counts['conversation_count'] or 0),
                    project_request_count=int(counts['project_request_count'] or 0),
                )
            )
    return summaries


def get_dashboard_totals() -> dict[str, int]:
    summaries = list_tenant_summaries()
    return {
        'tenants': len(summaries),
        'active_tenants': sum(item.status == 'active' for item in summaries),
        'users': sum(item.user_count for item in summaries),
        'conversations': sum(item.conversation_count for item in summaries),
        'project_requests': sum(item.project_request_count for item in summaries),
    }


def change_status(slug: str, action: str):
    normalized = (action or '').strip().lower()
    if normalized == 'suspend':
        return tenant_lifecycle.suspend_tenant(slug)
    if normalized == 'reactivate':
        return tenant_lifecycle.reactivate_tenant(slug)
    if normalized == 'archive':
        return tenant_lifecycle.archive_tenant(slug)
    return False, 'Unsupported tenant lifecycle action.', None


def _esc(value: object) -> str:
    return html.escape(str(value or ''))


def render_tenant_dashboard() -> str:
    totals = get_dashboard_totals()
    summaries = list_tenant_summaries()
    cards = ''.join(
        f"<article class='admin-stat-card'><strong>{totals[key]}</strong><span>{label}</span></article>"
        for key, label in (
            ('tenants', 'Tenants'),
            ('active_tenants', 'Active'),
            ('users', 'Users'),
            ('conversations', 'Conversations'),
            ('project_requests', 'Project requests'),
        )
    )
    rows = []
    for tenant in summaries:
        actions = []
        if tenant.slug != 'solutions':
            if tenant.status == 'active':
                actions.extend((
                    f"<button type='button' data-tenant-action='suspend' data-tenant='{_esc(tenant.slug)}'>Suspend</button>",
                    f"<button type='button' data-tenant-action='archive' data-tenant='{_esc(tenant.slug)}'>Archive</button>",
                ))
            elif tenant.status == 'inactive':
                actions.append(
                    f"<button type='button' data-tenant-action='reactivate' data-tenant='{_esc(tenant.slug)}'>Reactivate</button>"
                )
        rows.append(
            "<tr>"
            f"<td><span class='tenant-brand-swatch' style='background:{_esc(tenant.primary_color)}'></span>"
            f"<strong>{_esc(tenant.site_name)}</strong><small>{_esc(tenant.slug)}</small></td>"
            f"<td>{_esc(tenant.primary_domain) or 'Not configured'}</td>"
            f"<td><span class='status status-{_esc(tenant.status)}'>{_esc(tenant.status.title())}</span></td>"
            f"<td>{tenant.user_count}</td><td>{tenant.conversation_count}</td>"
            f"<td>{tenant.project_request_count}</td>"
            f"<td>{''.join(actions) or 'Protected'}</td>"
            "</tr>"
        )
    return (
        "<section class='admin-tenant-dashboard'>"
        "<div class='admin-stat-grid'>" + cards + "</div>"
        "<div class='admin-table-wrap'><table><thead><tr>"
        "<th>Tenant</th><th>Primary domain</th><th>Status</th>"
        "<th>Users</th><th>Conversations</th><th>Requests</th><th>Actions</th>"
        "</tr></thead><tbody>" + ''.join(rows) + "</tbody></table></div>"
        "</section>"
    )
