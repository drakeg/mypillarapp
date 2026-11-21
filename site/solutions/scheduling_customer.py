from __future__ import annotations

from dataclasses import dataclass
import time

import portal_auth
import portal_tenancy
import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import scheduling_notifications
import scheduling_public
import tenant_auth
import tenant_sites


class CustomerSlotUnavailable(ValueError):
    pass


def claim_matching_guest_bookings(
    scope: portal_tenancy.CustomerScope,
) -> list[scheduling_appointments.Appointment]:
    checked = portal_auth.revalidate_customer_scope(scope)
    scheduling_appointments.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET customer_user_id=?,updated_at=?
            WHERE organization_id=?
              AND customer_user_id IS NULL
              AND lower(trim(guest_email))=?
            ''',
            (
                checked.user_id,
                tenant_auth.now(),
                checked.organization_id,
                checked.email,
            ),
        )
        conn.commit()
    return list_customer_appointments(
        checked, include_canceled=True
    )


def list_customer_appointments(
    scope: portal_tenancy.CustomerScope,
    *,
    include_canceled: bool = True,
) -> list[scheduling_appointments.Appointment]:
    checked = portal_auth.revalidate_customer_scope(scope)
    return scheduling_appointments.list_appointments(
        checked.organization_slug,
        customer_user_id=checked.user_id,
        include_canceled=include_canceled,
    )


def cancel_customer_appointment(
    scope: portal_tenancy.CustomerScope,
    appointment_id: int,
    *,
    reason: str = 'customer_canceled',
) -> scheduling_appointments.Appointment:
    checked = portal_auth.revalidate_customer_scope(scope)
    scheduling_appointments.ensure_schema()
    clean_reason = _reason(reason)

    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = _owned_row(
            conn,
            checked.organization_id,
            checked.user_id,
            appointment_id,
        )
        if row is None:
            conn.rollback()
            raise PermissionError(
                'Customer appointment access denied.'
            )
        status = str(row['status'])
        if status == 'canceled':
            conn.rollback()
            return _appointment_from_row(row)
        if status not in {'pending', 'confirmed'}:
            conn.rollback()
            raise ValueError(
                'Only pending or confirmed appointments can be canceled.'
            )

        now = tenant_auth.now()
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET status='canceled',updated_at=?
            WHERE organization_id=?
              AND id=?
              AND customer_user_id=?
            ''',
            (
                now,
                checked.organization_id,
                int(appointment_id),
                checked.user_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,'canceled',?,?,?)
            ''',
            (
                int(appointment_id),
                checked.organization_id,
                status,
                checked.user_id,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        updated = _owned_row(
            conn,
            checked.organization_id,
            checked.user_id,
            appointment_id,
        )
    result = _appointment_from_row(updated)
    scheduling_notifications.cancel_scheduled_notifications(
        checked.organization_slug,
        result.id,
    )
    return result


def reschedule_customer_appointment(
    scope: portal_tenancy.CustomerScope,
    appointment_id: int,
    *,
    start_at: int,
    now: int | None = None,
) -> scheduling_appointments.Appointment:
    checked = portal_auth.revalidate_customer_scope(scope)
    appointment = _owned_appointment(checked, appointment_id)
    if appointment.status not in {'pending', 'confirmed'}:
        raise ValueError(
            'Only pending or confirmed appointments can be rescheduled.'
        )

    calendar = scheduling_calendars.get_calendar(
        checked.organization_slug, appointment.calendar_id
    )
    service = scheduling_calendars.get_service_type(
        checked.organization_slug, appointment.service_id
    )
    if (
        calendar is None
        or calendar.status != 'published'
        or service is None
        or service.status != 'published'
        or calendar.site_id is None
    ):
        raise CustomerSlotUnavailable(
            'Appointment is no longer eligible for online rescheduling.'
        )

    site = _published_site_by_id(
        checked.organization_slug, calendar.site_id
    )
    if site is None:
        raise CustomerSlotUnavailable(
            'Appointment site is no longer published.'
        )

    current = int(time.time()) if now is None else int(now)
    _, _, resources = scheduling_public._eligible_resources_for_slot(
        checked.organization_slug,
        site.slug,
        calendar_slug=calendar.slug,
        service_slug=service.slug,
        start_at=int(start_at),
        now=current,
    )
    if not resources:
        raise CustomerSlotUnavailable(
            'The requested reschedule slot is unavailable.'
        )

    for resource in sorted(resources, key=lambda item: item.id):
        try:
            updated = _reschedule_owned(
                checked,
                appointment,
                resource,
                int(start_at),
            )
            scheduling_notifications.rebuild_reminders(
                checked.organization_slug,
                updated.id,
                now=current,
            )
            return updated
        except scheduling_appointments.AppointmentConflictError:
            continue

    raise CustomerSlotUnavailable(
        'The requested reschedule slot was claimed by another booking.'
    )


def _reschedule_owned(
    scope: portal_tenancy.CustomerScope,
    appointment: scheduling_appointments.Appointment,
    resource: scheduling_availability.SchedulingResource,
    start_at: int,
) -> scheduling_appointments.Appointment:
    duration = appointment.duration_minutes
    before = appointment.buffer_before_minutes
    after = appointment.buffer_after_minutes
    end_at = start_at + duration * 60
    block_start = start_at - before * 60
    block_end = end_at + after * 60
    if block_start < 0:
        raise ValueError(
            'Appointment buffer would precede the UTC epoch.'
        )

    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = _owned_row(
            conn,
            scope.organization_id,
            scope.user_id,
            appointment.id,
        )
        if row is None:
            conn.rollback()
            raise PermissionError(
                'Customer appointment access denied.'
            )
        if str(row['status']) not in {'pending', 'confirmed'}:
            conn.rollback()
            raise ValueError(
                'Appointment can no longer be rescheduled.'
            )

        eligible = conn.execute(
            '''
            SELECT 1
            FROM scheduling_service_resources sr
            JOIN scheduling_resources r
              ON r.id=sr.resource_id
             AND r.organization_id=sr.organization_id
            WHERE sr.organization_id=?
              AND sr.service_id=?
              AND sr.resource_id=?
              AND r.calendar_id=?
              AND r.status='active'
            LIMIT 1
            ''',
            (
                scope.organization_id,
                appointment.service_id,
                resource.id,
                appointment.calendar_id,
            ),
        ).fetchone()
        if eligible is None:
            conn.rollback()
            raise PermissionError(
                'Reschedule resource is no longer eligible.'
            )

        conflict = conn.execute(
            '''
            SELECT id
            FROM scheduling_appointments
            WHERE organization_id=?
              AND resource_id=?
              AND id!=?
              AND status IN ('pending','confirmed')
              AND block_start_at < ?
              AND block_end_at > ?
            LIMIT 1
            ''',
            (
                scope.organization_id,
                resource.id,
                appointment.id,
                block_end,
                block_start,
            ),
        ).fetchone()
        if conflict is not None:
            conn.rollback()
            raise scheduling_appointments.AppointmentConflictError(
                'Appointment conflicts with an existing resource booking.'
            )

        changed_at = tenant_auth.now()
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET resource_id=?,start_at=?,end_at=?,
                block_start_at=?,block_end_at=?,updated_at=?
            WHERE organization_id=?
              AND id=?
              AND customer_user_id=?
            ''',
            (
                resource.id,
                start_at,
                end_at,
                block_start,
                block_end,
                changed_at,
                scope.organization_id,
                appointment.id,
                scope.user_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,?,?,'customer_rescheduled',?)
            ''',
            (
                appointment.id,
                scope.organization_id,
                str(row['status']),
                str(row['status']),
                scope.user_id,
                changed_at,
            ),
        )
        conn.commit()
        updated = _owned_row(
            conn,
            scope.organization_id,
            scope.user_id,
            appointment.id,
        )
    return _appointment_from_row(updated)


def _owned_appointment(
    scope: portal_tenancy.CustomerScope,
    appointment_id: int,
) -> scheduling_appointments.Appointment:
    appointment = scheduling_appointments.get_appointment(
        scope.organization_slug, int(appointment_id)
    )
    if (
        appointment is None
        or appointment.customer_user_id != scope.user_id
    ):
        raise PermissionError(
            'Customer appointment access denied.'
        )
    return appointment


def _owned_row(
    conn,
    organization_id: int,
    user_id: int,
    appointment_id: int,
):
    return conn.execute(
        '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=?
          AND a.id=?
          AND a.customer_user_id=?
        LIMIT 1
        ''',
        (
            int(organization_id),
            int(appointment_id),
            int(user_id),
        ),
    ).fetchone()


def _published_site_by_id(
    organization_slug: str,
    site_id: int,
):
    for site in tenant_sites.list_sites(
        organization_slug, include_archived=True
    ):
        if site.id == int(site_id) and site.status == 'published':
            return site
    return None


def _appointment_from_row(row):
    return scheduling_appointments._appointment_from_row(row)


def _reason(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        clean = 'customer_canceled'
    if len(clean) > 500:
        raise ValueError(
            'Customer cancellation reason must be 500 characters or fewer.'
        )
    return clean
