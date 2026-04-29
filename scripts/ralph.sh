#!/usr/bin/env bash
# ralph.sh — AFK Ralph loop using GitHub Issues as task source
# Usage: ./scripts/ralph.sh <prd-issue-number> [iterations]
# Example: ./scripts/ralph.sh 1 10
set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
PRD_ISSUE="${1:-}"
MAX_ITERATIONS="${2:-20}"

if [ -z "$PRD_ISSUE" ]; then
  echo "Usage: $0 <prd-issue-number> [max-iterations]"
  exit 1
fi

echo "Ralph loop starting — PRD: issue #$PRD_ISSUE, max iterations: $MAX_ITERATIONS"
echo "Repository: $REPO"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  echo "━━━ Iteration $i / $MAX_ITERATIONS ━━━"

  # Check remaining open issues before starting
  OPEN_COUNT="$(gh issue list \
    --repo "$REPO" \
    --state open \
    --json number \
    --jq "[.[] | select(.number != $PRD_ISSUE)] | length")"

  if [ "$OPEN_COUNT" -eq 0 ]; then
    echo "All issues closed. PRD complete after $((i-1)) iterations."
    echo "<promise>COMPLETE</promise>"
    exit 0
  fi

  echo "$OPEN_COUNT issue(s) remaining."

  result="$("$SCRIPT_DIR/ralph-once.sh" "$PRD_ISSUE" 2>&1)"
  echo "$result"

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "PRD complete after $i iterations."
    exit 0
  fi

  echo ""
done

echo "Reached max iterations ($MAX_ITERATIONS). Check remaining issues:"
gh issue list --repo "$REPO" --state open --json number,title \
  --jq '.[] | select(.number != '"$PRD_ISSUE"') | "#\(.number) \(.title)"'
