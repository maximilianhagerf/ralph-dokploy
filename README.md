# Ralph

Ralph is a self-hosted Telegram bot that autonomously implements GitHub issues using Claude Code. You send it a PRD issue number from Telegram; it clones the repo, iterates through child issues with `ralph.sh` → `ralph-once.sh` → `claude`, commits the work, and opens a pull request — all unattended.

## Prerequisites

- A running [Dokploy](https://dokploy.com) instance with a public HTTPS domain
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- GitHub Personal Access Token (PAT) with `repo` scope
- Anthropic API key (used by the `claude` CLI inside the container)
- Your Telegram user ID (see [docs/telegram-setup.md](docs/telegram-setup.md))

## Quick start

1. **Create a Telegram bot** — follow [docs/telegram-setup.md](docs/telegram-setup.md) to get a token and your user ID.
2. **Deploy to Dokploy** — follow [docs/dokploy-deploy.md](docs/dokploy-deploy.md) to build the container and set env vars.
3. **Register the webhook** — run the `curl` command in the deploy guide to point Telegram at your domain.
4. **Send `/status`** in Telegram — bot replies with `State: IDLE` when ready.
5. **Send `/start`** — pick a repo, pick a PRD issue, enter branches, confirm.

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/architecture.md](docs/architecture.md) | Module map, data-flow diagram, RALPH: protocol, state machine |
| [docs/dokploy-deploy.md](docs/dokploy-deploy.md) | End-to-end Dokploy deploy and webhook registration |
| [docs/telegram-setup.md](docs/telegram-setup.md) | BotFather setup, user ID, env var formats |

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Pick a repo and issue from inline menus, then launch a job |
| `/stop` | Graceful stop — waits for the current issue to finish before halting |
| `/force_stop` | Immediately kill the running job (SIGTERM → SIGKILL) |
| `/status` | Show current job state and the issue being worked on |
| `/help` | Show the command list |
