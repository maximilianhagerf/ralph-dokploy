# GitHub Personal Access Token for Ralph

Ralph uses the `gh` CLI to list issues and open PRs. It authenticates via the `GITHUB_TOKEN` environment variable.

## Token type: Classic PAT

Use a **classic Personal Access Token**, not a fine-grained token. Fine-grained tokens have incomplete `gh` CLI support and cannot be used as a drop-in `GITHUB_TOKEN` in all versions.

Classic PATs start with `ghp_`.

## Required scope

| Scope | Why |
|-------|-----|
| `repo` | Read issues, create branches, open PRs on private and public repos |

`read:org` is optional — only needed if your repos belong to an organisation and you want org-level metadata.

## Steps to generate

1. Open **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**.
   Direct link: `https://github.com/settings/tokens`
2. Click **Generate new token (classic)**.
3. Set a descriptive **Note** (e.g. `ralph-bot`).
4. Set **Expiration** — 90 days is a reasonable default; calendar-remind yourself to rotate.
5. Under **Select scopes**, tick **`repo`** (top-level checkbox — selects all sub-scopes).
6. Click **Generate token**.
7. **Copy the token immediately** — GitHub shows it only once.

## Where to put it

Set `GITHUB_TOKEN=ghp_…` in your Dokploy app's **Environment** tab (see [dokploy-deploy.md](dokploy-deploy.md)).

> **Security:** Store the token only in Dokploy's env var store. Never commit it to the repo or paste it into logs.

## Rotating the token

When the token expires, generate a new one (same scopes) and update `GITHUB_TOKEN` in Dokploy, then redeploy.
