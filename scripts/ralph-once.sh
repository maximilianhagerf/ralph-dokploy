#!/usr/bin/env bash
# ralph-once.sh — single Ralph iteration using GitHub Issues as task source
# Usage: ./scripts/ralph-once.sh <prd-issue-number>
set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
PRD_ISSUE="${1:-}"

if [ -z "$PRD_ISSUE" ]; then
	echo "Usage: $0 <prd-issue-number>"
	exit 1
fi

# ─── main ───────────────────────────────────────────────────────────────────

# Find the next open task issue (lowest number, excluding the PRD)
NEXT_ISSUE="$(gh issue list \
	--repo "$REPO" \
	--state open \
	--json number,title \
	--jq "[.[] | select(.number != $PRD_ISSUE)] | sort_by(.number) | first")"

if [ -z "$NEXT_ISSUE" ] || [ "$NEXT_ISSUE" = "null" ]; then
	echo "<promise>COMPLETE</promise>"
	exit 0
fi

ISSUE_NUMBER="$(echo "$NEXT_ISSUE" | jq -r '.number')"
ISSUE_TITLE="$(echo "$NEXT_ISSUE" | jq -r '.title')"
ISSUE_BODY="$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json body -q '.body')"

echo "→ Working on issue #$ISSUE_NUMBER: $ISSUE_TITLE"

PROMPT="$(
	cat <<PROMPT
You are working on the codebase described in CLAUDE.md. Implement the following GitHub issue fully.

## Issue #${ISSUE_NUMBER}: ${ISSUE_TITLE}

${ISSUE_BODY}

## Instructions

1. Read CLAUDE.md before making any changes.
2. Implement the issue fully, following all project conventions and using the /caveman skill.
3. As you complete each acceptance criterion, update the issue body to check it off:
   gh issue edit ${ISSUE_NUMBER} --repo ${REPO} --body "<updated body with - [x] for completed items>"
4. Run the project's lint and type check commands (see CLAUDE.md) before committing.
5. Commit with a conventional commit message but with the /caveman-commit skill.
6. When ALL acceptance criteria are checked off, close the issue:
   gh issue close ${ISSUE_NUMBER} --repo ${REPO}
7. If the issue is already done or not applicable, close it with a comment.
8. Write documentation for any new public functions, components, or modules you create.

## Delegation

You can delegate self-contained sub-tasks to a sub-agent by running this via Bash:
  claude --permission-mode bypassPermissions -p "<sub-task prompt>"

Use this for focused, parallelisable work: generating a component, writing a schema, drafting a test file, etc. Delegate only when the sub-task is fully self-contained and its output can be reviewed before use. Do not delegate the entire issue.

ONLY IMPLEMENT THIS ONE ISSUE. Do not start on any other issues.
PROMPT
)"

CLAUDE_STDERR_FILE="$(mktemp)"
CLAUDE_EXIT=0
claude --model "${ANTHROPIC_MODEL:-claude-sonnet-4-6}" --permission-mode bypassPermissions -p "$PROMPT" \
    2>"$CLAUDE_STDERR_FILE" || CLAUDE_EXIT=$?

CLAUDE_STDERR="$(cat "$CLAUDE_STDERR_FILE")"
rm -f "$CLAUDE_STDERR_FILE"

if [ "$CLAUDE_EXIT" -ne 0 ]; then
    if echo "$CLAUDE_STDERR" | grep -qiE "authentication|invalid api key|401|unauthorized|credentials|login required|auth"; then
        if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${RALPH_ALLOWED_USERS:-}" ]; then
            ALERT="Ralph auth failure on issue #${ISSUE_NUMBER}: ${ISSUE_TITLE}

Error:
$(echo "$CLAUDE_STDERR" | head -20)

Fix: re-inject ANTHROPIC_API_KEY or refresh CLAUDE_CREDENTIALS_B64 in Dokploy."
            IFS=',' read -ra USERS <<< "$RALPH_ALLOWED_USERS"
            for USER_ID in "${USERS[@]}"; do
                curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
                    --data-urlencode "chat_id=${USER_ID}" \
                    --data-urlencode "text=${ALERT}" > /dev/null
            done
        fi
    fi
    echo "$CLAUDE_STDERR" >&2
    exit "$CLAUDE_EXIT"
fi
