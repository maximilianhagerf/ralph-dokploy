# Anthropic API Key Setup

Ralph uses the `claude` CLI (Claude Code) inside `ralph-once.sh` to implement GitHub issues. The CLI requires an Anthropic API key at runtime.

## Getting a key

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in.
2. Open **API Keys** and click **Create Key**.
3. Copy the key — it starts with `sk-ant-`.

## Local / docker-compose

Add to your `.env` file (copy `.env.example` if you haven't already):

```env
ANTHROPIC_API_KEY=sk-ant-your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6   # optional; this is the default
```

`docker-compose.yml` loads `.env` via `env_file: .env` and passes all variables into the container automatically.

## Dokploy deployment

In the app's **Environment** tab, add:

| Variable | Example value | Notes |
|----------|---------------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-…` | Required |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Optional; defaults to `claude-sonnet-4-6` |

After saving, click **Redeploy**.

## Model selection

`ralph-once.sh` passes `--model "$ANTHROPIC_MODEL"` to the `claude` CLI, defaulting to `claude-sonnet-4-6`. To use a more capable model for harder problems, set:

```env
ANTHROPIC_MODEL=claude-opus-4-7
```

Available models (as of 2026-04):

| Model ID | Notes |
|----------|-------|
| `claude-sonnet-4-6` | Default — good balance of speed and capability |
| `claude-opus-4-7` | Most capable; higher cost per issue |
| `claude-haiku-4-5-20251001` | Fastest; suitable only for simple issues |

## Verifying auth

After deploy, trigger a job. If the key is missing or invalid, the container logs will show:

```
Error: ANTHROPIC_API_KEY is not set
```

or

```
Error: authentication failed
```

Fix: add/correct the key in your `.env` or Dokploy env vars and redeploy.
