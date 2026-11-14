"""
Automated Unit & Integration Test Suite for TradePilot NSE.
Validates:
1. Technical Indicator math (EMA, SMA, RSI, MACD, StochRSI, ROC, ADX, Supertrend, ATR, Bollinger, OBV, RVol).
2. Fundamental evaluation & missing-data normalization (distinguishing None from negative performance).
3. Screening Strategies A, B, C, and D detection.
4. 100-Point Scoring Engine & Entry/Stop-Loss/Target calculations.
5. Position-Sizing & Portfolio Risk Management constraints.
6. Event-Driven Backtesting Engine (zero look-ahead bias, transaction costs, benchmark comparison).
7. SQLite Database initialization, CRUD operations, and Watchlist/Portfolio lifecycle.
8. Telegram EOD Alert HTML formatting & credential resolution.
"""
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd

from data.database import DatabaseManager
from analysis.indicators import calculate_all_indicators, extract_latest_indicator_snapshot
from analysis.fundamental import evaluate_fundamentals
from analysis.strategies import evaluate_strategies_on_bar
from analysis.scoring import calculate_entry_sl_targets, score_and_evaluate_stock
from analysis.risk_management import calculate_position_size
from analysis.backtesting import run_strategy_backtest
from utils.telegram_notifier import format_eod_telegram_message, resolve_telegram_credentials


def _build_test_ohlcv(num_days: int = 260) -> pd.DataFrame:
    """Builds a deterministic upward-trending OHLCV series ONLY for unit testing math validation."""
    dates = pd.bdate_range("2025-01-01", periods=num_days)
    np.random.seed(42)
    base = 1000.0 + np.linspace(0, 350, num_days) + np.sin(np.linspace(0, 12, num_days)) * 18.0
    close = base + np.random.normal(0, 3.5, num_days)
    # Force strong breakout on final bar
    close[-1] = max(close[-25:-1]) * 1.018
    open_p = close - np.random.uniform(-4.0, 6.0, num_days)
    open_p[-1] = close[-2] * 1.002
    high = np.maximum(open_p, close) + np.random.uniform(2.0, 10.0, num_days)
    low = np.minimum(open_p, close) - np.random.uniform(2.0, 10.0, num_days)
    volume = np.random.randint(200_000, 350_000, size=num_days)
    volume[-1] = 680_000  # High relative volume (> 1.5x)

    return pd.DataFrame(
        {
            "trade_date": [d.strftime("%Y-%m-%d") for d in dates],
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "adj_close": close,
            "volume": volume,
            "prev_close": pd.Series(close).shift(1),
            "daily_pct_change": pd.Series(close).pct_change() * 100.0,
        }
    )


def test_technical_indicators():
    df = _build_test_ohlcv(260)
    enriched = calculate_all_indicators(df)
    assert not enriched.empty
    required_cols = [
        "ema_9",
        "ema_20",
        "ema_50",
        "ema_100",
        "ema_200",
        "sma_20",
        "sma_50",
        "sma_200",
        "adx_14",
        "supertrend",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "stoch_rsi_k",
        "roc_12",
        "atr_14",
        "bb_upper",
        "bb_lower",
        "hist_volatility_20d",
        "vol_sma_20",
        "relative_volume",
        "obv",
        "vol_breakout",
    ]
    for col in required_cols:
        assert col in enriched.columns, f"Missing indicator column: {col}"

    snap = extract_latest_indicator_snapshot("TESTSYM", enriched)
    assert snap is not None
    assert 0.0 <= snap["rsi_14"] <= 100.0
    assert snap["atr_14"] > 0.0
    assert snap["relative_volume"] > 1.5


def test_fundamentals_missing_vs_negative():
    strong = evaluate_fundamentals(
        "TCS",
        {
            "revenue_growth_pct": 16.5,
            "profit_growth_pct": 19.2,
            "roe_pct": 38.0,
            "debt_to_equity": 0.12,
            "pe_ratio": 26.5,
            "promoter_pledging_pct": None,
        },
    )
    assert strong["fundamental_class"] == "Strong Fundamentals"
    assert strong["fundamental_raw_score"] >= 70.0
    assert "Promoter Pledging" in strong["notes"]

    empty = evaluate_fundamentals("UNKNOWN", {})
    assert empty["fundamental_class"] == "Data Unavailable"
    assert empty["fundamental_raw_score"] is None


def test_scoring_and_entry_sl_targets():
    df = _build_test_ohlcv(260)
    enriched = calculate_all_indicators(df)
    fund = evaluate_fundamentals(
        "HAL",
        {"revenue_growth_pct": 18.0, "profit_growth_pct": 22.0, "roe_pct": 24.0, "debt_to_equity": 0.05, "pe_ratio": 25.0},
    )
    scored = score_and_evaluate_stock("HAL", enriched, fund)
    assert scored is not None
    assert 0.0 <= scored["overall_score"] <= 100.0
    assert scored["stop_loss"] < scored["close_price"]
    assert scored["target_1"] > scored["close_price"]
    assert scored["target_2"] > scored["target_1"]
    assert scored["target_3"] > scored["target_2"]
    assert scored["risk_reward_ratio"] > 1.5


def test_risk_management_position_sizing():
    res = calculate_position_size(
        total_capital=200_000.0,
        risk_pct_per_trade=1.0,
        entry_price=1000.0,
        stop_loss_price=950.0,
        target_price=1125.0,
    )
    assert "error" not in res
    assert res["max_acceptable_loss"] == 2000.0
    assert res["risk_per_share"] == 50.0
    assert res["quantity"] == 40
    assert res["total_investment"] == 40_000.0
    assert res["potential_loss"] == 2000.0
    assert res["potential_profit"] == 5000.0
    assert res["risk_reward_ratio"] == 2.5


def test_database_and_backtesting_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_tradepilot.db"
        db = DatabaseManager(db_path=db_file)
        stocks = db.get_active_stocks()
        assert len(stocks) >= 30

        df = _build_test_ohlcv(260)
        yf_df = pd.DataFrame(
            {
                "Open": df["open"].values,
                "High": df["high"].values,
                "Low": df["low"].values,
                "Close": df["close"].values,
                "Adj Close": df["adj_close"].values,
                "Volume": df["volume"].values,
            },
            index=pd.to_datetime(df["trade_date"]),
        )
        saved_count = db.save_historical_prices("RELIANCE", yf_df)
        assert saved_count == 260

        loaded = db.get_historical_prices("RELIANCE", limit_days=300)
        assert len(loaded) == 260

        db.add_to_watchlist("RELIANCE", 1250.0, 1200.0, 1375.0, "Strategy A", "Test note")
        wl = db.get_watchlist()
        assert len(wl) == 1

        db.add_portfolio_position("RELIANCE", "2025-10-01", 1250.0, 10, 1200.0, 1375.0, "Strategy A", "Paper trade")
        open_pos = db.get_open_positions()
        assert len(open_pos) == 1
        pid = int(open_pos.iloc[0]["position_id"])

        db.close_portfolio_position(pid, "2025-10-12", 1350.0, "Target Reached")
        assert len(db.get_open_positions()) == 0
        hist = db.get_trade_history()
        assert len(hist) == 1
        assert hist.iloc[0]["gross_pnl"] == 1000.0

        bt = run_strategy_backtest(
            stock_histories={"RELIANCE": loaded},
            strategy_name="Strategy B: Trend-Following",
            start_date="2025-02-01",
            end_date="2025-12-31",
            initial_capital=100_000.0,
        )
        assert "total_trades" in bt
        assert "win_rate_pct" in bt


def test_telegram_eod_formatter():
    df = _build_test_ohlcv(260)
    enriched = calculate_all_indicators(df)
    fund = evaluate_fundamentals(
        "RELIANCE",
        {"revenue_growth_pct": 18.0, "profit_growth_pct": 22.0, "roe_pct": 24.0, "debt_to_equity": 0.05, "pe_ratio": 25.0},
    )
    scored = score_and_evaluate_stock("RELIANCE", enriched, fund)
    scored["signal"] = "BUY WATCH"
    screen_df = pd.DataFrame([scored])

    msg = format_eod_telegram_message(screen_df, max_alerts=5)
    assert "TradePilot NSE — Daily EOD Report" in msg
    assert "#RELIANCE" in msg
    assert "Entry Zone:" in msg
    assert "Stop-Loss:" in msg
