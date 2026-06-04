"""Shared version read/write for VERSION, pyproject.toml, and ingest/api.py."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "pyproject.toml"
API_PY = ROOT / "ingest" / "api.py"
README = ROOT / "readme.md"
README_TITLE_RE = re.compile(r"^# ianbot-skill-legal(?: v[\d.]+)?\s*$", re.MULTILINE)


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def parse_version(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def format_version(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"


def bump_patch(version: str) -> str:
    major, minor, patch = parse_version(version)
    return format_version(major, minor, patch + 1)


def bump_minor(version: str) -> str:
    major, minor, _patch = parse_version(version)
    return format_version(major, minor + 1, 0)


def bump_major(version: str) -> str:
    major, _minor, _patch = parse_version(version)
    return format_version(major + 1, 0, 0)


def write_version(version: str) -> None:
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")

    pyproject = PYPROJECT.read_text(encoding="utf-8")
    pyproject = re.sub(
        r'^version = ".*"',
        f'version = "{version}"',
        pyproject,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(pyproject, encoding="utf-8")

    api_py = API_PY.read_text(encoding="utf-8")
    api_py = re.sub(
        r'version="[^"]+"',
        f'version="{version}"',
        api_py,
        count=1,
    )
    API_PY.write_text(api_py, encoding="utf-8")

    readme = README.read_text(encoding="utf-8")
    readme = README_TITLE_RE.sub(f"# ianbot-skill-legal v{version}", readme, count=1)
    README.write_text(readme, encoding="utf-8")
