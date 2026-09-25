#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): format and auto-fix a Python file Claude just wrote.
# Reads the hook payload on stdin. Silent no-op for non-Python files or when ruff is absent.
set -euo pipefail

file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"
[[ -n "$file" && "$file" == *.py && -f "$file" ]] || exit 0

if python3 -m ruff --version >/dev/null 2>&1; then
  python3 -m ruff format --quiet "$file"
  python3 -m ruff check --fix --quiet "$file" || true
fi
