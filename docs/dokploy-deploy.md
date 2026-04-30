# Deploying Ralph on Dokploy

## Prerequisites

- Dokploy instance with a public domain and wildcard SSL (or per-app SSL)
- GitHub repo URL for this project (or a fork)
- Values for all six env vars (see below)

## 1. Create the app

1. Open your Dokploy dashboard and click **Create Application**.
2. Give it a name (e.g. `ralph-bot`).
3. Under **Source**, choose **Git** and paste your repo URL. Set branch to `main` (or `develop`).
4. Under **Build**, select **Dockerfile**. Leave the path as `Dockerfile` (it is in the repo root).
5. Click **Save**.

## 2. Set environment variables

In the app's **Environment** tab, add all six variables:

| Variable | Example value | Notes |
|----------|---------------|-------|
| `TELEGRAM_BOT_TOKEN` | `7123456789:AAF…` | From @BotFather |
| `RALPH_WEBHOOK_URL` | `https://ralph.example.com/webhook` | Must be HTTPS; include `/webhook` |
| `PORT` | `8443` | Port inside the container; must match the exposed port below |
| `RALPH_ALLOWED_USERS` | `123456789` | Your Telegram user ID; comma-separate multiple IDs |
| `RALPH_REPOS` | `https://github.com/owner/repo` | Comma-separate multiple repos |
| `GITHUB_TOKEN` | `ghp_…` | PAT with `repo` scope |

You also need to inject your Anthropic API key so `claude` can authenticate:

| Variable | Example value |
|----------|---------------|
| `ANTHROPIC_API_KEY` | `sk-ant-…` |

## 3. Configure the domain and SSL

1. In the **Domains** tab, add your domain (e.g. `ralph.example.com`).
2. Enable **HTTPS / Let's Encrypt**. Dokploy provisions the certificate automatically.
3. Set the **container port** to the value of `PORT` (default `8443`).

## 4. Build and deploy

Click **Deploy**. Dokploy builds the Docker image and starts the container. Watch the **Logs** tab — you should see:

```
INFO:httpx:HTTP Request: POST https://api.telegram.org/bot.../setWebhook ...
INFO:telegram.ext.Application:Application started
```

If the image build fails, check that the repo is accessible and the Dockerfile path is correct.

## 5. Register the Telegram webhook

After the container is running, tell Telegram where to send updates. Replace `<TOKEN>` and `<DOMAIN>`:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<DOMAIN>/webhook"}'
```

Expected response:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

> **Note:** `python-telegram-bot` calls `setWebhook` automatically on startup via `run_webhook()`. The manual `curl` is a fallback if the automatic call fails (e.g. due to a network race at startup).

## 6. Verify the service is running

**Check Dokploy logs** — in the app's **Logs** tab, look for `Application started` and no Python tracebacks.

**Check via Telegram** — send `/status` to your bot. It should reply:

```
State: IDLE
```

If it does not reply, the webhook is not registered or the bot token is wrong.

## Troubleshooting

### Webhook not registered

```
{"ok":false,"error_code":401,"description":"Unauthorized"}
```

`TELEGRAM_BOT_TOKEN` is wrong or missing. Double-check in Dokploy env vars and redeploy.

```
{"ok":false,"error_code":400,"description":"Bad Request: bad webhook: HTTPS URL must be provided for webhook"}
```

`RALPH_WEBHOOK_URL` does not start with `https://`. Fix the value and re-run the `curl` command.

### `claude` auth failure

The container logs will show something like:

```
Error: ANTHROPIC_API_KEY is not set
```

Add `ANTHROPIC_API_KEY` to the Dokploy env vars and redeploy.

### `gh` auth failure

`ralph.sh` uses the `gh` CLI, which reads `GITHUB_TOKEN` from the environment. If it is missing you will see:

```
RALPH:ERROR:gh issue list exited 1
```

Set `GITHUB_TOKEN` in Dokploy env vars and redeploy.

### Job starts but no PR is created

Check that `RALPH_REPOS` matches the exact URL of the repo you selected in the bot, and that `GITHUB_TOKEN` has `repo` scope (not just `read:repo`).
