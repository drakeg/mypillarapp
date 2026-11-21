from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tenant_auth
import tenant_memberships


READ_ROLES = {'owner', 'admin', 'staff', 'viewer'}
WRITE_ROLES = {'owner', 'admin', 'staff'}
ADMIN_ROLES = {'owner', 'admin'}

CAPABILITIES = {
    'view': READ_ROLES,
    'manage': WRITE_ROLES,
    'admin': ADMIN_ROLES,
}


@dataclass(frozen=True)
class SchedulingAccess:
    user_id: int
    organization_id: int
    organization_slug: str
    role: str
    can_view: bool
    can_manage: bool
    can_administer: bool


def access_for(
    user_id: int,
    organization_slug: str,
) -> SchedulingAccess | None:
    org = _active_org(organization_slug)
    if org is None:
        return None
    membership = tenant_memberships.get_membership(
        int(user_id), str(org['slug'])
    )
    if (
        membership is None
        or membership.status != 'active'
        or membership.role not in READ_ROLES
    ):
        return None
    return SchedulingAccess(
        user_id=int(user_id),
        organization_id=int(org['id']),
        organization_slug=str(org['slug']),
        role=membership.role,
        can_view=True,
        can_manage=membership.role in WRITE_ROLES,
        can_administer=membership.role in ADMIN_ROLES,
    )


def require(
    user_id: int,
    organization_slug: str,
    capability: str,
) -> SchedulingAccess:
    clean_capability = (capability or '').strip().lower()
    allowed = CAPABILITIES.get(clean_capability)
    access = access_for(user_id, organization_slug)
    if access is None or allowed is None or access.role not in allowed:
        raise PermissionError('Scheduling access denied.')
    return access


def normalize_timezone(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Calendar timezone is required.')
    try:
        zone = ZoneInfo(clean)
    except ZoneInfoNotFoundError as exc:
        raise ValueError('Calendar timezone must be a valid IANA timezone.') from exc
    key = getattr(zone, 'key', None)
    return str(key or clean)


def validate_utc_range(start_at: int, end_at: int) -> tuple[int, int]:
    start = _epoch(start_at, 'start_at')
    end = _epoch(end_at, 'end_at')
    if end <= start:
        raise ValueError('Appointment end time must be after start time.')
    return start, end


def local_to_utc_epoch(
    local_datetime: datetime,
    timezone_name: str,
) -> int:
    if not isinstance(local_datetime, datetime):
        raise ValueError('Local appointment time must be a datetime.')
    if local_datetime.tzinfo is not None:
        raise ValueError(
            'Local appointment input must be naive and paired with an IANA timezone.'
        )
    zone = ZoneInfo(normalize_timezone(timezone_name))
    aware = local_datetime.replace(tzinfo=zone)
    round_trip = (
        aware.astimezone(timezone.utc)
        .astimezone(zone)
        .replace(tzinfo=None)
    )
    if round_trip != local_datetime:
        raise ValueError(
            'Local appointment time does not exist in the selected timezone.'
        )
    return int(aware.astimezone(timezone.utc).timestamp())


def utc_epoch_to_local(
    value: int,
    timezone_name: str,
) -> datetime:
    epoch = _epoch(value, 'utc_epoch')
    zone = ZoneInfo(normalize_timezone(timezone_name))
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(zone)


def require_site(
    organization_slug: str,
    site_id: int | None,
) -> int | None:
    if site_id is None:
        return None
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT id
               FROM site_builder_sites
               WHERE id=? AND organization_id=? AND status!='archived'
               LIMIT 1''',
            (_positive_id(site_id, 'site_id'), organization_id),
        ).fetchone()
    if row is None:
        raise PermissionError('Scheduling site reference is not owned by tenant.')
    return int(row['id'])


def require_contact(
    organization_slug: str,
    contact_id: int | None,
) -> int | None:
    if contact_id is None:
        return None
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT id
               FROM crm_v2_contacts
               WHERE id=? AND organization_id=? AND status!='archived'
               LIMIT 1''',
            (_positive_id(contact_id, 'contact_id'), organization_id),
        ).fetchone()
    if row is None:
        raise PermissionError('Scheduling contact reference is not owned by tenant.')
    return int(row['id'])


def require_customer_user(
    organization_slug: str,
    customer_user_id: int | None,
) -> int | None:
    if customer_user_id is None:
        return None
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT u.id
               FROM auth_users u
               JOIN auth_memberships m
                 ON m.user_id=u.id AND m.organization_id=u.organization_id
               WHERE u.id=?
                 AND u.organization_id=?
                 AND u.is_active=1
                 AND m.status='active'
               LIMIT 1''',
            (
                _positive_id(customer_user_id, 'customer_user_id'),
                organization_id,
            ),
        ).fetchone()
    if row is None:
        raise PermissionError(
            'Scheduling customer reference is not owned by tenant.'
        )
    return int(row['id'])


def _active_org(organization_slug: str):
    clean = (organization_slug or '').strip().lower()
    if not clean:
        return None
    with tenant_auth.db() as conn:
        return conn.execute(
            '''SELECT id,slug
               FROM auth_organizations
               WHERE slug=? AND status='active'
               LIMIT 1''',
            (clean,),
        ).fetchone()


def _organization_id(organization_slug: str) -> int:
    row = _active_org(organization_slug)
    if row is None:
        raise PermissionError('Scheduling organization is not active.')
    return int(row['id'])


def _epoch(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer UTC epoch.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be an integer UTC epoch.') from exc
    if clean < 0:
        raise ValueError(f'{label} must be an integer UTC epoch.')
    return clean


def _positive_id(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a positive integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a positive integer.') from exc
    if clean <= 0:
        raise ValueError(f'{label} must be a positive integer.')
    return clean
