#!/usr/bin/env bash
# ralph.sh — AFK Ralph loop using GitHub Issues as task source
# Usage: ./scripts/ralph.sh <prd-issue-number> [iterations] [base-branch] [new-branch]
# Example: ./scripts/ralph.sh 1 10 main feature/my-work
set -euo pipefail

REPO="${RALPH_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
PRD_ISSUE="${1:-}"
MAX_ITERATIONS="${2:-20}"
BASE_BRANCH="${3:-}"
NEW_BRANCH="${4:-}"

if [ -z "$PRD_ISSUE" ]; then
  echo "Usage: $0 <prd-issue-number> [max-iterations] [base-branch] [new-branch]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Track the command that caused an error (for RALPH:ERROR message)
FAILED_CMD=""
trap 'FAILED_CMD=$BASH_COMMAND' ERR

# Emit RALPH:ERROR on unexpected exit; cleared by setting RALPH_DONE=true
RALPH_DONE=false
trap '
  RC=$?
  if [ "$RALPH_DONE" != "true" ] && [ "$RC" -ne 0 ]; then
    echo "RALPH:ERROR:${FAILED_CMD:-unknown command} exited $RC"
  fi
' EXIT

echo "Ralph loop starting — PRD: issue #$PRD_ISSUE, max iterations: $MAX_ITERATIONS"
echo "Repository: $REPO"
echo ""

# Branch setup: checkout base then create new branch
if [ -n "$NEW_BRANCH" ]; then
  if [ -n "$BASE_BRANCH" ]; then
    git checkout "$BASE_BRANCH"
  fi
  git checkout -b "$NEW_BRANCH"
fi

# Snapshot closed issue IDs before loop so PR body can list what was closed
BEFORE_CLOSED_IDS="[]"
if [ -n "$BASE_BRANCH" ]; then
  BEFORE_CLOSED_IDS="$(gh issue list \
    --repo "$REPO" \
    --state closed \
    --limit 1000 \
    --json number \
    --jq '[.[].number]')"
fi

LOOP_SUCCESS=false

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  echo "━━━ Iteration $i / $MAX_ITERATIONS ━━━"

  NEXT_ISSUE_JSON="$(gh issue list \
    --repo "$REPO" \
    --state open \
    --json number,title \
    --jq "[.[] | select(.number != $PRD_ISSUE)] | sort_by(.number) | first")"

  if [ -z "$NEXT_ISSUE_JSON" ] || [ "$NEXT_ISSUE_JSON" = "null" ]; then
    echo "All issues closed. PRD complete after $((i-1)) iterations."
    LOOP_SUCCESS=true
    break
  fi

  NEXT_NUM="$(echo "$NEXT_ISSUE_JSON" | jq -r '.number')"
  NEXT_TITLE="$(echo "$NEXT_ISSUE_JSON" | jq -r '.title')"
  OPEN_COUNT="$(gh issue list \
    --repo "$REPO" \
    --state open \
    --json number \
    --jq "[.[] | select(.number != $PRD_ISSUE)] | length")"

  echo "RALPH:ISSUE:${NEXT_NUM}:${NEXT_TITLE}"
  echo "$OPEN_COUNT issue(s) remaining."

  result="$("$SCRIPT_DIR/ralph-once.sh" "$PRD_ISSUE" 2>&1)"
  echo "$result"

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "PRD complete after $i iterations."
    LOOP_SUCCESS=true
    break
  fi

  echo ""
done

RALPH_DONE=true

if [ "$LOOP_SUCCESS" = "true" ]; then
  echo "RALPH:COMPLETE"

  if [ -n "$BASE_BRANCH" ]; then
    PRD_TITLE="$(gh issue view "$PRD_ISSUE" --repo "$REPO" --json title -q '.title')"

    AFTER_CLOSED_IDS="$(gh issue list \
      --repo "$REPO" \
      --state closed \
      --limit 1000 \
      --json number \
      --jq '[.[].number]')"

    NEW_CLOSED_IDS="$(jq -n \
      --argjson before "$BEFORE_CLOSED_IDS" \
      --argjson after "$AFTER_CLOSED_IDS" \
      '$after - $before | sort')"

    PR_BODY="Closes #${PRD_ISSUE}"$'\n\n'
    while IFS= read -r num; do
      ITITLE="$(gh issue view "$num" --repo "$REPO" --json title -q '.title')"
      PR_BODY+="- Closes #${num}: ${ITITLE}"$'\n'
    done < <(echo "$NEW_CLOSED_IDS" | jq -r '.[]')

    gh pr create \
      --base "$BASE_BRANCH" \
      --title "$PRD_TITLE" \
      --body "$PR_BODY"
  fi
else
  echo "Reached max iterations ($MAX_ITERATIONS). Check remaining issues:"
  gh issue list --repo "$REPO" --state open --json number,title \
    --jq '.[] | select(.number != '"$PRD_ISSUE"') | "#\(.number) \(.title)"'
fi
