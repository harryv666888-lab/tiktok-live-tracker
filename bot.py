import asyncio
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes
from TikTokLive import TikTokLiveClient

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
INTERVAL = max(30, int(os.getenv('CHECK_INTERVAL', '60')))
DATA_FILE = Path(__file__).with_name('tracker_data.json')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def load_data():
    try:
        return json.loads(DATA_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_data(data):
    temp = DATA_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temp.replace(DATA_FILE)


def clean_username(value):
    value = value.strip().removeprefix('@').lower()
    return value if re.fullmatch(r'[a-z0-9._]{2,24}', value) else None


def dashboard(chat):
    users = chat.get('users', {})
    lines = ['📡 TikTok LIVE Tracker', '', f'Tracking {len(users)} account(s)', '']
    for username, status in sorted(users.items()):
        marker = {'live': '🟢 LIVE', 'offline': '⚪ OFFLINE', 'unknown': '🟡 UNKNOWN'}.get(status, '🟡 UNKNOWN')
        lines.append(f'@{username} — {marker}')
    if not users:
        lines.append('No accounts yet. Use /track username')
    lines.extend(['', 'Statuses checked periodically. 🟡 means TikTok could not be checked.'])
    return '\n'.join(lines)


async def update_dashboard(bot, chat_id, chat, force=False):
    content = dashboard(chat)
    message_id = chat.get('message_id')
    if message_id:
        try:
            await bot.edit_message_text(chat_id=int(chat_id), message_id=message_id, text=content)
            return
        except BadRequest as exc:
            if 'Message is not modified' in str(exc):
                return
            log.warning('Cannot edit dashboard for %s: %s', chat_id, exc)
        except TelegramError as exc:
            log.warning('Dashboard edit failed for %s: %s', chat_id, exc)
    message = await bot.send_message(chat_id=int(chat_id), text=content)
    chat['message_id'] = message.message_id


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Usage: /track username')
        return
    username = clean_username(context.args[0])
    if not username:
        await update.message.reply_text('Invalid TikTok username.')
        return
    async with context.application.bot_data['lock']:
        data = load_data()
        chat = data.setdefault(str(update.effective_chat.id), {'users': {}})
        chat.setdefault('users', {})
        if username in chat['users']:
            await update.message.reply_text(f'@{username} is already tracked.')
            return
        chat['users'][username] = 'unknown'
        await update_dashboard(context.bot, update.effective_chat.id, chat)
        save_data(data)
    await update.message.reply_text(f'Now tracking @{username}.')


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Usage: /untrack username')
        return
    username = clean_username(context.args[0])
    async with context.application.bot_data['lock']:
        data = load_data()
        chat = data.get(str(update.effective_chat.id), {'users': {}})
        if not username or username not in chat.get('users', {}):
            await update.message.reply_text('That account is not tracked.')
            return
        del chat['users'][username]
        await update_dashboard(context.bot, update.effective_chat.id, chat)
        data[str(update.effective_chat.id)] = chat
        save_data(data)
    await update.message.reply_text(f'Stopped tracking @{username}.')


async def untrackall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with context.application.bot_data['lock']:
        data = load_data()
        chat = data.setdefault(str(update.effective_chat.id), {'users': {}})
        chat['users'] = {}
        await update_dashboard(context.bot, update.effective_chat.id, chat)
        save_data(data)
    await update.message.reply_text('All accounts removed.')


async def tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with context.application.bot_data['lock']:
        data = load_data()
        chat = data.setdefault(str(update.effective_chat.id), {'users': {}})
        await update_dashboard(context.bot, update.effective_chat.id, chat)
        save_data(data)
    await update.message.reply_text('Dashboard is up to date.')


async def check_live(username):
    try:
        client = TikTokLiveClient(unique_id=username)
        result = await asyncio.wait_for(client.is_live(), timeout=20)
        return 'live' if result else 'offline'
    except Exception as exc:
        log.warning('TikTok check failed for @%s: %s', username, exc)
        return 'unknown'


async def check_all(context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    if app.bot_data['lock'].locked():
        return
    async with app.bot_data['lock']:
        data = load_data()
        changed = False
        for chat_id, chat in data.items():
            for username, previous in list(chat.get('users', {}).items()):
                status = await check_live(username)
                if status != previous:
                    chat['users'][username] = status
                    changed = True
            if changed:
                try:
                    await update_dashboard(context.bot, chat_id, chat)
                except TelegramError as exc:
                    log.warning('Could not update chat %s: %s', chat_id, exc)
        if changed:
            save_data(data)


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Checking LIVE statuses now…')
    await check_all(context)


def main():
    if not TOKEN or TOKEN == 'PASTE_YOUR_BOTFATHER_TOKEN_HERE':
        raise SystemExit('Set TELEGRAM_BOT_TOKEN in .env first.')
    app = Application.builder().token(TOKEN).build()
    app.bot_data['lock'] = asyncio.Lock()
    for name, handler in [('track', track), ('untrack', untrack), ('untrackall', untrackall), ('tracking', tracking), ('refresh', refresh)]:
        app.add_handler(CommandHandler(name, handler))
    app.job_queue.run_repeating(check_all, interval=INTERVAL, first=5)
    log.info('TikTok Telegram tracker started.')
    app.run_polling()


if __name__ == '__main__':
    main()
