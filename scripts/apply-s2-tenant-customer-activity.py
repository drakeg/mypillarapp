from pathlib import Path

path = Path('site/solutions/tenant_auth.py')
text = path.read_text(encoding='utf-8')

if 'import tenant_conversations\n' not in text:
    text = text.replace('import messaging\n', 'import messaging\nimport tenant_conversations\n', 1)

start = text.index('def _customer_activity(')
end = text.index('\ndef _fmt_timestamp(', start)
replacement = '''def _customer_activity(user: sqlite3.Row) -> tuple[dict[str, int], list[sqlite3.Row]]:
    email = str(user['email']).strip().lower()
    tenant_slug = str(user['organization_slug']).strip().lower()
    tenant_conversations.ensure_schema()
    with db() as conn:
        counts_row = conn.execute(
            \"\"\"SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status NOT IN ('closed', 'spam') THEN 1 ELSE 0 END) AS open_count,
                      SUM(CASE WHEN kind = 'project_request' THEN 1 ELSE 0 END) AS request_count,
                      SUM(CASE WHEN kind = 'chat' THEN 1 ELSE 0 END) AS conversation_count
               FROM conversations
               WHERE organization_slug = ?
                 AND lower(COALESCE(email, '')) = ?\"\"\",
            (tenant_slug, email),
        ).fetchone()
        recent = conn.execute(
            \"\"\"SELECT token, kind, subject, status, updated_at
               FROM conversations
               WHERE organization_slug = ?
                 AND lower(COALESCE(email, '')) = ?
               ORDER BY updated_at DESC LIMIT 8\"\"\",
            (tenant_slug, email),
        ).fetchall()
    return {
        'total': int(counts_row['total'] or 0),
        'open': int(counts_row['open_count'] or 0),
        'requests': int(counts_row['request_count'] or 0),
        'conversations': int(counts_row['conversation_count'] or 0),
    }, recent


def _customer_history(
    user: sqlite3.Row,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    return tenant_conversations.list_customer_conversations(
        str(user['organization_slug']),
        str(user['email']),
        kind,
    )


def _customer_conversation(
    user: sqlite3.Row,
    token: str,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    conversation = tenant_conversations.get_conversation(
        str(user['organization_slug']),
        token,
    )
    if not conversation or str(conversation['email'] or '').strip().lower() != str(user['email']).strip().lower():
        return None, []
    with db() as conn:
        messages = conn.execute(
            \"\"\"SELECT *
               FROM messages
               WHERE conversation_id = ? AND internal = 0
               ORDER BY created_at ASC, id ASC\"\"\",
            (conversation['id'],),
        ).fetchall()
    return conversation, messages

'''
text = text[:start] + replacement + text[end + 1:]
path.write_text(text, encoding='utf-8')

changelog = Path('CHANGELOG.md')
body = changelog.read_text(encoding='utf-8')
entry = '- Customer dashboard, request history, and conversation detail are isolated by the authenticated tenant.\n'
marker = '### Added\n\n'
if entry not in body:
    body = body.replace(marker, marker + entry, 1)
    changelog.write_text(body, encoding='utf-8')

print('Applied S2-T06 tenant-scoped customer activity.')
