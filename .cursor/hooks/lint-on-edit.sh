#!/bin/bash
# Hook: Run linter after file edits
# Registered in .cursor/hooks.json under afterFileEdit
#
# Cursor passes event data as JSON on stdin. The JSON contains a "path" field
# with the absolute path of the file that was edited.

input=$(cat)
FILE_PATH=$(echo "$input" | jq -r '.path // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

EXTENSION="${FILE_PATH##*.}"

case "$EXTENSION" in
  py)
    ruff check "$FILE_PATH" --fix --quiet 2>/dev/null
    ;;
  ts|tsx|js|jsx)
    npx eslint "$FILE_PATH" --fix --quiet 2>/dev/null
    ;;
  *)
    # No linter configured for this file type
    ;;
esac
