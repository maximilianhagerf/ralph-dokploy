"""bot.py — Telegram webhook handler for Ralph.

Public surface: build_application(token) -> Application, main().
All job execution delegated to job_manager; no subprocesses spawned here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import job_manager

logger = logging.getLogger(__name__)

# Conversation states
(
    SELECTING_REPO,
    SELECTING_ISSUE,
    ENTERING_BASE_BRANCH,
    ENTERING_NEW_BRANCH,
    CONFIRMING,
) = range(5)

# Most-recently-used repo (module-level, persisted across conversations)
_last_repo: Optional[str] = None


# ── helpers ────────────────────────────────────────────────────────────────


def _allowed_users() -> set[int]:
    raw = os.environ.get("RALPH_ALLOWED_USERS", "")
    return {int(u.strip()) for u in raw.split(",") if u.strip().isdigit()}


def _repos() -> list[str]:
    raw = os.environ.get("RALPH_REPOS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


def _is_allowed(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    allowed = _allowed_users()
    return bool(allowed) and user.id in allowed


def _repo_slug(repo_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL or bare slug."""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", repo_url)
    return m.group(1) if m else repo_url


async def _fetch_issues(repo_url: str) -> list[dict]:
    """Return open issues from the GitHub REST API for *repo_url*."""
    slug = _repo_slug(repo_url)
    url = f"https://api.github.com/repos/{slug}/issues"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            url, params={"state": "open", "per_page": 50}, headers=headers
        )
        resp.raise_for_status()
        return resp.json()


def _status_text(s: Dict[str, Any]) -> str:
    state = s.get("state", "UNKNOWN")
    issue = s.get("issue")
    if issue:
        return f"State: {state}\nIssue: #{issue['number']} {issue['title']}"
    return f"State: {state}"


# ── conversation handlers ──────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: show repo picker, or report status if job is running."""
    if not _is_allowed(update):
        return ConversationHandler.END

    s = job_manager.status()
    if s["state"] != "IDLE":
        await update.message.reply_text(
            f"Job already running.\n{_status_text(s)}"
        )
        return ConversationHandler.END

    global _last_repo
    repos = _repos()
    if not repos:
        await update.message.reply_text("No repos configured. Set RALPH_REPOS.")
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(f"★ {r}" if r == _last_repo else r, callback_data=f"repo:{r}")]
        for r in repos
    ]
    await update.message.reply_text(
        "Select a repository:", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECTING_REPO


async def repo_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not _is_allowed(update):
        return ConversationHandler.END

    repo = query.data[len("repo:"):]
    context.user_data["repo"] = repo

    await query.edit_message_text(f"Fetching issues for {repo}…")
    try:
        issues = await _fetch_issues(repo)
    except Exception as exc:
        await query.edit_message_text(f"Failed to fetch issues: {exc}")
        return ConversationHandler.END

    if not issues:
        await query.edit_message_text("No open issues found.")
        return ConversationHandler.END

    context.user_data["issues"] = {str(i["number"]): i["title"] for i in issues}
    buttons = [
        [
            InlineKeyboardButton(
                f"#{i['number']} {i['title'][:40]}",
                callback_data=f"issue:{i['number']}",
            )
        ]
        for i in issues[:20]
    ]
    await query.edit_message_text(
        "Select a PRD issue:", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECTING_ISSUE


async def issue_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not _is_allowed(update):
        return ConversationHandler.END

    issue_number = query.data[len("issue:"):]
    context.user_data["prd_issue"] = issue_number
    title = context.user_data.get("issues", {}).get(issue_number, "")
    context.user_data["prd_title"] = title

    await query.edit_message_text(
        f"Selected issue #{issue_number}: {title}\n\nEnter base branch name:"
    )
    return ENTERING_BASE_BRANCH


async def base_branch_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_allowed(update):
        return ConversationHandler.END
    context.user_data["base_branch"] = update.message.text.strip()
    await update.message.reply_text("Enter new branch name:")
    return ENTERING_NEW_BRANCH


async def new_branch_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_allowed(update):
        return ConversationHandler.END
    context.user_data["new_branch"] = update.message.text.strip()
    d = context.user_data
    text = (
        f"Confirm job:\n"
        f"  Repo: {d.get('repo')}\n"
        f"  Issue: #{d.get('prd_issue')} {d.get('prd_title', '')}\n"
        f"  Base branch: {d.get('base_branch')}\n"
        f"  New branch: {d.get('new_branch')}\n"
    )
    buttons = [
        [
            InlineKeyboardButton("Confirm", callback_data="confirm"),
            InlineKeyboardButton("Cancel", callback_data="cancel"),
        ]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRMING


async def confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not _is_allowed(update):
        return ConversationHandler.END

    global _last_repo
    d = context.user_data
    repo = d.get("repo", "")
    prd_issue = d.get("prd_issue", "")
    base_branch = d.get("base_branch", "")
    new_branch = d.get("new_branch", "")
    _last_repo = repo

    chat_id = update.effective_chat.id
    bot = context.bot
    loop = asyncio.get_event_loop()

    def on_event(event_type: str, payload: Dict[str, Any]) -> None:
        if event_type == "issue":
            text = f"▶ Working on #{payload['number']}: {payload['title']}"
        elif event_type == "complete":
            pr_url = payload.get("pr_url", "")
            text = f"✅ Done. PR: {pr_url}"
        elif event_type == "error":
            text = f"❌ Error: {payload['message']}"
        else:
            return
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=text),
            loop,
        )

    err = job_manager.start(repo, prd_issue, base_branch, new_branch, on_event)
    if err:
        await query.edit_message_text(f"Failed to start: {err}")
    else:
        await query.edit_message_text("Job started.")
    return ConversationHandler.END


async def cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


# ── standalone commands ────────────────────────────────────────────────────


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    job_manager.stop()
    await update.message.reply_text(_status_text(job_manager.status()))


async def force_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    job_manager.force_stop()
    await update.message.reply_text("Stopped.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(_status_text(job_manager.status()))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "/start — pick repo and issue, launch job\n"
        "/stop — graceful stop after current issue\n"
        "/force-stop — kill job immediately\n"
        "/status — show current job state\n"
        "/help — show this message\n"
    )


# ── application factory ────────────────────────────────────────────────────


def build_application(token: str) -> Application:
    """Create and configure the PTB Application with all handlers registered."""
    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_REPO: [CallbackQueryHandler(repo_selected, pattern=r"^repo:")],
            SELECTING_ISSUE: [CallbackQueryHandler(issue_selected, pattern=r"^issue:")],
            ENTERING_BASE_BRANCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, base_branch_entered)
            ],
            ENTERING_NEW_BRANCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_branch_entered)
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirmed, pattern=r"^confirm$"),
                CallbackQueryHandler(cancelled, pattern=r"^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("force_stop", force_stop_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    webhook_url = os.environ["RALPH_WEBHOOK_URL"]
    app = build_application(token)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", "8443")),
        webhook_url=webhook_url,
        url_path="webhook",
    )


if __name__ == "__main__":
    main()
