from __future__ import annotations

from dataclasses import dataclass

import creator_profiles
import crm_companies
import portal_projects
import site_pages
import tenant_auth
import tenant_conversations
import tenant_memberships
import tenant_sites


ALLOWED_CONTEXT_CLASSES = {
    'site_page',
    'crm_company',
    'portal_project',
    'creator_profile',
    'creator_link',
    'conversation',
}

BLOCKED_CONTEXT_CLASSES = {
    'auth_material',
    'provider_secret',
    'storage_key',
    'infrastructure_state',
    'portal_internal',
    'session_token',
}

OUTPUT_CLASSIFICATION = 'untrusted_generated_text'


@dataclass(frozen=True)
class AIRequestScope:
    user_id: int
    organization_id: int
    organization_slug: str
    role: str
    site_id: int | None = None
    site_slug: str | None = None


@dataclass(frozen=True)
class AIContextReference:
    context_class: str
    identifier: str
    site_slug: str | None = None


def classify_context(context_class: str) -> str:
    normalized = (context_class or '').strip().lower()
    if normalized in ALLOWED_CONTEXT_CLASSES:
        return 'eligible'
    if normalized in BLOCKED_CONTEXT_CLASSES:
        return 'blocked'
    return 'unknown'


def authorize_request(
    user_id: int,
    organization_slug: str,
    *,
    site_slug: str | None = None,
) -> AIRequestScope:
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        user = conn.execute(
            'SELECT id, is_active FROM auth_users WHERE id=? LIMIT 1',
            (int(user_id),),
        ).fetchone()
        organization = conn.execute(
            'SELECT id, status FROM auth_organizations WHERE slug=? LIMIT 1',
            (slug,),
        ).fetchone()

    if not user or int(user['is_active']) != 1:
        raise PermissionError('AI access denied.')
    if not organization or organization['status'] != 'active':
        raise PermissionError('AI access denied.')

    membership = tenant_memberships.get_membership(int(user_id), slug)
    if membership is None or membership.status != 'active':
        raise PermissionError('AI access denied.')

    site_id = None
    normalized_site = None
    if site_slug is not None:
        normalized_site = (site_slug or '').strip().lower()
        site = tenant_sites.get_site(slug, normalized_site)
        if site is None or site.status == 'archived':
            raise PermissionError('AI site scope denied.')
        site_id = site.id

    return AIRequestScope(
        user_id=int(user_id),
        organization_id=int(organization['id']),
        organization_slug=slug,
        role=membership.role,
        site_id=site_id,
        site_slug=normalized_site,
    )


def validate_context_reference(
    scope: AIRequestScope,
    reference: AIContextReference,
) -> None:
    context_class = (reference.context_class or '').strip().lower()
    if classify_context(context_class) != 'eligible':
        raise PermissionError('AI context class is not eligible.')

    if context_class == 'site_page':
        site_slug = _require_site_scope(scope, reference.site_slug)
        if site_pages.get_page(scope.organization_slug, site_slug, reference.identifier) is None:
            raise PermissionError('AI context reference denied.')
        return

    if context_class == 'crm_company':
        record = crm_companies.get_company(
            scope.organization_slug,
            _int_identifier(reference.identifier),
        )
        if record is None:
            raise PermissionError('AI context reference denied.')
        return

    if context_class == 'portal_project':
        record = portal_projects.get_project(
            scope.organization_slug,
            _int_identifier(reference.identifier),
        )
        if record is None:
            raise PermissionError('AI context reference denied.')
        return

    if context_class == 'creator_profile':
        site_slug = _require_site_scope(scope, reference.site_slug)
        if creator_profiles.get_profile(scope.organization_slug, site_slug) is None:
            raise PermissionError('AI context reference denied.')
        return

    if context_class == 'creator_link':
        site_slug = _require_site_scope(scope, reference.site_slug)
        record = creator_profiles.get_link(
            scope.organization_slug,
            site_slug,
            _int_identifier(reference.identifier),
        )
        if record is None:
            raise PermissionError('AI context reference denied.')
        return

    if context_class == 'conversation':
        if tenant_conversations.get_conversation(
            scope.organization_slug,
            reference.identifier,
        ) is None:
            raise PermissionError('AI context reference denied.')
        return

    raise PermissionError('AI context reference denied.')


def validate_context_set(
    scope: AIRequestScope,
    references: list[AIContextReference] | tuple[AIContextReference, ...],
) -> tuple[AIContextReference, ...]:
    checked: list[AIContextReference] = []
    for reference in references:
        validate_context_reference(scope, reference)
        checked.append(reference)
    return tuple(checked)


def _require_site_scope(scope: AIRequestScope, reference_site_slug: str | None) -> str:
    candidate = (reference_site_slug or scope.site_slug or '').strip().lower()
    if not candidate:
        raise PermissionError('AI site context requires an explicit site scope.')
    site = tenant_sites.get_site(scope.organization_slug, candidate)
    if site is None or site.status == 'archived':
        raise PermissionError('AI site context denied.')
    if scope.site_slug is not None and candidate != scope.site_slug:
        raise PermissionError('AI context cannot cross the authorized site scope.')
    return candidate


def _int_identifier(value: str) -> int:
    if isinstance(value, bool):
        raise PermissionError('AI context reference denied.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PermissionError('AI context reference denied.') from exc
    if parsed <= 0:
        raise PermissionError('AI context reference denied.')
    return parsed
