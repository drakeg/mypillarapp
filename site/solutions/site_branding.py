from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from urllib.parse import urlsplit

import tenant_auth
import tenant_branding
import tenant_sites


_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
THEMES = ('classic', 'minimal', 'bold')


@dataclass(frozen=True)
class SiteBranding:
    site_name: str
    tagline: str
    logo_url: str
    primary_color: str
    secondary_color: str
    support_email: str
    theme: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_settings (
                site_id INTEGER NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(site_id, setting_key),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


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


def branding_values(
    *,
    site_name: str,
    tagline: str = '',
    logo_url: str = '',
    primary_color: str = '#1f6f5f',
    secondary_color: str = '#f4b942',
    support_email: str = '',
    theme: str = 'classic',
) -> dict[str, str]:
    return {
        'site_name': (site_name or '').strip(),
        'tagline': (tagline or '').strip(),
        'logo_url': (logo_url or '').strip(),
        'primary_color': (primary_color or '').strip(),
        'secondary_color': (secondary_color or '').strip(),
        'support_email': (support_email or '').strip().lower(),
        'theme': (theme or '').strip().lower(),
    }


def validate_branding(**kwargs) -> tuple[bool, str]:
    values = branding_values(**kwargs)
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
    if values['theme'] not in THEMES:
        return False, 'Theme must be classic, minimal, or bold.'
    return True, ''


def _defaults(organization_slug: str, site_slug: str) -> SiteBranding | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if not site:
        return None

    values = branding_values(site_name=site.name)
    if site.slug == 'main':
        legacy = tenant_branding.get_branding(organization_slug)
        if legacy:
            values.update(legacy.as_dict())

    values['theme'] = 'classic'
    return SiteBranding(**values)


def get_branding(
    organization_slug: str,
    site_slug: str = 'main',
) -> SiteBranding | None:
    defaults = _defaults(organization_slug, site_slug)
    if not defaults:
        return None

    ensure_schema()
    site = tenant_sites.get_site(organization_slug, site_slug)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT setting_value
               FROM site_builder_settings
               WHERE site_id = ? AND setting_key = 'branding'
               LIMIT 1''',
            (site.id,),
        ).fetchone()

    values = defaults.as_dict()
    if row:
        try:
            stored = json.loads(row['setting_value'])
        except (TypeError, json.JSONDecodeError):
            stored = {}
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in values and isinstance(value, str):
                    values[key] = value

    valid, _ = validate_branding(**values)
    if not valid:
        return defaults
    return SiteBranding(**values)


def update_branding(
    organization_slug: str,
    site_slug: str = 'main',
    *,
    site_name: str,
    tagline: str = '',
    logo_url: str = '',
    primary_color: str = '#1f6f5f',
    secondary_color: str = '#f4b942',
    support_email: str = '',
    theme: str = 'classic',
) -> tuple[bool, str]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if not site:
        return False, 'Site not found.'
    if site.status == 'archived':
        return False, 'Archived sites cannot be updated.'

    values = branding_values(
        site_name=site_name,
        tagline=tagline,
        logo_url=logo_url,
        primary_color=primary_color,
        secondary_color=secondary_color,
        support_email=support_email,
        theme=theme,
    )
    valid, message = validate_branding(**values)
    if not valid:
        return False, message

    ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''INSERT INTO site_builder_settings(
                   site_id, setting_key, setting_value, updated_at
               ) VALUES (?, 'branding', ?, ?)
               ON CONFLICT(site_id, setting_key) DO UPDATE SET
                   setting_value = excluded.setting_value,
                   updated_at = excluded.updated_at''',
            (
                site.id,
                json.dumps(values, separators=(',', ':'), sort_keys=True),
                tenant_auth.now(),
            ),
        )
        conn.commit()

    return True, 'Site branding updated.'
