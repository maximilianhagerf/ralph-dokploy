"""Integration tests for bot.py — handler behaviour and allowlist enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

import bot

ALLOWED = 42
DISALLOWED = 99


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("RALPH_ALLOWED_USERS", str(ALLOWED))
    monkeypatch.setenv("RALPH_REPOS", "https://github.com/owner/repo.git")


def _update(user_id: int, text: str) -> Update:
    user = User(id=user_id, first_name="T", is_bot=False)
    chat = Chat(id=user_id, type="private")
    msg = Message(
        message_id=1,
        date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=1, message=msg)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.bot = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_disallowed_user_no_reply():
    update = _update(DISALLOWED, "/start")
    ctx = _ctx()
    with patch("telegram.Message.reply_text", new_callable=AsyncMock) as mock_reply:
        await bot.start(update, ctx)
    mock_reply.assert_not_called()


@pytest.mark.asyncio
async def test_start_while_running_returns_status():
    update = _update(ALLOWED, "/start")
    ctx = _ctx()
    with (
        patch("bot.job_manager") as mock_jm,
        patch("telegram.Message.reply_text", new_callable=AsyncMock) as mock_reply,
    ):
        mock_jm.status.return_value = {"state": "RUNNING", "issue": None}
        await bot.start(update, ctx)
    mock_reply.assert_called_once()
    assert "RUNNING" in mock_reply.call_args.args[0]


@pytest.mark.asyncio
async def test_help_contains_all_commands():
    update = _update(ALLOWED, "/help")
    ctx = _ctx()
    with patch("telegram.Message.reply_text", new_callable=AsyncMock) as mock_reply:
        await bot.help_command(update, ctx)
    mock_reply.assert_called_once()
    text = mock_reply.call_args.args[0]
    for cmd in ("/start", "/stop", "/force-stop", "/status", "/help"):
        assert cmd in text


@pytest.mark.asyncio
async def test_status_while_idle():
    update = _update(ALLOWED, "/status")
    ctx = _ctx()
    with (
        patch("bot.job_manager") as mock_jm,
        patch("telegram.Message.reply_text", new_callable=AsyncMock) as mock_reply,
    ):
        mock_jm.status.return_value = {"state": "IDLE", "issue": None}
        await bot.status_command(update, ctx)
    mock_reply.assert_called_once()
    assert "IDLE" in mock_reply.call_args.args[0]
