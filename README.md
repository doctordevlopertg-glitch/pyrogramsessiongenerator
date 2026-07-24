# Pyrogram Session String Generator Bot

A Telegram bot that walks a user through a login flow and hands back a
**Pyrogram session string** — the same thing you'd normally get from running
Pyrogram's interactive `Client(...).start()` prompt on a terminal, but done
conversationally through Telegram itself.

Flow:

```
/generate
  -> bot: send your API_ID
  -> you: 123456
  -> bot: send your API_HASH
  -> you: abcdef0123456789abcdef0123456789
  -> bot: send your phone number
  -> you: +15551234567
  -> bot: (sends OTP to that account) enter the code
  -> you: a12345b
  -> bot: (if 2FA is on) send your password
  -> you: ********
  -> bot: here's your session string
```

## ⚠️ Security — read this first

A Pyrogram **session string is equivalent to a password** for the Telegram
account it was generated for. Anyone who has it can read messages, send
messages, join/leave chats, and generally act as that account, without
needing the phone or the OTP again.

- Only run this bot for yourself, against your own account, in a private
  chat with a bot **only you** control (i.e., don't add it to a group, and
  don't hand the bot token to anyone else).
- The bot best-effort deletes the messages containing your OTP code and 2FA
  password right after processing them, and never writes them to disk — but
  Telegram's own chat history on your device will still show whatever you
  typed unless you delete it yourself too.
- Never paste a session string into a chat, issue tracker, or anywhere
  public. If one ever leaks, revoke it immediately from **Telegram Settings
  → Devices → [that session] → Terminate**, or terminate all other sessions.
- This script does not add its own extra authentication in front of the
  Telegram login step — the security boundary is exactly Telegram's own
  OTP + 2FA, same as logging in anywhere else.

## 1. Get credentials for the bot itself

1. **API_ID / API_HASH** — create an app at https://my.telegram.org → API
   Development Tools. (This is for the *bot's* own Pyrogram client — you'll
   supply a separate API_ID/API_HASH for the account you're generating a
   session for, inside the chat.)
2. **BOT_TOKEN** — from [@BotFather](https://t.me/BotFather) → `/newbot`.

## 2. Run locally (optional, to test first)

```bash
git clone <this-repo>
cd pyrogram-generator-bot
pip install -r requirements.txt

export API_ID=123456
export API_HASH=your_api_hash
export BOT_TOKEN=your_bot_token

python bot.py
```

Open a private chat with your bot in Telegram and send `/generate`.

## 3. Deploy to Heroku

### Option A — Heroku CLI

```bash
heroku login
heroku create your-app-name

heroku config:set API_ID=123456
heroku config:set API_HASH=your_api_hash
heroku config:set BOT_TOKEN=your_bot_token

git push heroku main

# This app runs as a worker dyno (no web port to bind), so scale it up:
heroku ps:scale worker=1
```

### Option B — Deploy Button

1. Push this folder to a GitHub repo.
2. Update `"repository"` in `app.json` to point at that repo.
3. Add to your repo's README:

   ```markdown
   [![Deploy](https://www.herokuapp.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/yourusername/pyrogram-generator-bot)
   ```

4. Click it, fill in `API_ID` / `API_HASH` / `BOT_TOKEN`, deploy.
5. In the Heroku dashboard → **Resources**, make sure the `worker` dyno is
   turned **on** (worker dynos don't auto-start).

## 4. Bot commands

- `/start` — welcome + security notice
- `/generate` — begins the API_ID → API_HASH → phone → code → (password)
  → session string flow
- `/cancel` — aborts the current flow and disconnects the temporary client
- `/help` — quick recap of the steps

## Notes

- Runs as a Heroku **worker** dyno (long-polling) — there's no HTTP server
  bound to `$PORT`.
- The temporary login client uses `in_memory=True`, so nothing is written to
  disk on the server; the session only exists in memory until it's exported
  as a string and sent to the user, then the client disconnects.
- If Telegram invalidates the OTP code because it detects it was typed in
  plain digit form, the bot's prompt tells you to send it with extra
  characters mixed in (e.g. `a12345b`) — it strips non-digits before use.
