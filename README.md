# Pyrogram Script Generator Bot

A Telegram bot, built with [Pyrogram](https://docs.pyrogram.org/), that lets
users pick a bot "template" from a menu and instantly get back a ready-to-run
Pyrogram bot script as a downloadable `.py` file.

Included templates:

| Key        | Template               | What it does                                   |
|------------|-------------------------|-------------------------------------------------|
| `echo`     | Echo Bot                | Replies with whatever text you send it          |
| `welcome`  | Group Welcome Bot       | Greets new members when they join a group       |
| `admin`    | Admin/Moderation Bot    | `/ban /unban /mute /unmute /kick` commands      |
| `inline`   | Inline Query Bot        | Handles `@bot query` inline mode                |
| `callback` | Inline Buttons Bot      | Inline keyboards + callback query handling      |

## 1. Get your credentials

1. **API_ID / API_HASH** — create an app at https://my.telegram.org → API
   Development Tools.
2. **BOT_TOKEN** — talk to [@BotFather](https://t.me/BotFather) on Telegram,
   run `/newbot`, and copy the token it gives you.

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

Then open Telegram, find your bot, and send `/start`.

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

### Option B — Deploy Button (needs the repo pushed to GitHub first)

1. Push this folder to a GitHub repo.
2. Update the `"repository"` field in `app.json` to point at that repo.
3. Add a button to your repo's README:

   ```markdown
   [![Deploy](https://www.herokuapp.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/yourusername/pyrogram-generator-bot)
   ```

4. Click it, fill in `API_ID` / `API_HASH` / `BOT_TOKEN`, and deploy.
5. After deploy, go to **Resources** in the Heroku dashboard and make sure the
   `worker` dyno is turned **on** (Heroku doesn't auto-start worker dynos).

## 4. Usage in Telegram

- `/start` — welcome message
- `/help` — lists all templates
- `/generate` — shows inline buttons; tap one to receive that template as a
  `.py` file, ready to fill in your own `API_ID` / `API_HASH` / `BOT_TOKEN`
  and run.

## 5. Adding your own templates

Open `bot.py`, add a new `tpl_<name>()` function that returns a string of
Python source code, then register it in the `TEMPLATES` dict near the top of
the handlers section:

```python
TEMPLATES = {
    ...
    "mytemplate": ("My Template", "What it does", tpl_mytemplate),
}
```

It will automatically show up in `/generate` and `/help`.

## Notes

- This bot runs as a Heroku **worker** dyno (long-polling), not a web dyno —
  there's no HTTP server to bind to `$PORT`. Free/eco dynos will sleep after
  inactivity unless you're on a plan that keeps workers alive continuously;
  check current Heroku dyno behavior in your dashboard, since Heroku's free
  tier has changed over time.
- Keep `API_HASH` and `BOT_TOKEN` secret — never commit them to source
  control. Use Heroku Config Vars (or a local `.env` you don't commit).
