from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import tenant_auth
import tenant_context


@dataclass(frozen=True)
class RequestContext:
    tenant: tenant_context.Tenant
    host: str
    user: object | None

    @property
    def authenticated(self) -> bool:
        return self.user is not None


def request_host(headers: Mapping[str, str]) -> str:
    """Return the externally visible request host.

    Caddy supplies X-Forwarded-Host for proxied requests. Only the first
    forwarded host is accepted; direct Host remains the fallback.
    """
    forwarded = str(headers.get('X-Forwarded-Host', '') or '').split(',', 1)[0].strip()
    return tenant_context.normalize_host(forwarded or str(headers.get('Host', '') or ''))


def resolve_request_tenant(headers: Mapping[str, str]) -> tenant_context.Tenant | None:
    host = request_host(headers)
    return tenant_context.resolve_tenant(host) if host else None


def user_belongs_to_tenant(user: object | None, tenant: tenant_context.Tenant | None) -> bool:
    if not user or not tenant:
        return False
    try:
        return str(user['organization_slug']).strip().lower() == tenant.slug
    except (KeyError, TypeError, IndexError):
        return False


def build_request_context(
    headers: Mapping[str, str],
    session_token: str = '',
) -> RequestContext | None:
    """Resolve tenant and optionally authenticate a customer within it.

    Unknown hosts are rejected. A valid session from a different tenant is
    intentionally treated as anonymous so it cannot cross tenant boundaries.
    """
    tenant = resolve_request_tenant(headers)
    if not tenant:
        return None

    user = tenant_auth.current_user(session_token) if session_token else None
    if user and not user_belongs_to_tenant(user, tenant):
        user = None

    return RequestContext(tenant=tenant, host=request_host(headers), user=user)
