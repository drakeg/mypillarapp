from __future__ import annotations

from dataclasses import dataclass

import scheduling_appointments
import scheduling_availability
import scheduling_boundary
import scheduling_calendars
import scheduling_notifications


@dataclass(frozen=True)
class SchedulingAdminOverview:
    organization_slug: str
    calendars: tuple[scheduling_calendars.SchedulingCalendar, ...]
    services: tuple[scheduling_calendars.ServiceType, ...]
    resources: tuple[scheduling_availability.SchedulingResource, ...]
    appointments: tuple[scheduling_appointments.Appointment, ...]


def overview(
    actor_user_id: int,
    organization_slug: str,
    *,
    calendar_id: int | None = None,
    start_at: int | None = None,
    end_at: int | None = None,
) -> SchedulingAdminOverview:
    scope = scheduling_boundary.require(
        actor_user_id, organization_slug, 'view'
    )
    calendars = scheduling_calendars.list_calendars(
        scope.organization_slug
    )
    selected = None
    if calendar_id is not None:
        selected = scheduling_calendars.get_calendar(
            scope.organization_slug, calendar_id
        )
        if selected is None:
            raise PermissionError('Scheduling calendar access denied.')

    services: list[scheduling_calendars.ServiceType] = []
    resources: list[scheduling_availability.SchedulingResource] = []
    if selected is not None:
        services = scheduling_calendars.list_service_types(
            scope.organization_slug,
            selected.id,
        )
        resources = scheduling_availability.list_resources(
            scope.organization_slug,
            selected.id,
        )

    appointments = scheduling_appointments.list_appointments(
        scope.organization_slug,
        start_at=start_at,
        end_at=end_at,
        include_canceled=True,
    )
    if selected is not None:
        appointments = [
            item for item in appointments
            if item.calendar_id == selected.id
        ]

    return SchedulingAdminOverview(
        organization_slug=scope.organization_slug,
        calendars=tuple(calendars),
        services=tuple(services),
        resources=tuple(resources),
        appointments=tuple(appointments),
    )


def create_calendar(
    actor_user_id: int,
    organization_slug: str,
    **kwargs,
) -> scheduling_calendars.SchedulingCalendar:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_calendars.create_calendar(
        organization_slug, **kwargs
    )


def update_calendar(
    actor_user_id: int,
    organization_slug: str,
    calendar_id: int,
    **kwargs,
) -> scheduling_calendars.SchedulingCalendar | None:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_calendars.update_calendar(
        organization_slug,
        calendar_id,
        **kwargs,
    )


def create_service_type(
    actor_user_id: int,
    organization_slug: str,
    calendar_id: int,
    **kwargs,
) -> scheduling_calendars.ServiceType:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_calendars.create_service_type(
        organization_slug,
        calendar_id,
        **kwargs,
    )


def update_service_type(
    actor_user_id: int,
    organization_slug: str,
    service_id: int,
    **kwargs,
) -> scheduling_calendars.ServiceType | None:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_calendars.update_service_type(
        organization_slug,
        service_id,
        **kwargs,
    )


def create_resource(
    actor_user_id: int,
    organization_slug: str,
    calendar_id: int,
    **kwargs,
) -> scheduling_availability.SchedulingResource:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_availability.create_resource(
        organization_slug,
        calendar_id,
        **kwargs,
    )


def add_weekly_availability(
    actor_user_id: int,
    organization_slug: str,
    resource_id: int,
    **kwargs,
) -> scheduling_availability.WeeklyAvailability:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_availability.add_weekly_availability(
        organization_slug,
        resource_id,
        **kwargs,
    )


def add_blackout(
    actor_user_id: int,
    organization_slug: str,
    resource_id: int,
    **kwargs,
) -> scheduling_availability.BlackoutPeriod:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    return scheduling_availability.add_blackout(
        organization_slug,
        resource_id,
        **kwargs,
    )


def assign_service_resource(
    actor_user_id: int,
    organization_slug: str,
    *,
    service_id: int,
    resource_id: int,
) -> None:
    scheduling_boundary.require(
        actor_user_id, organization_slug, 'admin'
    )
    scheduling_availability.assign_service_resource(
        organization_slug,
        service_id=service_id,
        resource_id=resource_id,
    )


def create_appointment(
    actor_user_id: int,
    organization_slug: str,
    **kwargs,
) -> scheduling_appointments.Appointment:
    scope = scheduling_boundary.require(
        actor_user_id, organization_slug, 'manage'
    )
    appointment = scheduling_appointments.create_appointment(
        organization_slug,
        actor_user_id=scope.user_id,
        **kwargs,
    )
    scheduling_notifications.schedule_initial_notifications(
        organization_slug,
        appointment.id,
    )
    return appointment


def transition_appointment(
    actor_user_id: int,
    organization_slug: str,
    appointment_id: int,
    *,
    to_status: str,
    reason: str = '',
) -> scheduling_appointments.Appointment:
    scope = scheduling_boundary.require(
        actor_user_id, organization_slug, 'manage'
    )
    appointment = scheduling_appointments.transition_appointment(
        organization_slug,
        appointment_id,
        to_status=to_status,
        actor_user_id=scope.user_id,
        reason=reason,
    )
    if appointment.status in {'canceled', 'completed', 'no_show'}:
        scheduling_notifications.cancel_scheduled_notifications(
            organization_slug,
            appointment.id,
        )
    return appointment
