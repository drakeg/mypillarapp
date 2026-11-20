#!/usr/bin/env python3
"""Conservative, idempotent README badge generation for this repository."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

START = "<!-- madmallard-badges:start -->"
END = "<!-- madmallard-badges:end -->"
SLUG = "drakeg/mypillarapp"
BADGE = "https://img.shields.io/badge/"

TECH = {
    "Python": ("Python", "3776AB", "python", "https://www.python.org/"),
    "Django": ("Django", "092E20", "django", "https://www.djangoproject.com/"),
    "SQLite": ("SQLite", "003B57", "sqlite", "https://www.sqlite.org/"),
    "Docker": ("Docker", "2496ED", "docker", "https://www.docker.com/"),
    "Docker Compose": ("Docker Compose", "2496ED", "docker", "https://docs.docker.com/compose/"),
    "Terraform": ("Terraform", "844FBA", "terraform", "https://www.terraform.io/"),
    "AWS": ("AWS", "232F3E", "amazonwebservices", "https://aws.amazon.com/"),
}


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def cmd(*args: str, cwd: Path) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detected(root: Path) -> list[str]:
    found: set[str] = set()

    dockerfiles = [
        path for path in (
            root / "Dockerfile",
            root / "app" / "Dockerfile",
            root / "site" / "solutions" / "Dockerfile",
        )
        if path.is_file()
    ]
    if dockerfiles:
        found.add("Docker")
    if any((root / name).is_file() for name in (
        "compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"
    )):
        found.update(("Docker", "Docker Compose"))

    python_evidence = [
        path for path in (
            root / "requirements.txt",
            root / "pyproject.toml",
            root / "app" / "requirements.txt",
            root / "app" / "pyproject.toml",
            *dockerfiles,
        )
        if path.is_file()
    ]
    if python_evidence:
        for path in python_evidence:
            text = read(path)
            if path.name != "Dockerfile" or re.search(r"(?im)^FROM\s+python:", text):
                found.add("Python")
                break

    django_text = "\n".join(
        read(path)
        for path in (
            root / "requirements.txt",
            root / "app" / "requirements.txt",
        )
        if path.is_file()
    )
    if re.search(r"(?im)^\s*django\s*(?:[=<>!~\[]|$)", django_text):
        found.add("Django")

    sqlite_evidence = (
        read(root / "app" / "project" / "settings.py")
        + "\n"
        + "\n".join(read(path) for path in (root / "site" / "solutions").glob("*.py"))
    )
    if "sqlite3" in sqlite_evidence:
        found.add("SQLite")

    terraform_root = root / "terraform"
    terraform_files = (
        list(terraform_root.rglob("*.tf"))
        if terraform_root.is_dir()
        else []
    )
    if terraform_files:
        found.add("Terraform")
    terraform_text = "\n".join(read(path) for path in terraform_files)
    if "hashicorp/aws" in terraform_text or re.search(r"(?m)^\s*provider\s+\"aws\"", terraform_text):
        found.add("AWS")

    return [name for name in TECH if name in found]


def shield(label: str, color: str, logo: str) -> str:
    encoded = quote(label, safe="").replace("-", "--")
    return f"{BADGE}{encoded}-{color}?logo={logo}&logoColor=white"


def workflow_files(root: Path) -> list[Path]:
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        return []
    return sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


def published_release_exists(root: Path) -> bool:
    return bool(
        cmd(
            "gh", "release", "view",
            "--repo", SLUG,
            "--json", "tagName",
            "--jq", ".tagName",
            cwd=root,
        )
    )


def license_file(root: Path) -> str | None:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        if (root / name).is_file():
            return name
    return None


def generate(root: Path) -> str:
    tech = []
    for name in detected(root):
        label, color, logo, link = TECH[name]
        tech.append(f"[![{name}]({shield(label, color, logo)})]({link})")

    status = []
    for workflow in workflow_files(root):
        path = quote(workflow.name, safe="")
        url = f"https://github.com/{SLUG}/actions/workflows/{path}"
        status.append(
            f"[![{workflow.stem}](https://github.com/{SLUG}/actions/workflows/{path}/badge.svg)]({url})"
        )

    license_name = license_file(root)
    if license_name:
        status.append(
            f"[![License](https://img.shields.io/github/license/{SLUG})]"
            f"(https://github.com/{SLUG}/blob/HEAD/{license_name})"
        )
    if published_release_exists(root):
        status.append(
            f"[![Release](https://img.shields.io/github/v/release/{SLUG})]"
            f"(https://github.com/{SLUG}/releases/latest)"
        )

    status.extend([
        f"[![Issues](https://img.shields.io/github/issues/{SLUG})](https://github.com/{SLUG}/issues)",
        f"[![Pull requests](https://img.shields.io/github/issues-pr/{SLUG})](https://github.com/{SLUG}/pulls)",
    ])

    lines = [START]
    if tech:
        lines.append(" ".join(tech))
    if status:
        lines.extend(["", " ".join(status)])
    lines.append(END)
    return "\n".join(lines)


def apply(root: Path, *, write: bool) -> tuple[bool, str]:
    target = root / "README.md"
    if not target.is_file():
        raise ValueError("README.md missing; refusing to create or replace it")

    original = read(target)
    block = generate(root)

    if original.count(START) != original.count(END) or original.count(START) > 1:
        raise ValueError("malformed or duplicate badge markers; manual repair required")

    if START in original:
        updated = (
            original[:original.index(START)]
            + block
            + original[original.index(END) + len(END):]
        )
    else:
        lines = original.splitlines(keepends=True)
        heading = next(
            (idx for idx, line in enumerate(lines) if line.startswith("# ")),
            None,
        )
        if heading is None:
            raise ValueError("README has no H1; refusing to guess placement")
        lines.insert(heading + 1, "\n" + block + "\n")
        updated = "".join(lines)

    if updated == original:
        return False, "unchanged"
    if write:
        target.write_text(updated, encoding="utf-8")
    return True, "updated" if write else "would update"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument(
        "--mode",
        choices=["dry-run", "write", "check"],
        default="dry-run",
    )
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    try:
        changed, outcome = apply(root, write=args.mode == "write")
        print(f"{root}: {outcome}")
        return 1 if changed and args.mode == "check" else 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
