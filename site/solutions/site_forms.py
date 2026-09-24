from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sqlite3

import tenant_auth
import tenant_sites


FORM_STATUSES = ('draft', 'published', 'archived')
FIELD_TYPES = ('text', 'email', 'textarea', 'select')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_FIELD_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


@dataclass(frozen=True)
class PublicForm:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    slug: str
    title: str
    submit_label: str
    status: str
    fields: tuple[dict[str, object], ...]
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                submit_label TEXT NOT NULL DEFAULT 'Submit',
                status TEXT NOT NULL DEFAULT 'draft',
                fields_json TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(site_id, slug),
                CHECK(status IN ('draft', 'published', 'archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    return tenant_sites.get_site(organization_slug, site_slug)


def _slug(value: str) -> str:
    value = (value or '').strip().lower()
    if not value or not _SLUG_RE.fullmatch(value):
        raise ValueError(
            'Form slug must contain lowercase letters/numbers separated by hyphens.'
        )
    return value


def _status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in FORM_STATUSES:
        raise ValueError(f'Unknown form status: {value}')
    return value


def validate_fields(fields: list[dict[str, object]]) -> tuple[dict[str, object], ...]:
    if not isinstance(fields, list):
        raise ValueError('Form fields must be a list.')
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in fields:
        if not isinstance(raw, dict):
            raise ValueError('Each form field must be an object.')
        name = str(raw.get('name', '')).strip().lower()
        label = str(raw.get('label', '')).strip()
        field_type = str(raw.get('type', 'text')).strip().lower()
        required = bool(raw.get('required', False))
        placeholder = str(raw.get('placeholder', '')).strip()
        if not _FIELD_NAME_RE.fullmatch(name):
            raise ValueError('Form field names must use lowercase letters, numbers, and underscores.')
        if name in seen:
            raise ValueError(f'Duplicate form field name: {name}')
        if not label:
            raise ValueError('Form field label is required.')
        if field_type not in FIELD_TYPES:
            raise ValueError(f'Unsupported form field type: {field_type}')
        field: dict[str, object] = {
            'name': name,
            'label': label,
            'type': field_type,
            'required': required,
        }
        if placeholder:
            field['placeholder'] = placeholder
        if field_type == 'select':
            options = raw.get('options', [])
            if not isinstance(options, list):
                raise ValueError('Select field options must be a list.')
            clean_options = [str(option).strip() for option in options if str(option).strip()]
            if not clean_options or len(set(clean_options)) != len(clean_options):
                raise ValueError('Select fields require unique non-empty options.')
            field['options'] = clean_options
        normalized.append(field)
        seen.add(name)
    return tuple(normalized)


def create_form(
    organization_slug: str,
    site_slug: str,
    *,
    slug: str,
    title: str,
    fields: list[dict[str, object]],
    submit_label: str = 'Submit',
    status: str = 'draft',
) -> PublicForm:
    site = _site(organization_slug, site_slug)
    if not site:
        raise ValueError('Site not found.')
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    clean_title = (title or '').strip()
    clean_submit = (submit_label or '').strip()
    if not clean_title:
        raise ValueError('Form title is required.')
    if not clean_submit:
        raise ValueError('Submit label is required.')
    clean_fields = validate_fields(fields)

    ensure_schema()
    timestamp = tenant_auth.now()
    try:
        with tenant_auth.db() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO site_builder_forms(
                    site_id, slug, title, submit_label, status, fields_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    site.id,
                    _slug(slug),
                    clean_title,
                    clean_submit,
                    _status(status),
                    json.dumps(clean_fields, separators=(',', ':')),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            row = _select(conn, site.id, int(cursor.lastrowid))
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            'A form with that slug already exists for this site.'
        ) from exc
    return _from_row(row)


def get_form(
    organization_slug: str,
    site_slug: str,
    form_slug: str,
) -> PublicForm | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT f.*, o.slug AS organization_slug, s.slug AS site_slug
            FROM site_builder_forms f
            JOIN site_builder_sites s ON s.id = f.site_id
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE f.site_id = ? AND f.slug = ?
            LIMIT 1
            ''',
            (site.id, (form_slug or '').strip().lower()),
        ).fetchone()
    return _from_row(row) if row else None


def list_forms(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[PublicForm]:
    site = _site(organization_slug, site_slug)
    if not site:
        return []
    ensure_schema()
    sql = '''
        SELECT f.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_forms f
        JOIN site_builder_sites s ON s.id = f.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE f.site_id = ?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND f.status = 'published'"
    elif not include_archived:
        sql += " AND f.status != 'archived'"
    sql += ' ORDER BY f.title COLLATE NOCASE, f.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_form(
    organization_slug: str,
    site_slug: str,
    form_slug: str,
    *,
    title: str | None = None,
    fields: list[dict[str, object]] | None = None,
    submit_label: str | None = None,
    status: str | None = None,
) -> PublicForm | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    existing = get_form(organization_slug, site_slug, form_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived forms cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []
    if title is not None:
        clean = title.strip()
        if not clean:
            raise ValueError('Form title is required.')
        assignments.append('title = ?')
        params.append(clean)
    if submit_label is not None:
        clean = submit_label.strip()
        if not clean:
            raise ValueError('Submit label is required.')
        assignments.append('submit_label = ?')
        params.append(clean)
    if status is not None:
        assignments.append('status = ?')
        params.append(_status(status))
    if fields is not None:
        clean_fields = validate_fields(fields)
        assignments.append('fields_json = ?')
        params.append(json.dumps(clean_fields, separators=(',', ':')))
    if not assignments:
        return existing

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend([site.id, existing.id])
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE site_builder_forms
            SET {', '.join(assignments)}
            WHERE site_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, site.id, existing.id)
    return _from_row(row)


def archive_form(
    organization_slug: str,
    site_slug: str,
    form_slug: str,
) -> PublicForm | None:
    existing = get_form(organization_slug, site_slug, form_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        return existing
    return update_form(
        organization_slug,
        site_slug,
        form_slug,
        status='archived',
    )


def _select(conn, site_id: int, form_id: int):
    return conn.execute(
        '''
        SELECT f.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_forms f
        JOIN site_builder_sites s ON s.id = f.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE f.site_id = ? AND f.id = ?
        LIMIT 1
        ''',
        (site_id, form_id),
    ).fetchone()


def _from_row(row) -> PublicForm:
    try:
        fields = json.loads(row['fields_json'])
    except (TypeError, json.JSONDecodeError):
        fields = []
    return PublicForm(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        slug=str(row['slug']),
        title=str(row['title']),
        submit_label=str(row['submit_label']),
        status=str(row['status']),
        fields=tuple(fields if isinstance(fields, list) else []),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
