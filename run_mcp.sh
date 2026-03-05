#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_exe="$repo_root/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python_exe="python3"
elif command -v python >/dev/null 2>&1; then
  python_exe="python"
else
  echo "Python executable not found" >&2
  exit 1
fi

export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$python_exe" -m suitcode.mcp.server "$@"
