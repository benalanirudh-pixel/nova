"""Telegram push updates for Nova Desk. One-way: Nova sends, it never reads commands.

Off unless configured. Token and chat id come from env TELEGRAM_BOT_TOKEN /
TELEGRAM_CHAT_ID, or from the git-ignored telegram_config.json in the project
root: {"bot_token": "...", "chat_id": "..."}. Analysis only: no orders, no BUY/SELL.

Setup check:  .\\venv\\Scripts\\python.exe -m web.api.telegram
"""
import json
import os
import sys
from pathlib import Path

import requests

CONFIG_PATH = Path(__file__).resolve().parents[2] / "telegram_config.json"
API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram rejects messages over 4096 chars


def _config() -> tuple[str, str]:
    cfg = {}
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))  # PowerShell writes a BOM
    except (OSError, ValueError):
        pass
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or str(cfg.get("bot_token", "")).strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or str(cfg.get("chat_id", "")).strip()
    return token, chat


def is_configured() -> bool:
    return all(_config())


def send(text: str) -> bool:
    """Send a plain-text message. Never raises: a Telegram outage must not break a scan."""
    token, chat = _config()
    if not (token and chat):
        return False
    try:
        r = requests.post(API.format(token=token, method="sendMessage"),
                          json={"chat_id": chat, "text": text[:MAX_LEN], "disable_web_page_preview": True},
                          timeout=15)
        if not r.ok:
            print(f"[TELEGRAM] send failed: HTTP {r.status_code} {r.text[:200]}")
        return r.ok
    except requests.RequestException as exc:
        print(f"[TELEGRAM] send failed: {exc}")
        return False


def _setup_check() -> int:
    token, chat = _config()
    if not token:
        print("No bot token. Create a bot with @BotFather, then set TELEGRAM_BOT_TOKEN or telegram_config.json.")
        return 1
    if not chat:
        # the bot only sees chats where someone messaged it first
        r = requests.get(API.format(token=token, method="getUpdates"), timeout=15).json()
        chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name") or u["message"]["chat"].get("title")
                 for u in r.get("result", []) if "message" in u}
        print("No chat id. Send your bot any message, re-run, then use one of:" if not chats else "Chats found (put the id in chat_id):")
        for cid, name in chats.items():
            print(f"  {cid}  {name}")
        return 1
    ok = send("Nova Desk connected: pre-market 09:10, hourly 10:15-15:15, rescans 09:20/12:20/15:35/18:00, post-market after the 18:00 scan.")
    print("Test message sent." if ok else "Send failed, see error above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_setup_check())
