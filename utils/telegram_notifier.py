"""
Telegram Notification Module for TradePilot NSE.
Formats and dispatches daily End-of-Day BUY WATCH and top-ranked stock alerts to a user's Telegram chat
via the official Telegram Bot HTTP API (`https://api.telegram.org/bot<TOKEN>/sendMessage`).
Uses Python's built-in `urllib.request` so zero extra third-party dependencies are required.
"""
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
import pandas as pd

from config import DISCLAIMER_TEXT
from utils.logging_config import get_logger
from utils.helpers import format_inr, format_pct, now_ist

logger = get_logger("telegram_notifier")


def resolve_telegram_credentials(db=None, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolves Telegram Bot Token, Chat ID, and enabled status from:
    1. Explicit function arguments
    2. Environment variables (`TRADEPILOT_TELEGRAM_BOT_TOKEN`, `TRADEPILOT_TELEGRAM_CHAT_ID`)
    3. SQLite `user_settings` table (`telegram_config`)
    """
    env_token = os.getenv("TRADEPILOT_TELEGRAM_BOT_TOKEN", "").strip()
    env_chat = os.getenv("TRADEPILOT_TELEGRAM_CHAT_ID", "").strip()

    db_cfg = {}
    if db is not None:
        db_cfg = db.get_setting("telegram_config", {}) or {}

    final_token = (bot_token or env_token or db_cfg.get("bot_token", "")).strip()
    final_chat_id = (chat_id or env_chat or db_cfg.get("chat_id", "")).strip()
    enabled = bool(db_cfg.get("enabled", True))
    max_alerts = int(db_cfg.get("max_alerts", 5))
    include_hold_if_empty = bool(db_cfg.get("include_hold_if_empty", True))

    return {
        "bot_token": final_token,
        "chat_id": final_chat_id,
        "enabled": enabled,
        "max_alerts": max_alerts,
        "include_hold_if_empty": include_hold_if_empty,
    }


def format_eod_telegram_message(
    screening_df: pd.DataFrame,
    sync_summary: Optional[Dict[str, Any]] = None,
    max_alerts: int = 5,
    include_hold_if_empty: bool = True,
) -> str:
    """
    Builds an HTML-formatted Telegram summary message highlighting the market breadth and top BUY WATCH setups.
    """
    date_str = now_ist().strftime("%d %b %Y (%H:%M IST)")

    if screening_df is None or screening_df.empty:
        return (
            f"<b>📊 TradePilot NSE — EOD Alert ({date_str})</b>\n\n"
            f"⚠️ No screening records available in database. Please run Smart Sync."
        )

    total_scanned = len(screening_df)
    buy_df = screening_df[screening_df["signal"] == "BUY WATCH"].sort_values("overall_score", ascending=False)
    hold_df = screening_df[screening_df["signal"] == "HOLD WATCH"].sort_values("overall_score", ascending=False)
    avoid_count = int((screening_df["signal"] == "AVOID").sum())
    latest_trade_date = str(screening_df["trade_date"].max())

    lines: List[str] = [
        f"<b>📈 TradePilot NSE — Daily EOD Report</b>",
        f"<b>Bar Date:</b> <code>{latest_trade_date}</code> | <b>Generated:</b> {date_str}",
        f"<b>Universe Breadth:</b> Scanned: <b>{total_scanned}</b> | 🟢 BUY WATCH: <b>{len(buy_df)}</b> | 🟡 HOLD WATCH: <b>{len(hold_df)}</b> | 🔴 AVOID: <b>{avoid_count}</b>",
        "",
    ]

    if not buy_df.empty:
        lines.append(f"<b>🚀 Top {min(len(buy_df), max_alerts)} BUY WATCH Setups:</b>")
        lines.append("")
        for rank, (_, row) in enumerate(buy_df.head(max_alerts).iterrows(), start=1):
            sym = row["symbol"]
            close = format_inr(row["close_price"])
            pct = format_pct(row["daily_pct_change"])
            score = f"{row['overall_score']:.1f}/100"
            entry_z = f"₹{row['entry_low']:,.2f}–₹{row['entry_high']:,.2f}"
            sl = f"₹{row['stop_loss']:,.2f} (-{row['downside_pct']:.1f}%)"
            t1 = f"₹{row['target_1']:,.2f}"
            t2 = f"₹{row['target_2']:,.2f} (+{row['upside_pct']:.1f}%)"
            rr = f"1:{row['risk_reward_ratio']:.2f}"
            strat = row.get("matched_strategies", "N/A")

            lines.append(
                f"<b>{rank}. #{sym}</b> — {close} ({pct}) | <b>Score: {score}</b>\n"
                f"   • <b>Strategy:</b> {strat}\n"
                f"   • <b>Entry Zone:</b> <code>{entry_z}</code>\n"
                f"   • <b>Stop-Loss:</b> <code>{sl}</code>\n"
                f"   • <b>Targets:</b> T1 <code>{t1}</code> | T2 <code>{t2}</code> (<b>R:R {rr}</b>)"
            )
            lines.append("")
    else:
        lines.append("ℹ️ <b>No stocks met strict BUY WATCH criteria today.</b>")
        if include_hold_if_empty and not hold_df.empty:
            lines.append("")
            lines.append(f"<b>👀 Top {min(len(hold_df), 3)} HOLD WATCH Candidates to Monitor:</b>")
            for rank, (_, row) in enumerate(hold_df.head(3).iterrows(), start=1):
                lines.append(
                    f"<b>{rank}. #{row['symbol']}</b> — ₹{row['close_price']:,.2f} ({format_pct(row['daily_pct_change'])}) | "
                    f"Score: <b>{row['overall_score']:.1f}</b> | Entry: <code>₹{row['entry_low']:,.2f}–₹{row['entry_high']:,.2f}</code> | "
                    f"SL: <code>₹{row['stop_loss']:,.2f}</code> | T2: <code>₹{row['target_2']:,.2f}</code>"
                )
            lines.append("")

    if sync_summary:
        lines.append(f"<i>Sync Status: {sync_summary.get('details', 'Completed')}</i>")

    lines.append("<i>⚠️ Analytical estimates only; not investment advice or assured execution prices.</i>")
    return "\n".join(lines)


def send_telegram_message(
    message_html: str,
    bot_token: str,
    chat_id: str,
    timeout_sec: int = 15,
) -> Dict[str, Any]:
    """
    Sends an HTML-formatted message via the Telegram Bot API.
    Returns {'ok': True/False, 'status_code': ..., 'description': ...}.
    """
    if not bot_token or not chat_id:
        return {
            "ok": False,
            "error": "Missing Telegram Bot Token or Chat ID. Configure them in .env or Custom Settings -> Telegram Alerts.",
        }

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": message_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            resp_body = resp.read().decode("utf-8")
            parsed = json.loads(resp_body)
            if parsed.get("ok"):
                logger.info(f"Telegram alert dispatched successfully to chat_id={chat_id}")
                return {"ok": True, "result": parsed.get("result")}
            else:
                err_desc = parsed.get("description", "Unknown Telegram API error")
                logger.error(f"Telegram API rejected message: {err_desc}")
                return {"ok": False, "error": err_desc}
    except urllib.error.HTTPError as http_err:
        try:
            err_body = http_err.read().decode("utf-8")
            err_json = json.loads(err_body)
            desc = err_json.get("description", str(http_err))
        except Exception:
            desc = str(http_err)
        logger.error(f"Telegram HTTP error ({http_err.code}): {desc}")
        return {"ok": False, "error": f"HTTP {http_err.code}: {desc}"}
    except Exception as exc:
        logger.error(f"Failed to send Telegram alert: {exc}")
        return {"ok": False, "error": str(exc)}


def dispatch_eod_telegram_alert(db, sync_summary: Optional[Dict[str, Any]] = None, force_send: bool = False) -> Dict[str, Any]:
    """
    High-level helper called by `eod_auto_update.py` or the Streamlit UI to format and send the latest EOD BUY WATCH alert.
    """
    cfg = resolve_telegram_credentials(db)
    if not cfg["enabled"] and not force_send:
        logger.info("Telegram alerts are disabled in settings; skipping notification.")
        return {"ok": False, "skipped": True, "reason": "Telegram alerts disabled in settings."}

    if not cfg["bot_token"] or not cfg["chat_id"]:
        logger.info("Telegram credentials not configured yet; skipping EOD Telegram notification.")
        return {
            "ok": False,
            "skipped": True,
            "reason": "Telegram Bot Token or Chat ID not configured.",
        }

    df = db.get_all_screening_results()
    msg_html = format_eod_telegram_message(
        screening_df=df,
        sync_summary=sync_summary,
        max_alerts=cfg["max_alerts"],
        include_hold_if_empty=cfg["include_hold_if_empty"],
    )
    return send_telegram_message(
        message_html=msg_html,
        bot_token=cfg["bot_token"],
        chat_id=cfg["chat_id"],
    )
