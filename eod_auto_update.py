"""
Automated End-of-Day Update, Daily Screening, 1-Month Paper Trial & Telegram Alert Runner for TradePilot NSE.
Can be executed from the command line or scheduled via Windows Task Scheduler at 16:15 IST every weekday:
    python eod_auto_update.py
"""
import argparse
from pathlib import Path
from config import EXPORTS_DIR
from data.database import DatabaseManager
from data.market_data import MarketDataService
from analysis.pipeline import run_full_screening_pipeline
from analysis.paper_trial import run_daily_paper_trial_step
from utils.telegram_notifier import dispatch_eod_telegram_alert
from utils.logging_config import get_logger
from utils.helpers import now_ist

logger = get_logger("eod_automation")


def run_eod_job(force_refresh: bool = False, send_telegram: bool = True, run_paper_trial: bool = True) -> dict:
    logger.info("Starting TradePilot NSE End-of-Day automated sync & screening job...")
    db = DatabaseManager()
    service = MarketDataService(db)

    sync_res = service.refresh_stock_universe(force=force_refresh, fetch_fundamentals=True)
    logger.info(f"Market data sync finished: {sync_res['details']}")

    pipe_res = run_full_screening_pipeline(db)
    logger.info(f"Screening pipeline finished: Processed={pipe_res['processed']}, Skipped={pipe_res['skipped']}")

    trial_res = {"skipped": True}
    if run_paper_trial:
        trial_res = run_daily_paper_trial_step(db)
        logger.info(f"Paper Trial step finished: {trial_res}")

    df = db.get_all_screening_results()
    csv_path = None
    if not df.empty:
        date_tag = now_ist().strftime("%Y%m%d")
        csv_path = Path(EXPORTS_DIR) / f"TradePilot_NSE_EOD_{date_tag}.csv"
        xlsx_path = Path(EXPORTS_DIR) / f"TradePilot_NSE_EOD_{date_tag}.xlsx"
        df.to_csv(csv_path, index=False)
        try:
            df.to_excel(xlsx_path, index=False, engine="openpyxl")
        except Exception as exc:
            logger.warning(f"Excel export skipped: {exc}")
        logger.info(f"Saved EOD screening exports to {csv_path}")

    tg_res = {"ok": False, "skipped": True}
    if send_telegram:
        tg_res = dispatch_eod_telegram_alert(db, sync_summary=sync_res)
        if tg_res.get("ok"):
            logger.info("Daily BUY WATCH Telegram alert sent successfully!")
        elif tg_res.get("skipped"):
            logger.info(f"Telegram alert skipped: {tg_res.get('reason')}")
        else:
            logger.warning(f"Telegram alert failed: {tg_res.get('error')}")

    return {
        "sync": sync_res,
        "pipeline": pipe_res,
        "paper_trial": trial_res,
        "csv_export": str(csv_path) if csv_path else None,
        "telegram": tg_res,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradePilot NSE End-of-Day Sync, Screener, Paper Trial & Telegram Notifier")
    parser.add_argument("--force", action="store_true", help="Force full OHLCV download even if latest bar is cached")
    parser.add_argument("--no-telegram", action="store_true", help="Skip sending Telegram notification")
    parser.add_argument("--no-trial", action="store_true", help="Skip automated 1-Month Paper Trial step")
    args = parser.parse_args()

    run_eod_job(force_refresh=args.force, send_telegram=not args.no_telegram, run_paper_trial=not args.no_trial)
