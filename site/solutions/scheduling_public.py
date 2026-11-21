from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

import scheduling_appointments
import scheduling_availability
import scheduling_boundary
import scheduling_calendars
import tenant_sites


DEFAULT_SLOT_STEP_MINUTES = 15
MAX_PUBLIC_WINDOW_DAYS = 31


@dataclass(frozen=True)
class PublicService:
    calendar_slug: str
    calendar_name: str
    timezone: str
    service_slug: str
    service_name: str
    description: str
    duration_minutes: int


@dataclass(frozen=True)
class PublicSlot:
    calendar_slug: str
    service_slug: str
    start_at: int
    end_at: int
    timezone: str
    available_resource_count: int


def list_public_services(
    organization_slug: str,
    site_slug: str,
) -> list[PublicService]:
    site = _published_site(organization_slug, site_slug)
    if site is None:
        return []
    services: list[PublicService] = []
    for calendar in scheduling_calendars.list_calendars(
        organization_slug, published_only=True
    ):
        if calendar.site_id != site.id:
            continue
        for service in scheduling_calendars.list_service_types(
            organization_slug,
            calendar.id,
            published_only=True,
        ):
            services.append(
                PublicService(
                    calendar_slug=calendar.slug,
                    calendar_name=calendar.name,
                    timezone=calendar.timezone,
                    service_slug=service.slug,
                    service_name=service.name,
                    description=service.description,
                    duration_minutes=service.duration_minutes,
                )
            )
    return sorted(
        services,
        key=lambda item: (
            item.calendar_name.casefold(),
            item.service_name.casefold(),
            item.service_slug,
        ),
    )


def list_public_slots(
    organization_slug: str,
    site_slug: str,
    *,
    calendar_slug: str,
    service_slug: str,
    window_start_at: int,
    window_end_at: int,
    now: int | None = None,
    step_minutes: int = DEFAULT_SLOT_STEP_MINUTES,
) -> list[PublicSlot]:
    site = _published_site(organization_slug, site_slug)
    if site is None:
        return []
    calendar = _public_calendar(
        organization_slug, site.id, calendar_slug
    )
    if calendar is None:
        return []
    service = _public_service(
        organization_slug, calendar.id, service_slug
    )
    if service is None:
        return []

    requested_start, requested_end = scheduling_boundary.validate_utc_range(
        window_start_at, window_end_at
    )
    if requested_end - requested_start > MAX_PUBLIC_WINDOW_DAYS * 86400:
        raise ValueError(
            f'Public availability window cannot exceed '
            f'{MAX_PUBLIC_WINDOW_DAYS} days.'
        )
    clean_step = _step_minutes(step_minutes)
    current = int(now if now is not None else __import__('time').time())
    notice_start = current + (calendar.minimum_notice_minutes * 60)
    horizon_end = current + (calendar.booking_horizon_days * 86400)
    effective_start = max(requested_start, notice_start)
    effective_end = min(requested_end, horizon_end)
    if effective_end <= effective_start:
        return []

    resources = scheduling_availability.list_service_resources(
        organization_slug, service.id
    )
    if not resources:
        return []

    counts: dict[int, int] = {}
    slot_end_by_start: dict[int, int] = {}
    for resource in resources:
        for start_at in _resource_candidate_starts(
            organization_slug,
            calendar,
            service,
            resource,
            effective_start,
            effective_end,
            clean_step,
        ):
            end_at = start_at + service.duration_minutes * 60
            counts[start_at] = counts.get(start_at, 0) + 1
            slot_end_by_start[start_at] = end_at

    return [
        PublicSlot(
            calendar_slug=calendar.slug,
            service_slug=service.slug,
            start_at=start_at,
            end_at=slot_end_by_start[start_at],
            timezone=calendar.timezone,
            available_resource_count=counts[start_at],
        )
        for start_at in sorted(counts)
    ]


def _resource_candidate_starts(
    organization_slug: str,
    calendar: scheduling_calendars.SchedulingCalendar,
    service: scheduling_calendars.ServiceType,
    resource: scheduling_availability.SchedulingResource,
    effective_start: int,
    effective_end: int,
    step_minutes: int,
):
    zone_name = calendar.timezone
    zone_start = scheduling_boundary.utc_epoch_to_local(
        effective_start, zone_name
    )
    zone_end = scheduling_boundary.utc_epoch_to_local(
        effective_end - 1, zone_name
    )
    availability = scheduling_availability.list_weekly_availability(
        organization_slug, resource.id
    )
    by_weekday: dict[int, list[scheduling_availability.WeeklyAvailability]] = {}
    for row in availability:
        by_weekday.setdefault(row.weekday, []).append(row)

    current_date = zone_start.date()
    final_date = zone_end.date()
    while current_date <= final_date:
        for window in by_weekday.get(current_date.weekday(), []):
            starts = _window_candidate_starts(
                current_date,
                window,
                calendar.timezone,
                service,
                step_minutes,
            )
            for start_at, block_start, block_end in starts:
                if start_at < effective_start:
                    continue
                end_at = start_at + service.duration_minutes * 60
                if end_at > effective_end:
                    continue
                if _is_blacked_out(
                    organization_slug,
                    resource.id,
                    block_start,
                    block_end,
                ):
                    continue
                if not scheduling_appointments.resource_is_free(
                    organization_slug,
                    resource.id,
                    block_start_at=block_start,
                    block_end_at=block_end,
                ):
                    continue
                yield start_at
        current_date += timedelta(days=1)


def _window_candidate_starts(
    local_date,
    window: scheduling_availability.WeeklyAvailability,
    timezone_name: str,
    service: scheduling_calendars.ServiceType,
    step_minutes: int,
):
    midnight = datetime.combine(local_date, time.min)
    local_window_start = midnight + timedelta(
        minutes=window.start_minute
    )
    local_window_end = midnight + timedelta(
        minutes=window.end_minute
    )
    try:
        window_start = scheduling_boundary.local_to_utc_epoch(
            local_window_start, timezone_name
        )
        window_end = scheduling_boundary.local_to_utc_epoch(
            local_window_end, timezone_name
        )
    except ValueError:
        return []

    step_seconds = step_minutes * 60
    duration_seconds = service.duration_minutes * 60
    before_seconds = service.buffer_before_minutes * 60
    after_seconds = service.buffer_after_minutes * 60

    first_start = window_start + before_seconds
    candidate = _ceil_to_step(first_start, step_seconds)
    rows = []
    while True:
        end_at = candidate + duration_seconds
        block_start = candidate - before_seconds
        block_end = end_at + after_seconds
        if block_end > window_end:
            break
        rows.append((candidate, block_start, block_end))
        candidate += step_seconds
    return rows


def _is_blacked_out(
    organization_slug: str,
    resource_id: int,
    block_start: int,
    block_end: int,
) -> bool:
    rows = scheduling_availability.list_blackouts(
        organization_slug,
        resource_id,
        start_at=block_start,
        end_at=block_end,
    )
    return bool(rows)


def _published_site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None or site.status != 'published':
        return None
    return site


def _public_calendar(
    organization_slug: str,
    site_id: int,
    calendar_slug: str,
):
    clean_slug = (calendar_slug or '').strip().lower()
    for calendar in scheduling_calendars.list_calendars(
        organization_slug, published_only=True
    ):
        if calendar.site_id == site_id and calendar.slug == clean_slug:
            return calendar
    return None


def _public_service(
    organization_slug: str,
    calendar_id: int,
    service_slug: str,
):
    clean_slug = (service_slug or '').strip().lower()
    for service in scheduling_calendars.list_service_types(
        organization_slug,
        calendar_id,
        published_only=True,
    ):
        if service.slug == clean_slug:
            return service
    return None


def _step_minutes(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Slot step must be an integer number of minutes.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Slot step must be an integer number of minutes.'
        ) from exc
    if clean < 5 or clean > 120 or clean % 5:
        raise ValueError(
            'Slot step must be 5–120 minutes in 5-minute increments.'
        )
    return clean


def _ceil_to_step(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step
