from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import messaging
import tenant_auth
import tenant_branding
import tenant_context
import tenant_organizations


@dataclass(frozen=True)
class OnboardingResult:
    organization_slug: str
    primary_domain: str
    owner_email: str


def onboard_tenant(
    *,
    slug: str,
    organization_name: str,
    primary_domain: str,
    owner_first_name: str,
    owner_last_name: str,
    owner_email: str,
    owner_password: str,
    site_name: str = '',
    tagline: str = '',
    logo_url: str = '',
    primary_color: str = '#1f6f5f',
    secondary_color: str = '#f4b942',
    support_email: str = '',
) -> tuple[bool, str, OnboardingResult | None]:
    normalized_slug = (slug or '').strip().lower()
    clean_name = (organization_name or '').strip()
    domain = tenant_context.normalize_host(primary_domain)
    first_name = (owner_first_name or '').strip()
    last_name = (owner_last_name or '').strip()
    email = (owner_email or '').strip().lower()

    if not tenant_organizations.SLUG_RE.fullmatch(normalized_slug):
        return False, 'Slug must contain lowercase letters, numbers, and single hyphens.', None
    if not clean_name:
        return False, 'Organization name is required.', None
    if not domain:
        return False, 'Enter a valid primary domain.', None
    if not first_name or not last_name:
        return False, 'Owner first and last name are required.', None
    if not email or '@' not in email:
        return False, 'Enter a valid owner email address.', None
    if len(owner_password) < 12:
        return False, 'Owner password must be at least 12 characters.', None

    branding_name = (site_name or '').strip() or clean_name
    branding_ok, branding_message = tenant_branding.validate_branding(
        site_name=branding_name,
        tagline=tagline,
        logo_url=logo_url,
        primary_color=primary_color,
        secondary_color=secondary_color,
        support_email=support_email,
    )
    if not branding_ok:
        return False, branding_message, None

    tenant_context.ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        if conn.execute(
            'SELECT 1 FROM auth_organizations WHERE slug = ?',
            (normalized_slug,),
        ).fetchone():
            return False, 'An organization already uses that slug.', None
        if conn.execute(
            'SELECT 1 FROM tenant_domains WHERE lower(domain) = lower(?)',
            (domain,),
        ).fetchone():
            return False, 'A tenant already uses that domain.', None

        cursor = conn.execute(
            '''INSERT INTO auth_organizations(
                   created_at, updated_at, slug, name, status
               ) VALUES (?, ?, ?, ?, 'active')''',
            (timestamp, timestamp, normalized_slug, clean_name),
        )
        organization_id = int(cursor.lastrowid)
        conn.execute(
            '''INSERT INTO tenant_domains(
                   organization_id, domain, is_primary, is_active,
                   created_at, updated_at
               ) VALUES (?, ?, 1, 1, ?, ?)''',
            (organization_id, domain, timestamp, timestamp),
        )
        user_cursor = conn.execute(
            '''INSERT INTO auth_users(
                   created_at, updated_at, organization_id, email,
                   first_name, last_name, password_hash, role, is_active
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 'owner', 0)''',
            (
                timestamp,
                timestamp,
                organization_id,
                email,
                first_name,
                last_name,
                tenant_auth.hash_password(owner_password),
            ),
        )
        owner_id = int(user_cursor.lastrowid)
        token = tenant_auth._new_token(
            conn,
            owner_id,
            'verify_email',
            60 * 60 * 24,
        )
        branding = tenant_branding.branding_values(
            site_name=branding_name,
            tagline=tagline,
            logo_url=logo_url,
            primary_color=primary_color,
            secondary_color=secondary_color,
            support_email=support_email,
        )
        conn.execute(
            '''INSERT INTO tenant_settings(
                   organization_id, setting_key, setting_value, updated_at
               ) VALUES (?, 'branding', ?, ?)''',
            (
                organization_id,
                tenant_branding.serialize_branding(branding),
                timestamp,
            ),
        )
        conn.commit()

    verification_url = tenant_auth.public_url(
        f'/verify-email/{quote(token)}',
        domain,
    )
    messaging.send_email(
        f'Verify your {branding_name} owner account',
        f'Hello {first_name},\n\nVerify your owner account:\n{verification_url}\n\nThis link expires in 24 hours.',
        f'<p>Hello {tenant_auth.esc(first_name)},</p><p>Verify your owner account:</p><p><a href="{tenant_auth.esc(verification_url)}">Verify email address</a></p><p>This link expires in 24 hours.</p>',
        email,
    )

    return (
        True,
        'Tenant onboarding completed. The owner must verify their email.',
        OnboardingResult(normalized_slug, domain, email),
    )
