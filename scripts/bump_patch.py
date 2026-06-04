#!/usr/bin/env python3
"""Bump patch version (0.0.1 -> 0.0.2). Used before routine revision commits."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from version_lib import bump_patch, read_version, write_version  # noqa: E402


def main() -> None:
    current = read_version()
    new = bump_patch(current)
    write_version(new)
    print(new)


if __name__ == "__main__":
    main()
