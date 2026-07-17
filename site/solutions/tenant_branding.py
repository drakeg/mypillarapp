from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from urllib.parse import urlsplit

import tenant_context


_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


@dataclass(frozen=True)
class TenantBranding:
    site_name: str
    tagline: str
    logo_url: str
    primary_color: str
    secondary_color: str
    support_email: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _valid_url(value: str) -> bool:
    if not value:
        return True
    parsed = urlsplit(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _valid_email(value: str) -> bool:
    if not value:
        return True
    local, separator, domain = value.partition('@')
    return bool(local and separator and domain and '.' in domain)


def _defaults(organization_slug: str) -> TenantBranding | None:
    tenant = tenant_context.get_tenant_by_slug(organization_slug)
    if not tenant:
        return None
    return TenantBranding(
        site_name=tenant.name,
        tagline='',
        logo_url='',
        primary_color='#1f6f5f',
        secondary_color='#f4b942',
        support_email='',
    )


def get_branding(organization_slug: str) -> TenantBranding | None:
    defaults = _defaults(organization_slug)
    if not defaults:
        return None

    settings = tenant_context.get_settings(organization_slug)
    stored = settings.get('branding', {})
    if not isinstance(stored, dict):
        stored = {}

    values = defaults.as_dict()
    for key, value in stored.items():
        if key in values and isinstance(value, str):
            values[key] = value

    return TenantBranding(**values)


def update_branding(
    organization_slug: str,
    *,
    site_name: str,
    tagline: str = '',
    logo_url: str = '',
    primary_color: str = '#1f6f5f',
    secondary_color: str = '#f4b942',
    support_email: str = '',
) -> tuple[bool, str]:
    tenant = tenant_context.get_tenant_by_slug(organization_slug)
    if not tenant:
        return False, 'Tenant not found.'

    values = {
        'site_name': (site_name or '').strip(),
        'tagline': (tagline or '').strip(),
        'logo_url': (logo_url or '').strip(),
        'primary_color': (primary_color or '').strip(),
        'secondary_color': (secondary_color or '').strip(),
        'support_email': (support_email or '').strip().lower(),
    }

    if not values['site_name']:
        return False, 'Site name is required.'
    if not _HEX_COLOR.fullmatch(values['primary_color']):
        return False, 'Primary color must be a six-digit hex color.'
    if not _HEX_COLOR.fullmatch(values['secondary_color']):
        return False, 'Secondary color must be a six-digit hex color.'
    if not _valid_url(values['logo_url']):
        return False, 'Logo URL must use http or https.'
    if not _valid_email(values['support_email']):
        return False, 'Support email is invalid.'

    if not tenant_context.set_setting(organization_slug, 'branding', values):
        return False, 'Branding could not be saved.'

    return True, 'Branding updated.'
