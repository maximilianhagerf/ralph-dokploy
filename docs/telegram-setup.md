# Telegram setup

## 1. Create a bot with BotFather

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. BotFather asks for a **name** (display name, e.g. `Ralph`) and a **username** (must end in `bot`, e.g. `my_ralph_bot`).
4. BotFather replies with your bot token:

   ```
   Use this token to access the HTTP API:
   7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

5. Copy this token — it is the value of `TELEGRAM_BOT_TOKEN`.

## 2. Set bot commands via BotFather

So Telegram shows autocomplete for Ralph's commands, register them with BotFather:

1. Send `/setcommands` to @BotFather.
2. Select your bot.
3. Paste this block exactly:

   ```
   start - Pick a repo and issue, launch a job
   stop - Graceful stop after current issue finishes
   force_stop - Kill the running job immediately
   status - Show current job state
   help - Show the command list
   ```

BotFather confirms: `Success! Command list updated.`

## 3. Find your Telegram user ID

Ralph uses numeric user IDs (not usernames) for the allowlist. To find yours:

1. Open Telegram and start a chat with [@userinfobot](https://t.me/userinfobot).
2. Send any message (e.g. `/start`).
3. It replies with your profile info including:

   ```
   Id: 123456789
   ```

4. Copy the `Id` value.

To allow multiple people, repeat for each user.

## 4. Configure env vars

### `RALPH_ALLOWED_USERS`

Comma-separated list of numeric Telegram user IDs. Only these IDs can interact with the bot.

```
# Single user
RALPH_ALLOWED_USERS=123456789

# Multiple users
RALPH_ALLOWED_USERS=123456789,987654321,555000111
```

### `RALPH_REPOS`

Comma-separated list of GitHub repository URLs. The bot presents these as options in the `/start` inline menu and refuses to operate on any repo not in this list.

```
# Single repo
RALPH_REPOS=https://github.com/owner/my-project

# Multiple repos
RALPH_REPOS=https://github.com/owner/my-project,https://github.com/owner/other-project
```

Use full HTTPS URLs matching the `github.com/owner/repo` pattern. SSH URLs (`git@github.com:…`) are not supported.
