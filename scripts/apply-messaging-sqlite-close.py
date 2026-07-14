#!/usr/bin/env python3
from pathlib import Path
import subprocess

root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
path = root / 'site/solutions/messaging.py'
text = path.read_text(encoding='utf-8')

old_import = "from pathlib import Path\nimport html\n"
new_import = "from collections.abc import Iterator\nfrom contextlib import contextmanager\nfrom pathlib import Path\nimport html\n"
if new_import not in text:
    if old_import not in text:
        raise SystemExit('Expected messaging import marker missing.')
    text = text.replace(old_import, new_import, 1)

old_start = "def db() -> sqlite3.Connection:\n    DATA_DIR.mkdir(parents=True, exist_ok=True)\n    conn = sqlite3.connect(DB_PATH)\n    conn.row_factory = sqlite3.Row\n"
new_start = "@contextmanager\ndef db() -> Iterator[sqlite3.Connection]:\n    DATA_DIR.mkdir(parents=True, exist_ok=True)\n    conn = sqlite3.connect(DB_PATH)\n    try:\n        conn.row_factory = sqlite3.Row\n"
if new_start not in text:
    if old_start not in text:
        raise SystemExit('Expected messaging db() marker missing.')
    text = text.replace(old_start, new_start, 1)

old_end = "    conn.commit()\n    return conn\n\n\ndef send_email"
new_end = "        conn.commit()\n        yield conn\n    finally:\n        conn.close()\n\n\ndef send_email"
if new_end not in text:
    if old_end not in text:
        raise SystemExit('Expected messaging db() return marker missing.')
    # Indent the full schema-initialization body inside try.
    start = text.index(new_start) + len(new_start)
    end = text.index(old_end, start)
    body = text[start:end]
    body = ''.join(('    ' + line if line.strip() else line) for line in body.splitlines(keepends=True))
    text = text[:start] + body + text[end:]
    text = text.replace(old_end, new_end, 1)

path.write_text(text, encoding='utf-8')
subprocess.run(['python3', '-m', 'py_compile', str(path)], check=True)
subprocess.run(['python3', '-W', 'error::ResourceWarning', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'], cwd=root, check=True)
subprocess.run(['git', 'diff', '--check'], cwd=root, check=True)
print('Messaging SQLite connection fix applied and tests passed.')
