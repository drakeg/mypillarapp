from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import portal_projects
import tenant_auth


NOTIFICATION_CHANNELS = ('email', 'in_app')
NOTIFICATION_TYPES = (
    'project_update',
    'ticket_update',
    'file_available',
    'message',
    'service_notice',
)
DELIVERY_STATUSES = ('queued', 'sent', 'failed')


@dataclass(frozen=True)
class NotificationPreference:
    organization_id: int
    organization_slug: str
    customer_user_id: int
    customer_email: str
    channel: str
    notification_type: str
    enabled: bool
    updated_at: int


@dataclass(frozen=True)
class NotificationDelivery:
    id: int
    organization_id: int
    organization_slug: str
    customer_user_id: int
    customer_email: str
    channel: str
    notification_type: str
    subject: str
    body: str
    status: str
    created_at: int


def ensure_schema() -> None:
    portal_projects.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_notification_preferences (
                organization_id INTEGER NOT NULL,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                channel TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(
                    organization_id, customer_user_id, channel, notification_type
                ),
                CHECK(channel IN ('email','in_app')),
                CHECK(notification_type IN (
                    'project_update','ticket_update','file_available',
                    'message','service_notice'
                )),
                CHECK(enabled IN (0,1)),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_notification_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                channel TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                created_at INTEGER NOT NULL,
                CHECK(channel IN ('email','in_app')),
                CHECK(notification_type IN (
                    'project_update','ticket_update','file_available',
                    'message','service_notice'
                )),
                CHECK(status IN ('queued','sent','failed')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_notification_deliveries_customer '
            'ON portal_notification_deliveries('
            'organization_id, customer_user_id, created_at DESC, id DESC)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return portal_projects._org_id(organization_slug)


def _validate_customer(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
) -> str:
    return portal_projects._validate_customer(
        conn, organization_id, customer_user_id
    )


def _clean_channel(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in NOTIFICATION_CHANNELS:
        raise ValueError(f'Unknown notification channel: {value}')
    return value


def _clean_type(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in NOTIFICATION_TYPES:
        raise ValueError(f'Unknown notification type: {value}')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in DELIVERY_STATUSES:
        raise ValueError(f'Unknown notification delivery status: {value}')
    return value


def _clean_text(value: str, label: str, limit: int) -> str:
    value = (value or '').strip()
    if len(value) > limit:
        raise ValueError(f'{label} must be {limit} characters or fewer.')
    return value


def set_preference(
    organization_slug: str,
    *,
    customer_user_id: int,
    channel: str,
    notification_type: str,
    enabled: bool,
) -> NotificationPreference:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    clean_channel = _clean_channel(channel)
    clean_type = _clean_type(notification_type)
    if not isinstance(enabled, bool):
        raise ValueError('Notification preference enabled must be boolean.')
    with tenant_auth.db() as conn:
        email = _validate_customer(conn, organization_id, customer_user_id)
        now = tenant_auth.now()
        conn.execute(
            '''
            INSERT INTO portal_notification_preferences(
                organization_id, customer_user_id, customer_email,
                channel, notification_type, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                organization_id, customer_user_id, channel, notification_type
            ) DO UPDATE SET
                customer_email=excluded.customer_email,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            ''',
            (
                organization_id,
                int(customer_user_id),
                email,
                clean_channel,
                clean_type,
                int(enabled),
                now,
            ),
        )
        conn.commit()
        row = _select_preference(
            conn, organization_id, int(customer_user_id),
            clean_channel, clean_type
        )
    return _preference_from_row(row)


def is_enabled(
    organization_slug: str,
    *,
    customer_user_id: int,
    channel: str,
    notification_type: str,
) -> bool:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    clean_channel = _clean_channel(channel)
    clean_type = _clean_type(notification_type)
    with tenant_auth.db() as conn:
        _validate_customer(conn, organization_id, customer_user_id)
        row = _select_preference(
            conn, organization_id, int(customer_user_id),
            clean_channel, clean_type
        )
    return True if row is None else bool(row['enabled'])


def list_preferences(
    organization_slug: str,
    *,
    customer_user_id: int,
) -> list[NotificationPreference]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        _validate_customer(conn, organization_id, customer_user_id)
        rows = conn.execute(
            '''
            SELECT p.*, o.slug AS organization_slug
            FROM portal_notification_preferences p
            JOIN auth_organizations o ON o.id=p.organization_id
            WHERE p.organization_id=? AND p.customer_user_id=?
            ORDER BY p.channel, p.notification_type
            ''',
            (organization_id, int(customer_user_id)),
        ).fetchall()
    return [_preference_from_row(row) for row in rows]


def create_delivery(
    organization_slug: str,
    *,
    customer_user_id: int,
    channel: str,
    notification_type: str,
    subject: str = '',
    body: str = '',
    status: str = 'queued',
) -> NotificationDelivery | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    clean_channel = _clean_channel(channel)
    clean_type = _clean_type(notification_type)
    clean_status = _clean_status(status)
    with tenant_auth.db() as conn:
        email = _validate_customer(conn, organization_id, customer_user_id)
        preference = _select_preference(
            conn, organization_id, int(customer_user_id),
            clean_channel, clean_type
        )
        if preference is not None and not bool(preference['enabled']):
            return None
        cur = conn.execute(
            '''
            INSERT INTO portal_notification_deliveries(
                organization_id, customer_user_id, customer_email,
                channel, notification_type, subject, body, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                int(customer_user_id),
                email,
                clean_channel,
                clean_type,
                _clean_text(subject, 'Notification subject', 200),
                _clean_text(body, 'Notification body', 10000),
                clean_status,
                tenant_auth.now(),
            ),
        )
        conn.commit()
        row = _select_delivery(conn, organization_id, int(cur.lastrowid))
    return _delivery_from_row(row)


def list_deliveries(
    organization_slug: str,
    *,
    customer_user_id: int,
    channel: str | None = None,
    notification_type: str | None = None,
    limit: int = 100,
) -> list[NotificationDelivery]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError('Notification history limit must be between 1 and 500.')
    with tenant_auth.db() as conn:
        _validate_customer(conn, organization_id, customer_user_id)
        sql = '''
            SELECT d.*, o.slug AS organization_slug
            FROM portal_notification_deliveries d
            JOIN auth_organizations o ON o.id=d.organization_id
            WHERE d.organization_id=? AND d.customer_user_id=?
        '''
        params: list[object] = [organization_id, int(customer_user_id)]
        if channel is not None:
            sql += ' AND d.channel=?'
            params.append(_clean_channel(channel))
        if notification_type is not None:
            sql += ' AND d.notification_type=?'
            params.append(_clean_type(notification_type))
        sql += ' ORDER BY d.created_at DESC, d.id DESC LIMIT ?'
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [_delivery_from_row(row) for row in rows]


def _select_preference(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
    channel: str,
    notification_type: str,
):
    return conn.execute(
        '''
        SELECT p.*, o.slug AS organization_slug
        FROM portal_notification_preferences p
        JOIN auth_organizations o ON o.id=p.organization_id
        WHERE p.organization_id=? AND p.customer_user_id=?
          AND p.channel=? AND p.notification_type=?
        LIMIT 1
        ''',
        (organization_id, customer_user_id, channel, notification_type),
    ).fetchone()


def _select_delivery(
    conn: sqlite3.Connection,
    organization_id: int,
    delivery_id: int,
):
    return conn.execute(
        '''
        SELECT d.*, o.slug AS organization_slug
        FROM portal_notification_deliveries d
        JOIN auth_organizations o ON o.id=d.organization_id
        WHERE d.organization_id=? AND d.id=?
        LIMIT 1
        ''',
        (organization_id, delivery_id),
    ).fetchone()


def _preference_from_row(row) -> NotificationPreference:
    return NotificationPreference(
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        channel=str(row['channel']),
        notification_type=str(row['notification_type']),
        enabled=bool(row['enabled']),
        updated_at=int(row['updated_at']),
    )


def _delivery_from_row(row) -> NotificationDelivery:
    return NotificationDelivery(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        channel=str(row['channel']),
        notification_type=str(row['notification_type']),
        subject=str(row['subject']),
        body=str(row['body']),
        status=str(row['status']),
        created_at=int(row['created_at']),
    )
