"""
End-to-End Screening Pipeline Coordinator for TradePilot NSE.
Iterates over the active NSE stock universe, computes all technical indicators,
evaluates fundamentals, runs the 4 screening strategies, calculates 100-point scores
and entry/SL/targets, and persists results into SQLite.
"""
from typing import Any, Dict, List, Optional
from data.database import DatabaseManager
from analysis.indicators import calculate_all_indicators, extract_latest_indicator_snapshot
from analysis.scoring import score_and_evaluate_stock
from utils.logging_config import get_logger

logger = get_logger("pipeline")


def run_full_screening_pipeline(db: DatabaseManager, progress_callback=None) -> Dict[str, Any]:
    stocks = db.get_active_stocks()
    horizon = db.get_setting("trading_horizon", "1-2 Weeks")
    enabled_strategies = db.get_setting("enabled_strategies", None)
    weights = db.get_setting("scoring_weights", None)

    processed = 0
    skipped = 0

    for i, stock in enumerate(stocks):
        sym = stock["symbol"]
        if progress_callback:
            progress_callback(i + 1, len(stocks), sym)

        hist_df = db.get_historical_prices(sym, limit_days=400)
        if hist_df.empty or len(hist_df) < 30:
            skipped += 1
            continue

        enriched_df = calculate_all_indicators(hist_df)
        if enriched_df.empty:
            skipped += 1
            continue

        ind_snapshot = extract_latest_indicator_snapshot(sym, enriched_df)
        if ind_snapshot:
            db.save_technical_indicators(ind_snapshot)

        fund_row = db.get_fundamental_data(sym)
        screen_row = score_and_evaluate_stock(
            symbol=sym,
            enriched_df=enriched_df,
            fundamental_row=fund_row,
            weights=weights,
            horizon=horizon,
            enabled_strategies=enabled_strategies,
        )
        if screen_row:
            db.save_screening_result(screen_row)
            processed += 1
        else:
            skipped += 1

    return {"processed": processed, "skipped": skipped, "total": len(stocks)}
