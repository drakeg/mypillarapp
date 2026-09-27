"""Non-destructive, opt-in Solutions -> Site Builder content bootstrap.

The existing static Solutions homepage remains authoritative for HTTP rendering,
contact intake, async chat and customer/account flows until an explicit cutover.
This module never changes site publication, domains, tenant roles or server routes.
"""
from __future__ import annotations

from dataclasses import dataclass

import form_config
import site_forms
import site_media
import site_navigation
import site_pages
import site_services
import tenant_sites


ORGANIZATION = 'solutions'
SITE = 'main'

# Human-maintained snapshots of the current static index.html. Updating live
# copy remains independent of this migration until the explicit cutover.
PAGES = (
    (
        'home',
        'Technology that helps small businesses move faster.',
        'AWS • Linux • Terraform • Automation',
        'Mad Mallard Solutions builds practical cloud, server, automation, '
        'and web systems without unnecessary enterprise complexity or '
        'runaway monthly costs.',
        0,
    ),
    (
        'platform',
        'More than a business card site.',
        'Platform-first',
        'This page is the start of a self-hosted Pillar-style platform: links, '
        'services, lead capture, conversations, and eventually dashboards '
        'for multiple brands while keeping identities separate.',
        1,
    ),
)
SERVICES = (
    (
        'aws-cloud-setup',
        'AWS & cloud setup',
        'Right-sized infrastructure, secure access, HTTPS, backups, and '
        'deployment patterns that keep costs under control.',
        0,
    ),
    (
        'linux-docker-support',
        'Linux & Docker support',
        'Server hardening, troubleshooting, container deployments, logging, '
        'patches, and practical operational documentation.',
        1,
    ),
    (
        'terraform-automation',
        'Terraform & automation',
        'Repeatable infrastructure, scripted workflows, GitHub-driven '
        'deployments, and small tools that save time every week.',
        2,
    ),
)
NAVIGATION = (
    ('Services', '/#services', 0),
    ('Platform', '/#platform', 1),
    ('Contact', '/#contact', 2),
)
MEDIA = (
    ('solutions-icon', 'image', '/assets/mad-mallard-solutions-logo-icon.png',
     'Mad Mallard Solutions icon', 'image/png'),
    ('solutions-lockup', 'image', '/assets/mad-mallard-solutions-logo-lockup.png',
     'Mad Mallard Solutions logo', 'image/png'),
)


@dataclass(frozen=True)
class MigrationResult:
    created_pages: int
    created_services: int
    created_forms: int
    created_navigation: int
    created_media: int


def migrate_solutions_content() -> MigrationResult:
    """Stage missing legacy content as *draft*, without changing live routes.

    Existing records, including edited or published records, are left intact.
    Re-running only fills missing seeded records. This function is opt-in:
    it is never called during request handling or schema initialization.
    """
    site = tenant_sites.get_site(ORGANIZATION, SITE)
    if not site or site.status == 'archived':
        raise ValueError('An active Solutions main site is required.')

    created_pages = 0
    for slug, title, summary, body, position in PAGES:
        if site_pages.get_page(ORGANIZATION, SITE, slug) is None:
            site_pages.create_page(
                ORGANIZATION, SITE, slug=slug, title=title, summary=summary,
                body=body, position=position, status='draft',
            )
            created_pages += 1

    created_services = 0
    for slug, name, summary, position in SERVICES:
        if site_services.get_service(ORGANIZATION, SITE, slug) is None:
            site_services.create_service(
                ORGANIZATION, SITE, slug=slug, name=name, summary=summary,
                position=position, status='draft',
            )
            created_services += 1

    created_forms = 0
    if site_forms.get_form(ORGANIZATION, SITE, 'project-request') is None:
        site_forms.create_form(
            ORGANIZATION, SITE,
            slug='project-request',
            title='Project request',
            fields=[dict(field) for field in form_config.REQUEST_FORM_FIELDS],
            submit_label='Send project request',
            status='draft',
        )
        created_forms += 1

    created_navigation = 0
    existing_nav = {
        (item.label, item.target)
        for item in site_navigation.list_items(ORGANIZATION, SITE)
    }
    for label, target, position in NAVIGATION:
        if (label, target) not in existing_nav:
            site_navigation.create_item(
                ORGANIZATION, SITE, label=label, target=target,
                position=position, is_visible=False,
            )
            created_navigation += 1

    created_media = 0
    for slug, kind, source, alt_text, mime_type in MEDIA:
        if site_media.get_media(ORGANIZATION, SITE, slug) is None:
            site_media.create_media(
                ORGANIZATION, SITE, slug=slug, kind=kind, source=source,
                alt_text=alt_text, mime_type=mime_type, status='draft',
            )
            created_media += 1

    return MigrationResult(
        created_pages=created_pages,
        created_services=created_services,
        created_forms=created_forms,
        created_navigation=created_navigation,
        created_media=created_media,
    )
