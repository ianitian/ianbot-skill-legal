#!/usr/bin/env bash
# Enable auto patch bump on every commit (optional; or use ./scripts/commit-revision.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x .githooks/pre-commit scripts/commit-revision.sh
git config core.hooksPath .githooks
echo "Git hooks enabled: patch version bumps on each commit (use --no-verify to skip)."
