# Architecture

## Module map

**`bot.py`** — Telegram webhook handler. Owns the HTTP server (python-telegram-bot webhooks), the five-state `ConversationHandler` for `/start`, and the four standalone command handlers (`/stop`, `/force_stop`, `/status`, `/help`). Validates every incoming update against `RALPH_ALLOWED_USERS`. Delegates all job execution to `job_manager`; never spawns subprocesses directly. Sends Telegram messages via thread-safe `asyncio.run_coroutine_threadsafe` callbacks supplied to the job manager.

**`job_manager.py`** — Subprocess lifecycle and state machine. Exposes a module-level singleton with four functions: `start()`, `stop()`, `force_stop()`, `status()`. `start()` clones the target repo to `/workspace/<uuid>`, spawns `ralph.sh` with `Popen`, and runs a reader thread that parses `RALPH:` protocol lines from stdout and fires `on_event` callbacks. `stop()` sets a flag checked between `readline()` calls; `force_stop()` sends SIGTERM to the whole process group, escalating to SIGKILL after 5 s. Cleanup (`shutil.rmtree`) runs in `_finish()` regardless of exit code.

**`scripts/ralph.sh`** — Outer iteration loop. Takes `<prd-issue-number> [max-iterations] [base-branch] [new-branch]`. Checks out the working branch, then loops up to `max-iterations` times: picks the lowest-numbered open issue (excluding the PRD), emits `RALPH:ISSUE:<n>:<title>`, calls `ralph-once.sh`, and breaks on `<promise>COMPLETE</promise>`. On success emits `RALPH:COMPLETE` and opens a PR via `gh pr create` listing all newly-closed issues. On unexpected exit the ERR/EXIT traps emit `RALPH:ERROR:<cmd> exited <rc>`.

**`scripts/ralph-once.sh`** — Single-issue executor. Finds the same lowest-numbered open issue, fetches its body, builds a structured prompt (including CLAUDE.md instructions), and invokes `claude --permission-mode bypassPermissions -p "$PROMPT"`. If no open issues remain, prints `<promise>COMPLETE</promise>` and exits 0. The output is captured by `ralph.sh` and echoed to stdout so `job_manager.py` can read it.

## Data flow

```
Telegram user
     │  HTTPS POST /webhook
     ▼
 bot.py (PTB webhook server)
     │  job_manager.start(repo, issue, base, branch, on_event)
     ▼
 job_manager.py
     │  git clone <repo> /workspace/<uuid>
     │  Popen(ralph.sh <prd_issue> 20 <base> <new>)
     │  reader thread → readline()
     ▼
 scripts/ralph.sh  (loop, max 20 iterations)
     │  gh issue list → pick next issue
     │  emit RALPH:ISSUE:<n>:<title>  ────────────────────────┐
     │  capture ralph-once.sh output                          │
     │  emit RALPH:COMPLETE / RALPH:ERROR  ───────────────────┤
     ▼                                                        │
 scripts/ralph-once.sh                                        │
     │  gh issue view → body                                  │
     │  claude --permission-mode bypassPermissions            │
     ▼                                                        │
 claude CLI (Claude Code)                                     │
     │  edits files, git commit, closes issue                 │
     ▼                                                        │
 GitHub (commits, issue close, PR)                            │
                                                              │
 job_manager reader thread ◄───────────────────────────────-─┘
     │  parse RALPH: lines → on_event callback
     ▼
 bot.py → bot.send_message(chat_id, text)
     │
     ▼
Telegram user
```

## RALPH: protocol

Lines written to stdout by `ralph.sh` and consumed by `job_manager.py`:

| Line format | Meaning |
|-------------|---------|
| `RALPH:ISSUE:<number>:<title>` | Starting work on issue `<number>`. `job_manager` updates `current_issue` and fires the `"issue"` event. |
| `RALPH:COMPLETE` | All issues closed; PR created. `job_manager` fires the `"complete"` event and reads ahead up to 5 lines to capture the `gh pr create` URL. |
| `RALPH:ERROR:<message>` | Unexpected script exit. `job_manager` fires the `"error"` event with `message`. |

## Job state diagram

```
         job_manager.start()
              │
         ┌────▼────┐
   ┌────►│  IDLE   │◄────────────────────────────────┐
   │    └────┬────┘                                   │
   │         │ start() called                         │
   │    ┌────▼───────┐                                │
   │    │  RUNNING   │                                │
   │    └──┬──┬──────┘                                │
   │       │  │ stop()                                │
   │       │  └──►┌──────────┐                        │
   │       │      │ STOPPING │── reader loop ends ───►│
   │       │      └──────────┘  (graceful, exit 0)   │
   │       │                                          │
   │       │ force_stop()                             │
   │       └──►┌─────────┐                            │
   │           │ STOPPED │                            │
   │           └─────────┘                            │
   │                                                  │
   └── exit 0 (no stop requested) ────────────────────┘
```

Transitions:
- `IDLE → RUNNING`: `start()` succeeds
- `RUNNING → STOPPING`: `stop()` called; job finishes current issue then terminates
- `STOPPING → IDLE`: reader loop exits cleanly
- `RUNNING → STOPPED`: `force_stop()` or non-zero exit code
- `STOPPED → IDLE`: next `start()` call (state resets at entry)
- `RUNNING → IDLE`: script exits 0 with no stop requested

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `RALPH_WEBHOOK_URL` | Yes | Public HTTPS URL Telegram POSTs to (must end with `/webhook`) |
| `PORT` | No (default `8443`) | Port the bot listens on inside the container |
| `RALPH_ALLOWED_USERS` | Yes | Comma-separated Telegram user IDs allowed to use the bot |
| `RALPH_REPOS` | Yes | Comma-separated GitHub repo URLs the bot may operate on |
| `GITHUB_TOKEN` | Yes | PAT with `repo` scope; used for GitHub API calls and `gh` CLI auth |

## Future: job queue

`job_manager.py` intentionally uses a single job slot (`_manager = JobManager()`). The public interface (`start`, `stop`, `force_stop`, `status`) is stable. To add a queue: replace `_manager` with a queue-aware implementation that accepts multiple `start()` calls and serialises them. `bot.py` and `ralph.sh` require no changes.
