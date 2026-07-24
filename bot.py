"""
Pyrogram Session String Generator Bot
======================================
A Telegram bot that walks a user through generating a Pyrogram
*user* session string:

    /generate  ->  bot asks for API_ID
                ->  bot asks for API_HASH
                ->  bot asks for phone number (international format)
                ->  bot sends an OTP code to that account via Telegram
                ->  user sends the code back to the bot
                ->  (if 2FA is enabled) bot asks for the cloud password
                ->  bot replies with the session string

IMPORTANT SECURITY NOTES (read before deploying / using):
  - A Pyrogram session string grants FULL access to the Telegram account
    it was generated for (read messages, send messages, delete account,
    etc.), exactly like the account's login session. Treat it like a
    password. Never send it to anyone, never paste it in a public chat.
  - This bot should only be used by you, for your own account(s), ideally
    in a private chat with a bot only you control. Anyone who can talk to
    this bot and complete the phone+code (+password) flow can generate a
    session for whatever phone number they enter — that's inherent to how
    Telegram login works, not something this script can restrict beyond
    the OTP/2FA check.
  - The bot deletes the message containing the user's OTP code and 2FA
    password from the chat as soon as it processes them (best-effort;
    Telegram may prevent deletion in some edge cases), and never logs
    them to disk.
  - The bot itself (BOT_TOKEN/API_ID/API_HASH in your environment) is
    just used to run the *bot*; the account being logged into during
    /generate is a separate, user-supplied API_ID/API_HASH/phone.

Environment variables required for the BOT itself (Heroku Config Vars):
    API_ID      - API ID for the *bot* client (https://my.telegram.org)
    API_HASH    - API HASH for the *bot* client
    BOT_TOKEN   - bot token from @BotFather
"""

import os
import logging

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PasswordHashInvalid,
    SessionPasswordNeeded,
    FloodWait,
)

# --------------------------------------------------------------------------
# Config for the bot itself
# --------------------------------------------------------------------------

BOT_API_ID = int(os.environ.get("API_ID", "0"))
BOT_API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

if not (BOT_API_ID and BOT_API_HASH and BOT_TOKEN):
    raise SystemExit(
        "Missing API_ID / API_HASH / BOT_TOKEN for the bot itself. "
        "Set them as environment variables (Heroku Config Vars)."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("session-gen-bot")

bot = Client(
    "session_generator_bot",
    api_id=BOT_API_ID,
    api_hash=BOT_API_HASH,
    bot_token=BOT_TOKEN,
)

# --------------------------------------------------------------------------
# Per-user conversation state
# --------------------------------------------------------------------------
# sessions[user_id] = {
#     "step": "api_id" | "api_hash" | "phone" | "code" | "password",
#     "api_id": int,
#     "api_hash": str,
#     "phone": str,
#     "phone_code_hash": str,
#     "client": Client,   # temporary user-login client (in_memory)
# }
sessions: dict[int, dict] = {}

STEP_API_ID = "api_id"
STEP_API_HASH = "api_hash"
STEP_PHONE = "phone"
STEP_CODE = "code"
STEP_PASSWORD = "password"

CANCEL_HINT = "\n\nSend /cancel at any time to stop."


async def cleanup(user_id: int, disconnect: bool = True):
    """Remove state and disconnect any temporary login client."""
    state = sessions.pop(user_id, None)
    if state and disconnect:
        client = state.get("client")
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass


async def safe_delete(message: Message):
    """Best-effort delete of a message that contained sensitive input."""
    try:
        await message.delete()
    except Exception:
        pass


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------


@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    await message.reply_text(
        "**Pyrogram Session String Generator**\n\n"
        "This bot logs into a Telegram account (using its own API_ID / "
        "API_HASH + your phone number + OTP, and 2FA password if set) "
        "and gives you back a Pyrogram session string for it.\n\n"
        "⚠️ A session string is equivalent to your account password — "
        "never share it with anyone. Only use this bot on yourself, "
        "in a private chat with a bot you trust/control.\n\n"
        "Send /generate to begin."
    )


@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client: Client, message: Message):
    if message.from_user.id in sessions:
        await cleanup(message.from_user.id)
        await message.reply_text("Cancelled. Send /generate to start again.")
    else:
        await message.reply_text("Nothing to cancel.")


@bot.on_message(filters.command("generate") & filters.private)
async def generate_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in sessions:
        await cleanup(user_id)

    sessions[user_id] = {"step": STEP_API_ID}
    await message.reply_text(
        "Step 1/4 — Send your **API_ID**.\n"
        "(Get it from https://my.telegram.org → API Development Tools)"
        + CANCEL_HINT
    )


@bot.on_message(filters.command("help") & filters.private)
async def help_cmd(client: Client, message: Message):
    await message.reply_text(
        "**How this works**\n"
        "1. /generate\n"
        "2. Send your API_ID\n"
        "3. Send your API_HASH\n"
        "4. Send your phone number (e.g. +15551234567)\n"
        "5. Send the OTP code Telegram sends you\n"
        "6. If 2FA is on, send your cloud password\n"
        "7. Receive your Pyrogram session string\n\n"
        "/cancel — abort the current flow at any point."
    )


# --------------------------------------------------------------------------
# Conversation flow (plain text messages, routed by current step)
# --------------------------------------------------------------------------


@bot.on_message(
    filters.private
    & filters.text
    & ~filters.command(["start", "generate", "cancel", "help"])
)
async def on_text(client: Client, message: Message):
    user_id = message.from_user.id
    state = sessions.get(user_id)
    if not state:
        await message.reply_text("Send /generate to start creating a session string.")
        return

    step = state["step"]

    if step == STEP_API_ID:
        await handle_api_id(message, state)
    elif step == STEP_API_HASH:
        await handle_api_hash(message, state)
    elif step == STEP_PHONE:
        await handle_phone(message, state)
    elif step == STEP_CODE:
        await handle_code(message, state)
    elif step == STEP_PASSWORD:
        await handle_password(message, state)


async def handle_api_id(message: Message, state: dict):
    text = message.text.strip()
    if not text.isdigit():
        await message.reply_text("That doesn't look like a number. Send just your API_ID (digits only).")
        return
    state["api_id"] = int(text)
    state["step"] = STEP_API_HASH
    await message.reply_text("Step 2/4 — Now send your **API_HASH**." + CANCEL_HINT)


async def handle_api_hash(message: Message, state: dict):
    api_hash = message.text.strip()
    if len(api_hash) < 10:
        await message.reply_text("That doesn't look like a valid API_HASH. Please check and resend.")
        return
    state["api_hash"] = api_hash
    state["step"] = STEP_PHONE
    await safe_delete(message)  # api_hash is semi-sensitive; tidy the chat
    await message.reply_text(
        "Step 3/4 — Send your phone number in **international format**, "
        "e.g. `+15551234567`." + CANCEL_HINT
    )


async def handle_phone(message: Message, state: dict):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].replace(" ", "").isdigit():
        await message.reply_text("Please send the phone number in international format, e.g. `+15551234567`.")
        return

    status_msg = await message.reply_text("Connecting and requesting an OTP code, please wait...")

    login_client = Client(
        name=":memory:",
        api_id=state["api_id"],
        api_hash=state["api_hash"],
        in_memory=True,
    )

    try:
        await login_client.connect()
        sent_code = await login_client.send_code(phone)
    except ApiIdInvalid:
        await status_msg.edit_text("Invalid API_ID / API_HASH pair. Send /generate to try again.")
        await cleanup(message.from_user.id)
        return
    except PhoneNumberInvalid:
        await status_msg.edit_text("Invalid phone number. Send /generate to try again.")
        await cleanup(message.from_user.id)
        return
    except FloodWait as e:
        await status_msg.edit_text(f"Rate limited by Telegram. Try again in {e.value} seconds.")
        await cleanup(message.from_user.id)
        return
    except Exception as e:
        log.exception("send_code failed")
        await status_msg.edit_text(f"Failed to send code: {e}\nSend /generate to try again.")
        await cleanup(message.from_user.id)
        return

    state["phone"] = phone
    state["phone_code_hash"] = sent_code.phone_code_hash
    state["client"] = login_client
    state["step"] = STEP_CODE

    await status_msg.edit_text(
        "Step 4/4 — Enter the login code Telegram just sent you.\n\n"
        "To avoid Telegram auto-invalidating the code, type it with "
        "extra characters around the digits, e.g. if the code is "
        "`12345` send `1-2-3-4-5` or `a12345b`. I'll strip non-digits."
        + CANCEL_HINT
    )


async def handle_code(message: Message, state: dict):
    raw = message.text.strip()
    code = "".join(ch for ch in raw if ch.isdigit())
    await safe_delete(message)

    if not code:
        await message.reply_text("That didn't contain any digits. Please resend the code.")
        return

    login_client: Client = state["client"]

    try:
        await login_client.sign_in(
            phone_number=state["phone"],
            phone_code_hash=state["phone_code_hash"],
            phone_code=code,
        )
    except PhoneCodeInvalid:
        await message.reply_text("Invalid code. Please resend the code Telegram sent you.")
        return
    except PhoneCodeExpired:
        await message.reply_text("Code expired. Send /generate to start over.")
        await cleanup(message.from_user.id)
        return
    except SessionPasswordNeeded:
        state["step"] = STEP_PASSWORD
        await message.reply_text(
            "This account has Two-Step Verification enabled.\n"
            "Send your **cloud password**." + CANCEL_HINT
        )
        return
    except FloodWait as e:
        await message.reply_text(f"Rate limited by Telegram. Try again in {e.value} seconds.")
        await cleanup(message.from_user.id)
        return
    except Exception as e:
        log.exception("sign_in failed")
        await message.reply_text(f"Sign-in failed: {e}\nSend /generate to try again.")
        await cleanup(message.from_user.id)
        return

    await finish_and_send_session(message, state)


async def handle_password(message: Message, state: dict):
    password = message.text
    await safe_delete(message)

    login_client: Client = state["client"]

    try:
        await login_client.check_password(password)
    except PasswordHashInvalid:
        await message.reply_text("Incorrect password. Please try again.")
        return
    except FloodWait as e:
        await message.reply_text(f"Rate limited by Telegram. Try again in {e.value} seconds.")
        await cleanup(message.from_user.id)
        return
    except Exception as e:
        log.exception("check_password failed")
        await message.reply_text(f"Password check failed: {e}\nSend /generate to try again.")
        await cleanup(message.from_user.id)
        return

    await finish_and_send_session(message, state)


async def finish_and_send_session(message: Message, state: dict):
    login_client: Client = state["client"]
    try:
        session_string = await login_client.export_session_string()
    except Exception as e:
        log.exception("export_session_string failed")
        await message.reply_text(f"Could not export session string: {e}")
        await cleanup(message.from_user.id)
        return

    await message.reply_text(
        "✅ **Session generated successfully.**\n\n"
        "`" + session_string + "`\n\n"
        "⚠️ Copy this now and store it somewhere safe (e.g. as a Heroku "
        "config var `SESSION_STRING`). This message will not be shown "
        "again — treat this string like a password and never share it. "
        "Anyone with this string has full access to the account."
    )
    await cleanup(message.from_user.id)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting Pyrogram Session String Generator Bot...")
    bot.run()
