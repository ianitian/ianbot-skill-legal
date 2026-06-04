#!/usr/bin/env python3
"""Bump minor version (0.1.0 -> 0.2.0). Run only when you intend a minor release."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from version_lib import bump_minor, read_version, write_version  # noqa: E402


def main() -> None:
    current = read_version()
    new = bump_minor(current)
    write_version(new)
    print(new)


if __name__ == "__main__":
    main()
