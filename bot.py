
import os
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.error import BadRequest
from TikTokLive import TikTokLiveClient

# ─────────────────────────────
# CONFIGURATION
# ─────────────────────────────

load_dotenv()

BOT_TOKEN_ID = os.getenv("BOT_TOKEN_ID", "").strip()
BOT_TOKEN_SECRET = os.getenv("BOT_TOKEN_SECRET", "").strip()

TOKEN = f"{BOT_TOKEN_ID}:{BOT_TOKEN_SECRET}"

INTERVAL = max(30, int(os.getenv("CHECK_INTERVAL", "60")))

DATA_FILE = Path(__file__).with_name("tracker_data.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

if not BOT_TOKEN_ID or not BOT_TOKEN_SECRET:
    raise ValueError(
        "Missing BOT_TOKEN_ID or BOT_TOKEN_SECRET in Railway!"
    )

# ─────────────────────────────
# DATA STORAGE
# ─────────────────────────────

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Could not read saved tracking data.")
    return {}

data = load_data()


def save_data():
    DATA_FILE.write_text(json.dumps(data, indent=2))


def get_chat(chat_id):
    key = str(chat_id)

    if key not in data:
        data[key] = {
            "users": {},
            "message_id": None
        }

    return data[key]


# ─────────────────────────────
# TIKTOK LIVE CHECKING
# ─────────────────────────────

async def check_live(username):
    try:
        client = TikTokLiveClient(unique_id=username)

        result = await asyncio.wait_for(
            client.is_live(),
            timeout=20
        )

        return bool(result)

    except Exception as e:
        log.warning(
            "Could not check @%s: %s",
            username,
            e
        )
        return None


def status_text(status):
    if status is True:
        return "🔴 LIVE"
    if status is False:
        return "⚪️ OFFLINE"
    return "❓ UNKNOWN"


# ─────────────────────────────
# DASHBOARD
# ─────────────────────────────

def build_dashboard(chat):
    lines = [
        "📡 TIKTOK LIVE TRACKER",
        "━━━━━━━━━━━━━━━━━━",
        ""
    ]

    users = chat["users"]

    if not users:
        lines.append("No TikTok accounts tracked yet.")
        lines.append("")
        lines.append("Use /track username to add one.")

    else:
        for username, status in sorted(users.items()):
            lines.append(
                f"@{username} — {status_text(status)}"
            )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"🔄 Checks every {INTERVAL} seconds",
        "📍 Statuses update automatically"
    ])

    return "\n".join(lines)


async def update_dashboard(bot, chat_id):
    chat = get_chat(chat_id)
    text = build_dashboard(chat)

    message_id = chat.get("message_id")

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text
            )
            return

        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
            log.warning("Dashboard edit failed: %s", e)

    message = await bot.send_message(
        chat_id=chat_id,
        text=text
    )

    chat["message_id"] = message.message_id
    save_data()


async def refresh_chat(bot, chat_id):
    chat = get_chat(chat_id)

    for username in list(chat["users"]):
        result = await check_live(username)

        if result is not None:
            chat["users"][username] = result

    save_data()
    await update_dashboard(bot, chat_id)


# ─────────────────────────────
# TELEGRAM COMMANDS
# ─────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 Welcome to TikTok LIVE Tracker!\n\n"
        "Track TikTok creators and see when they go LIVE.\n\n"
        "Use /track username to begin.\n"
        "Use /help to see all commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 TIKTOK LIVE TRACKER COMMANDS\n\n"
        "/start — Start the bot\n"
        "/track username — Track a TikTok user\n"
        "/untrack username — Stop tracking a user\n"
        "/untrackall — Remove all tracked users\n"
        "/tracking — Show the LIVE dashboard\n"
        "/refresh — Refresh LIVE statuses\n"
        "/help — Show this command list"
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /track username"
        )
        return

    username = context.args[0].lstrip("@").lower()
    chat_id = update.effective_chat.id
    chat = get_chat(chat_id)

    if username in chat["users"]:
        await update.message.reply_text(
            f"@{username} is already being tracked!"
        )
        return

    chat["users"][username] = None
    save_data()

    await update.message.reply_text(
        f"✅ Now tracking @{username}!"
    )

    await refresh_chat(context.bot, chat_id)


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /untrack username"
        )
        return

    username = context.args[0].lstrip("@").lower()
    chat_id = update.effective_chat.id
    chat = get_chat(chat_id)

    if username not in chat["users"]:
        await update.message.reply_text(
            f"@{username} is not being tracked."
        )
        return

    del chat["users"][username]
    save_data()

    await update_dashboard(context.bot, chat_id)

    await update.message.reply_text(
        f"✅ Stopped tracking @{username}."
    )


async def untrackall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat = get_chat(chat_id)

    chat["users"].clear()
    save_data()

    await update_dashboard(context.bot, chat_id)

    await update.message.reply_text(
        "✅ All TikTok accounts have been removed!"
    )


async def tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update_dashboard(
        context.bot,
        update.effective_chat.id
    )


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "🔄 Checking TikTok LIVE statuses..."
    )

    await refresh_chat(context.bot, chat_id)


# ─────────────────────────────
# AUTOMATIC REFRESH
# ─────────────────────────────

async def auto_refresh(application):
    while True:
        await asyncio.sleep(INTERVAL)

        for chat_id in list(data.keys()):
            try:
                await refresh_chat(
                    application.bot,
                    int(chat_id)
                )
            except Exception as e:
                log.error(
                    "Auto refresh failed for %s: %s",
                    chat_id,
                    e
                )


async def post_init(application):
    application.bot_data["refresh_task"] = (
        asyncio.create_task(auto_refresh(application))
    )

    log.info("Automatic LIVE tracking started.")


async def post_shutdown(application):
    task = application.bot_data.get("refresh_task")

    if task:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


# ─────────────────────────────
# START BOT
# ─────────────────────────────

def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("untrack", untrack))
    application.add_handler(CommandHandler("untrackall", untrackall))
    application.add_handler(CommandHandler("tracking", tracking))
    application.add_handler(CommandHandler("refresh", refresh))

    log.info("TikTok Telegram tracker starting...")

    application.run_polling()


if __name__ == "__main__":
    main()
