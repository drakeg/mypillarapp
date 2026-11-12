from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

import ai_boundary
import ai_settings
import tenant_auth


TASK_TYPES = {
    'draft',
    'summary',
    'suggested_reply',
    'knowledge_search',
}
USAGE_STATUSES = {
    'success',
    'rejected_before_call',
    'provider_error',
    'timeout',
    'quota_limit',
    'invalid_response',
}
MAX_TASK_TYPE_LENGTH = 64
MAX_PROVIDER_NAME_LENGTH = 80
MAX_MODEL_ID_LENGTH = 160
MAX_TIMEOUT_SECONDS = 120
ROLLING_WINDOW_SECONDS = 24 * 60 * 60
AI_KILL_SWITCH_ENV = 'MADMALLARD_AI_KILL_SWITCH'


@dataclass(frozen=True)
class ProviderResult:
    text: str
    input_units: int
    output_units: int


class AIProvider(Protocol):
    provider_name: str
    model_id: str

    def generate(
        self,
        prompt: str,
        *,
        max_output_units: int,
        timeout_seconds: int,
    ) -> ProviderResult:
        ...


@dataclass(frozen=True)
class AIUsageRecord:
    id: int
    organization_id: int
    organization_slug: str
    task_type: str
    provider_name: str
    model_id: str
    input_units: int
    output_units: int
    total_units: int
    status: str
    created_at: int


@dataclass(frozen=True)
class AIOperationalSummary:
    organization_slug: str
    total_events: int
    successful_events: int
    failed_events: int
    total_units: int
    failure_rate: float
    by_status: dict[str, int]
    by_task: dict[str, int]
    by_model: dict[str, int]


@dataclass(frozen=True)
class AIExecutionResult:
    text: str
    usage: AIUsageRecord


class AIExecutionError(RuntimeError):
    pass


def kill_switch_enabled() -> bool:
    return os.environ.get(AI_KILL_SWITCH_ENV, '').strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


def ensure_schema() -> None:
    ai_settings.ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='ai_usage_events'"
        ).fetchone()
        if row and 'rejected_before_call' not in str(row['sql'] or ''):
            conn.execute(
                'ALTER TABLE ai_usage_events RENAME TO ai_usage_events_legacy'
            )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS ai_usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                model_id TEXT NOT NULL,
                input_units INTEGER NOT NULL,
                output_units INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                CHECK(input_units >= 0),
                CHECK(output_units >= 0),
                CHECK(status IN (
                    'success','rejected_before_call','provider_error',
                    'timeout','quota_limit','invalid_response'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
        legacy = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='ai_usage_events_legacy'"
        ).fetchone()
        if legacy:
            conn.execute(
                '''
                INSERT INTO ai_usage_events(
                    id, organization_id, task_type, provider_name, model_id,
                    input_units, output_units, status, created_at
                )
                SELECT id, organization_id, task_type, provider_name, model_id,
                       input_units, output_units, status, created_at
                FROM ai_usage_events_legacy
                '''
            )
            conn.execute('DROP TABLE ai_usage_events_legacy')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_ai_usage_org_created '
            'ON ai_usage_events(organization_id, created_at DESC, id DESC)'
        )
        conn.commit()


def execute(
    user_id: int,
    organization_slug: str,
    *,
    task_type: str,
    prompt: str,
    requested_input_units: int,
    requested_output_units: int,
    provider: AIProvider,
    timeout_seconds: int = 30,
) -> AIExecutionResult:
    clean_task = _clean_task_type(task_type)
    clean_prompt = prompt if isinstance(prompt, str) else str(prompt or '')
    clean_timeout = _bounded_timeout(timeout_seconds)
    provider_name = _bounded_label(
        getattr(provider, 'provider_name', ''),
        'AI provider name',
        MAX_PROVIDER_NAME_LENGTH,
    )
    model_id = _bounded_label(
        getattr(provider, 'model_id', ''),
        'AI model identifier',
        MAX_MODEL_ID_LENGTH,
    )

    scope = ai_boundary.authorize_request(user_id, organization_slug)
    if kill_switch_enabled():
        _record_usage(
            scope.organization_id,
            scope.organization_slug,
            clean_task,
            provider_name,
            model_id,
            0,
            0,
            'rejected_before_call',
        )
        raise PermissionError('AI is temporarily disabled by the operational kill switch.')

    rolling_used = rolling_usage_units(scope.organization_slug)
    try:
        scope, settings = ai_settings.require_usage_allowed(
            user_id,
            scope.organization_slug,
            requested_input_units=requested_input_units,
            requested_output_units=requested_output_units,
            rolling_used_units=rolling_used,
        )
    except PermissionError as exc:
        status = (
            'quota_limit'
            if 'limit exceeded' in str(exc).lower()
            else 'rejected_before_call'
        )
        _record_usage(
            scope.organization_id,
            scope.organization_slug,
            clean_task,
            provider_name,
            model_id,
            0,
            0,
            status,
        )
        raise

    try:
        response = provider.generate(
            clean_prompt,
            max_output_units=min(
                int(requested_output_units), settings.max_output_units
            ),
            timeout_seconds=clean_timeout,
        )
    except TimeoutError as exc:
        _record_usage(
            scope.organization_id,
            scope.organization_slug,
            clean_task,
            provider_name,
            model_id,
            int(requested_input_units),
            0,
            'timeout',
        )
        raise AIExecutionError('AI provider request timed out.') from exc
    except Exception as exc:
        _record_usage(
            scope.organization_id,
            scope.organization_slug,
            clean_task,
            provider_name,
            model_id,
            int(requested_input_units),
            0,
            'provider_error',
        )
        raise AIExecutionError('AI provider request failed.') from exc

    try:
        text = _clean_output_text(response.text)
        actual_input = _bounded_usage(
            response.input_units, 'AI provider input usage'
        )
        actual_output = _bounded_usage(
            response.output_units, 'AI provider output usage'
        )
        if actual_input > settings.max_input_units:
            raise ValueError('AI provider input usage exceeded tenant limit.')
        if actual_output > settings.max_output_units:
            raise ValueError('AI provider output usage exceeded tenant limit.')
        if rolling_used + actual_input + actual_output > settings.rolling_limit_units:
            raise ValueError('AI provider usage exceeded tenant rolling limit.')
    except (AttributeError, TypeError, ValueError) as exc:
        _record_usage(
            scope.organization_id,
            scope.organization_slug,
            clean_task,
            provider_name,
            model_id,
            0,
            0,
            'invalid_response',
        )
        raise AIExecutionError('AI provider returned an invalid response.') from exc

    usage = _record_usage(
        scope.organization_id,
        scope.organization_slug,
        clean_task,
        provider_name,
        model_id,
        actual_input,
        actual_output,
        'success',
    )
    return AIExecutionResult(text=text, usage=usage)


def rolling_usage_units(
    organization_slug: str,
    *,
    now: int | None = None,
) -> int:
    ensure_schema()
    settings = ai_settings.get_settings(organization_slug)
    timestamp = tenant_auth.now() if now is None else int(now)
    cutoff = timestamp - ROLLING_WINDOW_SECONDS
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT COALESCE(SUM(input_units + output_units), 0) AS total
            FROM ai_usage_events
            WHERE organization_id=?
              AND created_at>=?
              AND status='success'
            ''',
            (settings.organization_id, cutoff),
        ).fetchone()
    return int(row['total'] or 0)


def list_usage(
    user_id: int,
    organization_slug: str,
    *,
    limit: int = 100,
) -> list[AIUsageRecord]:
    scope = ai_boundary.authorize_request(user_id, organization_slug)
    clean_limit = _bounded_list_limit(limit)
    ensure_schema()
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT e.*, o.slug AS organization_slug
            FROM ai_usage_events e
            JOIN auth_organizations o ON o.id=e.organization_id
            WHERE e.organization_id=?
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
            ''',
            (scope.organization_id, clean_limit),
        ).fetchall()
    return [_usage_from_row(row) for row in rows]


def operational_summary(
    user_id: int,
    organization_slug: str,
    *,
    since: int | None = None,
) -> AIOperationalSummary:
    scope = ai_boundary.authorize_request(user_id, organization_slug)
    ensure_schema()
    params: list[object] = [scope.organization_id]
    where = 'WHERE organization_id=?'
    if since is not None:
        where += ' AND created_at>=?'
        params.append(int(since))

    with tenant_auth.db() as conn:
        rows = conn.execute(
            f'''
            SELECT task_type, model_id, status,
                   COUNT(*) AS event_count,
                   COALESCE(SUM(input_units + output_units), 0) AS total_units
            FROM ai_usage_events
            {where}
            GROUP BY task_type, model_id, status
            ORDER BY task_type, model_id, status
            ''',
            params,
        ).fetchall()

    by_status = {status: 0 for status in sorted(USAGE_STATUSES)}
    by_task: dict[str, int] = {}
    by_model: dict[str, int] = {}
    total_events = 0
    total_units = 0
    for row in rows:
        count = int(row['event_count'])
        units = int(row['total_units'] or 0)
        status = str(row['status'])
        task = str(row['task_type'])
        model = str(row['model_id'])
        by_status[status] = by_status.get(status, 0) + count
        by_task[task] = by_task.get(task, 0) + count
        by_model[model] = by_model.get(model, 0) + count
        total_events += count
        total_units += units

    successful = by_status.get('success', 0)
    failed = total_events - successful
    return AIOperationalSummary(
        organization_slug=scope.organization_slug,
        total_events=total_events,
        successful_events=successful,
        failed_events=failed,
        total_units=total_units,
        failure_rate=(failed / total_events) if total_events else 0.0,
        by_status=by_status,
        by_task=by_task,
        by_model=by_model,
    )


def _record_usage(
    organization_id: int,
    organization_slug: str,
    task_type: str,
    provider_name: str,
    model_id: str,
    input_units: int,
    output_units: int,
    status: str,
) -> AIUsageRecord:
    ensure_schema()
    if status not in USAGE_STATUSES:
        raise ValueError('Unknown AI usage status.')
    input_units = _bounded_usage(input_units, 'AI input usage')
    output_units = _bounded_usage(output_units, 'AI output usage')
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO ai_usage_events(
                organization_id, task_type, provider_name, model_id,
                input_units, output_units, status, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ''',
            (
                int(organization_id),
                task_type,
                provider_name,
                model_id,
                input_units,
                output_units,
                status,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            '''
            SELECT e.*, o.slug AS organization_slug
            FROM ai_usage_events e
            JOIN auth_organizations o ON o.id=e.organization_id
            WHERE e.id=? AND e.organization_id=?
            ''',
            (cur.lastrowid, int(organization_id)),
        ).fetchone()
    return _usage_from_row(row)


def _usage_from_row(row) -> AIUsageRecord:
    input_units = int(row['input_units'])
    output_units = int(row['output_units'])
    return AIUsageRecord(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        task_type=str(row['task_type']),
        provider_name=str(row['provider_name']),
        model_id=str(row['model_id']),
        input_units=input_units,
        output_units=output_units,
        total_units=input_units + output_units,
        status=str(row['status']),
        created_at=int(row['created_at']),
    )


def _clean_task_type(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in TASK_TYPES:
        raise ValueError('Unknown AI task type.')
    return clean


def _clean_output_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('AI provider output must be text.')
    return value


def _bounded_label(value: str, label: str, maximum: int) -> str:
    clean = (value or '').strip()
    if not clean or len(clean) > maximum:
        raise ValueError(f'{label} must contain 1 to {maximum} characters.')
    return clean


def _bounded_timeout(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('AI timeout must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('AI timeout must be an integer.') from exc
    if clean < 1 or clean > MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f'AI timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds.'
        )
    return clean


def _bounded_usage(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be an integer.') from exc
    if clean < 0:
        raise ValueError(f'{label} cannot be negative.')
    return clean


def _bounded_list_limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('AI usage list limit must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('AI usage list limit must be an integer.') from exc
    if clean < 1 or clean > 500:
        raise ValueError('AI usage list limit must be between 1 and 500.')
    return clean
