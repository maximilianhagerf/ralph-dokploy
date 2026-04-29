#!/usr/bin/env bash
# ralph-start.sh — interactive launcher for the Ralph loop
# Starts Docker (PocketBase), picks a PRD issue, and runs the loop.
# Usage: ./scripts/ralph-start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

echo "╔══════════════════════════════════════╗"
echo "║           Ralph Loop — CV            ║"
echo "╚══════════════════════════════════════╝"
echo ""

# # 1. Start Docker / PocketBase
# echo "▶ Starting PocketBase (docker compose)..."
# cd "$(dirname "$SCRIPT_DIR")"
# if docker compose up -d 2>&1 | grep -q "Running\|Started\|healthy\|up-to-date"; then
#   echo "  PocketBase already running or just started."
# else
#   docker compose up -d
#   echo "  Waiting for PocketBase to be healthy..."
#   for i in {1..12}; do
#     if curl -sf http://localhost:8090/api/health > /dev/null 2>&1; then
#       echo "  PocketBase is healthy."
#       break
#     fi
#     sleep 5
#     if [ "$i" -eq 12 ]; then
#       echo "  ✗ PocketBase did not become healthy in time. Check docker logs."
#       exit 1
#     fi
#   done
# fi
# echo ""

# 2. List open issues and let user pick a PRD
echo "▶ Open GitHub Issues:"
echo ""
gh issue list --repo "$REPO" --state open --json number,title \
	--jq '.[] | "  #\(.number)  \(.title)"'
echo ""

read -rp "Enter the PRD issue number: " PRD_ISSUE

# Validate input
if ! [[ "$PRD_ISSUE" =~ ^[0-9]+$ ]]; then
	echo "✗ Invalid issue number."
	exit 1
fi

PRD_TITLE="$(gh issue view "$PRD_ISSUE" --repo "$REPO" --json title -q '.title')"
echo ""
echo "  PRD: #$PRD_ISSUE — $PRD_TITLE"
echo ""

# 3. Ask for iteration limit
read -rp "Max iterations [20]: " MAX_ITER
MAX_ITER="${MAX_ITER:-20}"

# 4. Ask for mode
echo ""
echo "  Modes:"
echo "    1) Human-in-the-loop  — run one issue at a time, you confirm each"
echo "    2) AFK                — run all issues unattended"
echo ""
read -rp "Mode [1]: " MODE
MODE="${MODE:-1}"

echo ""

if [ "$MODE" = "1" ]; then
	echo "▶ Human-in-the-loop mode. Running ralph-once.sh. Press Ctrl-C to stop."
	echo ""
	while true; do
		OPEN_COUNT="$(gh issue list \
			--repo "$REPO" \
			--state open \
			--json number \
			--jq "[.[] | select(.number != $PRD_ISSUE)] | length")"

		if [ "$OPEN_COUNT" -eq 0 ]; then
			echo "All issues closed. Done."
			break
		fi

		echo "$OPEN_COUNT issue(s) remaining."
		"$SCRIPT_DIR/ralph-once.sh" "$PRD_ISSUE"

		echo ""
		read -rp "Run next issue? [Y/n]: " CONT
		CONT="${CONT:-Y}"
		if [[ "$CONT" =~ ^[Nn] ]]; then
			echo "Stopped."
			break
		fi
	done
else
	echo "▶ AFK mode. Running up to $MAX_ITER iterations."
	echo ""
	"$SCRIPT_DIR/ralph.sh" "$PRD_ISSUE" "$MAX_ITER"
fi
