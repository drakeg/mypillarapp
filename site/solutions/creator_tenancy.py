from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import site_media
import site_navigation
import tenant_auth
import tenant_context
import tenant_memberships
import tenant_sites


@dataclass(frozen=True)
class CreatorSiteScope:
    user_id: int | None
    organization_id: int
    organization_slug: str
    site_id: int
    site_slug: str


@dataclass(frozen=True)
class CreatorLegacyAudit:
    sites: int
    published_sites: int
    active_domains: int
    external_navigation_links: int
    external_media_sources: int
    insecure_http_urls: int
    credentialed_urls: int
    domain_site_mismatches: int
    published_sites_without_active_domain: int

    @property
    def safe_for_creator_migration(self) -> bool:
        return (
            self.insecure_http_urls == 0
            and self.credentialed_urls == 0
            and self.domain_site_mismatches == 0
        )


def authoring_scope(
    user_id: int,
    organization_slug: str,
    site_slug: str,
) -> CreatorSiteScope:
    tenant_context.ensure_schema()
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None or site.status == 'archived':
        raise PermissionError('Creator site access denied.')

    with tenant_auth.db() as conn:
        organization = conn.execute(
            "SELECT status FROM auth_organizations WHERE id=?",
            (site.organization_id,),
        ).fetchone()
    if organization is None or organization['status'] != 'active':
        raise PermissionError('Creator site access denied.')

    membership = tenant_memberships.get_membership(
        int(user_id), organization_slug
    )
    if membership is None or membership.status != 'active':
        raise PermissionError('Creator site access denied.')

    return CreatorSiteScope(
        user_id=int(user_id),
        organization_id=site.organization_id,
        organization_slug=site.organization_slug,
        site_id=site.id,
        site_slug=site.slug,
    )


def public_scope(host: str) -> CreatorSiteScope | None:
    site = tenant_context.resolve_site(host)
    if site is None or site.status != 'published':
        return None
    return CreatorSiteScope(
        user_id=None,
        organization_id=site.organization_id,
        organization_slug=site.organization_slug,
        site_id=site.id,
        site_slug=site.slug,
    )


def audit_existing_creator_content() -> CreatorLegacyAudit:
    tenant_context.ensure_schema()
    site_navigation.ensure_schema()
    site_media.ensure_schema()

    with tenant_auth.db() as conn:
        sites = conn.execute(
            '''
            SELECT s.id, s.status,
                   SUM(CASE WHEN d.id IS NOT NULL THEN 1 ELSE 0 END)
                       AS active_domain_count
            FROM site_builder_sites s
            LEFT JOIN tenant_domains d
              ON d.site_id=s.id
             AND d.organization_id=s.organization_id
             AND d.is_active=1
            GROUP BY s.id, s.status
            '''
        ).fetchall()
        domains = conn.execute(
            '''
            SELECT d.organization_id, d.site_id, s.organization_id AS site_org
            FROM tenant_domains d
            LEFT JOIN site_builder_sites s ON s.id=d.site_id
            WHERE d.is_active=1
            '''
        ).fetchall()
        navigation = conn.execute(
            'SELECT target FROM site_builder_navigation'
        ).fetchall()
        media = conn.execute(
            'SELECT source FROM site_builder_media'
        ).fetchall()

    urls: list[str] = []
    external_navigation = 0
    for row in navigation:
        value = str(row['target'] or '').strip()
        if value and not value.startswith('/'):
            external_navigation += 1
            urls.append(value)

    external_media = 0
    for row in media:
        value = str(row['source'] or '').strip()
        if value and not value.startswith('/'):
            external_media += 1
            urls.append(value)

    insecure_http = 0
    credentialed = 0
    for value in urls:
        parsed = urlsplit(value)
        if parsed.scheme.lower() == 'http':
            insecure_http += 1
        if parsed.username is not None or parsed.password is not None:
            credentialed += 1

    domain_mismatches = sum(
        1
        for row in domains
        if row['site_id'] is None
        or row['site_org'] is None
        or int(row['organization_id']) != int(row['site_org'])
    )
    published_without_domain = sum(
        1
        for row in sites
        if row['status'] == 'published'
        and int(row['active_domain_count'] or 0) == 0
    )

    return CreatorLegacyAudit(
        sites=len(sites),
        published_sites=sum(1 for row in sites if row['status'] == 'published'),
        active_domains=len(domains),
        external_navigation_links=external_navigation,
        external_media_sources=external_media,
        insecure_http_urls=insecure_http,
        credentialed_urls=credentialed,
        domain_site_mismatches=domain_mismatches,
        published_sites_without_active_domain=published_without_domain,
    )
