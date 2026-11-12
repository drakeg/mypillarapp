from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
    'provider_error',
    'timeout',
    'invalid_response',
}
MAX_TASK_TYPE_LENGTH = 64
MAX_PROVIDER_NAME_LENGTH = 80
MAX_MODEL_ID_LENGTH = 160
MAX_TIMEOUT_SECONDS = 120
ROLLING_WINDOW_SECONDS = 24 * 60 * 60


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
class AIExecutionResult:
    text: str
    usage: AIUsageRecord


class AIExecutionError(RuntimeError):
    pass


def ensure_schema() -> None:
    ai_settings.ensure_schema()
    with tenant_auth.db() as conn:
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
                    'success','provider_error','timeout','invalid_response'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
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

    rolling_used = rolling_usage_units(organization_slug)
    scope, settings = ai_settings.require_usage_allowed(
        user_id,
        organization_slug,
        requested_input_units=requested_input_units,
        requested_output_units=requested_output_units,
        rolling_used_units=rolling_used,
    )

    try:
        response = provider.generate(
            clean_prompt,
            max_output_units=min(
                int(requested_output_units), settings.max_output_units
            ),
            timeout_seconds=clean_timeout,
        )
    except TimeoutError as exc:
        usage = _record_usage(
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
        usage = _record_usage(
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
        actual_input = _bounded_usage(response.input_units, 'AI provider input usage')
        actual_output = _bounded_usage(response.output_units, 'AI provider output usage')
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
    scope = ai_settings.ai_boundary.authorize_request(
        user_id, organization_slug
    )
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
