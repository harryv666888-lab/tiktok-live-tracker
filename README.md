# Telegram TikTok LIVE Tracker

1. Create a Telegram bot using @BotFather and copy its token.
2. Copy `.env.example` to `.env` and insert the token.
3. On macOS, open Terminal and navigate to this folder.
4. Run `python3 -m venv .venv` and `source .venv/bin/activate`.
5. Run `pip install -r requirements.txt`.
6. Run `python bot.py`.
7. Message your Telegram bot `/track niaxlivess`.

Commands: `/track username`, `/untrack username`, `/untrackall`, `/tracking`, `/refresh`.

The bot edits its own dashboard message. Keep the bot running for ongoing checks. LIVE status uses an unofficial TikTok library and may sometimes be unavailable. Avoid sharing your bot token.
