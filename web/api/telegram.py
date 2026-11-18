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


def _pct(v) -> str:
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "n/a"


def summary(report: dict) -> str:
    """Short scan digest. Missing fields show as n/a, never invented."""
    snap = report.get("nifty_snapshot") or {}
    vix = (report.get("volatility") or {}).get("india_vix") or {}
    b = report.get("breadth") or {}
    price = snap.get("price")
    lines = [
        f"NOVA scan {str(report.get('generated', ''))[:16].replace('T', ' ')} IST",
        f"Regime: {report.get('market_regime', 'n/a')}",
        f"NIFTY {price:,.1f} ({_pct(snap.get('change_percent'))})" if isinstance(price, (int, float)) and snap.get("available") else "NIFTY: n/a",
        f"BANKNIFTY 1D {_pct((report.get('bank_nifty_returns') or {}).get('1D'))}",
        f"VIX {vix['value']:.2f} ({_pct(vix.get('change_percent'))}, {vix.get('regime', '?')})" if vix.get("available") and isinstance(vix.get("value"), (int, float)) else "VIX: n/a",
        f"Breadth: {b.get('advancing', 'n/a')} up / {b.get('declining', 'n/a')} down of {b.get('total', 'n/a'):.0f}" if isinstance(b.get("total"), (int, float)) else "Breadth: n/a",
    ]
    sectors = (report.get("sector_intelligence") or {}).get("top_sectors") or []
    if sectors:
        lines.append("Top sectors (20D): " + ", ".join(f"{s.get('sector')} {_pct(s.get('return_20d'))}" for s in sectors[:3]))
    stocks = report.get("top_technical_stocks") or []
    if stocks:
        lines.append("Top technical scores: " + ", ".join(f"{s.get('symbol')} {s.get('technical_score', 0):.0f}" for s in stocks[:5]))
    events = report.get("event_risk_context") or {}
    if events.get("status") == "NOT_AVAILABLE" or events.get("source_fresh") is False:
        lines.append("Warning: event calendar stale or unavailable")
    lines.append("Analysis only. Not a buy/sell signal.")
    return "\n".join(lines)


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
    ok = send("Nova Desk connected. You'll get a digest after each scheduled scan.")
    print("Test message sent." if ok else "Send failed, see error above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_setup_check())
