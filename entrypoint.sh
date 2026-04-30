#!/usr/bin/env bash
set -euo pipefail

if [ -n "${CLAUDE_CREDENTIALS_B64:-}" ]; then
    mkdir -p /root/.claude
    echo "$CLAUDE_CREDENTIALS_B64" | base64 -d > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
fi

exec "$@"
