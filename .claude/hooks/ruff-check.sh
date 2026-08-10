#!/usr/bin/env bash
# PostToolUse hook: run `uv run ruff check` on any Python file Claude edits.
# Reports findings back to the user; never blocks the edit.
set -uo pipefail

# Hooks don't get a login shell, so uv may not be on PATH.
export PATH="$HOME/.local/bin:$PATH"

payload=$(cat)
file=$(printf '%s' "$payload" | jq -r '.tool_response.filePath // .tool_input.file_path // empty')

[[ "$file" == *.py ]] || exit 0
[[ -f "$file" ]] || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

output=$(uv run ruff check "$file" 2>&1)
status=$?

# Clean file, or ruff itself is unavailable — stay quiet either way.
[[ $status -eq 0 ]] && exit 0
command -v uv >/dev/null || exit 0

jq -n --arg out "$output" '{
  systemMessage: ("ruff check\n" + $out),
  suppressOutput: true
}'
