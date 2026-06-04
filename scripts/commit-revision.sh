#!/usr/bin/env bash
# Bump patch version, stage version files, then commit.
# Usage: ./scripts/commit-revision.sh -m "fix(v0.0.2): your message"
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/bump_patch.py
VERSION=$(cat VERSION)
git add VERSION pyproject.toml ingest/api.py

echo "Staged version bump to v${VERSION}"
git commit "$@"
