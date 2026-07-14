#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import py_compile
import subprocess

ROOT = Path(subprocess.check_output(
    ['git', 'rev-parse', '--show-toplevel'], text=True
).strip())
AUTH_PATH = ROOT / 'site/solutions/tenant_auth.py'
CHANGELOG_PATH = ROOT / 'CHANGELOG.md'

source = AUTH_PATH.read_text(encoding='utf-8')
changelog = CHANGELOG_PATH.read_text(encoding='utf-8')

import_marker = "from pathlib import Path\n"
import_replacement = "from collections.abc import Iterator\nfrom contextlib import contextmanager\nfrom pathlib import Path\n"

old_db = """def db() -> sqlite3.Connection:\n    DATA_DIR.mkdir(parents=True, exist_ok=True)\n    conn = sqlite3.connect(DB_PATH)\n    conn.row_factory = sqlite3.Row\n    conn.execute('PRAGMA foreign_keys = ON')\n    ensure_schema(conn)\n    return conn\n"""

new_db = """@contextmanager\ndef db() -> Iterator[sqlite3.Connection]:\n    DATA_DIR.mkdir(parents=True, exist_ok=True)\n    conn = sqlite3.connect(DB_PATH)\n    try:\n        conn.row_factory = sqlite3.Row\n        conn.execute('PRAGMA foreign_keys = ON')\n        ensure_schema(conn)\n        yield conn\n    finally:\n        conn.close()\n"""

if new_db not in source:
    if old_db not in source:
        raise SystemExit('Expected tenant_auth.db implementation was not found.')
    if 'from contextlib import contextmanager\n' not in source:
        if import_marker not in source:
            raise SystemExit('Expected import marker was not found.')
        source = source.replace(import_marker, import_replacement, 1)
    source = source.replace(old_db, new_db, 1)

entry = '- Closed every tenant-auth SQLite connection when its context exits.\n'
if entry not in changelog:
    marker = '### Fixed\n'
    if marker in changelog:
        changelog = changelog.replace(marker, marker + '\n' + entry, 1)
    else:
        marker = '### Current implementation baseline\n'
        if marker not in changelog:
            raise SystemExit('Expected CHANGELOG insertion point was not found.')
        changelog = changelog.replace(
            marker,
            '### Fixed\n\n' + entry + '\n' + marker,
            1,
        )

AUTH_PATH.write_text(source, encoding='utf-8')
CHANGELOG_PATH.write_text(changelog, encoding='utf-8')

py_compile.compile(str(AUTH_PATH), doraise=True)
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
subprocess.run(
    ['python3', '-W', 'error::ResourceWarning', '-m', 'unittest',
     'discover', '-s', 'tests', '-p', 'test_*.py', '-v'],
    cwd=ROOT,
    check=True,
)

print('SQLite connection fix applied and regression tests passed.')
subprocess.run(['git', 'status', '--short'], cwd=ROOT, check=True)
