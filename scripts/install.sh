#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
exec uv run --frozen python scripts/setup.py install
