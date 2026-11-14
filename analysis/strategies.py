"""
Stock Screening Strategies Engine for TradePilot NSE.
Implements 4 independently configurable short-term NSE trading strategies:
- Strategy A: Momentum Breakout
- Strategy B: Trend-Following
- Strategy C: Pullback Entry
- Strategy D: Early Momentum

All strategies can be evaluated on the latest bar (for daily screening) or across historical bars (for backtesting).
"""
from typing import Any, Dict, List
import pandas as pd
import numpy as np


def evaluate_strategies_on_bar(df: pd.DataFrame, idx: int = -1, enabled_strategies: List[str] = None) -> Dict[str, Any]:
    """
    Evaluates Strategies A, B, C, and D at row index `idx` of an indicator-enriched DataFrame.
    Returns matched strategies, detailed rule checks, and primary opportunity category.
    """
    if df is None or df.empty or len(df) < 5:
        return {"matched": [], "details": {}, "primary_category": "Watchlist"}

    if idx < 0:
        idx = len(df) + idx
    if idx < 2 or idx >= len(df):
        return {"matched": [], "details": {}, "primary_category": "Watchlist"}

    row = df.iloc[idx]
    prev = df.iloc[idx - 1]
    prev2 = df.iloc[idx - 2]

    close = float(row["close"])
    open_p = float(row["open"])
    low = float(row["low"])
    ema20 = row.get("ema_20")
    ema50 = row.get("ema_50")
    ema200 = row.get("ema_200")
    rsi = row.get("rsi_14")
    prev_rsi = prev.get("rsi_14")
    adx = row.get("adx_14")
    macd_hist = row.get("macd_hist")
    prev_macd_hist = prev.get("macd_hist")
    rel_vol = row.get("relative_volume")
    prev_rel_vol = prev.get("relative_volume")
    res20 = row.get("resistance_20d")

    def valid(*vals) -> bool:
        return all(v is not None and not (isinstance(v, float) and np.isnan(v)) for v in vals)

    matched: List[str] = []
    details: Dict[str, List[str]] = {}

    # -------------------------------------------------------------------------
    # Strategy A: Momentum Breakout
    # - Price above EMA 20 and EMA 50
    # - EMA 20 above EMA 50
    # - RSI between 55 and 70 (up to 73 allowed on strong breakout day)
    # - MACD bullish crossover or positive momentum
    # - Volume > 1.5x 20-day average
    # - Breakout above recent resistance (or within 0.8% of 20d high with strong close)
    # -------------------------------------------------------------------------
    strat_a_name = "Strategy A: Momentum Breakout"
    if enabled_strategies is None or strat_a_name in enabled_strategies:
        if valid(ema20, ema50, rsi, macd_hist, rel_vol, res20):
            cond_price_ema = (close > ema20) and (close > ema50)
            cond_ema_stack = ema20 > ema50
            cond_rsi = 55.0 <= rsi <= 73.0
            cond_macd = (macd_hist > 0) and (prev_macd_hist is None or np.isnan(prev_macd_hist) or macd_hist >= prev_macd_hist * 0.9)
            cond_vol = rel_vol >= 1.5
            cond_breakout = close >= (res20 * 0.992)

            if cond_price_ema and cond_ema_stack and cond_rsi and cond_macd and cond_vol and cond_breakout:
                matched.append(strat_a_name)
                details[strat_a_name] = [
                    f"Close (₹{close:.2f}) broke out near/above 20D resistance (₹{res20:.2f})",
                    f"Bullish EMA alignment (Close > EMA20 ₹{ema20:.2f} > EMA50 ₹{ema50:.2f})",
                    f"Strong volume expansion ({rel_vol:.2f}x 20D average)",
                    f"Momentum in sweet spot (RSI {rsi:.1f}, positive MACD histogram)",
                ]

    # -------------------------------------------------------------------------
    # Strategy B: Trend-Following
    # - Price above EMA 50
    # - EMA 50 above EMA 200
    # - ADX above 20
    # - RSI between 50 and 65
    # - Positive MACD histogram
    # - Consistent volume (Relative Volume >= 0.85)
    # -------------------------------------------------------------------------
    strat_b_name = "Strategy B: Trend-Following"
    if enabled_strategies is None or strat_b_name in enabled_strategies:
        if valid(ema50, ema200, adx, rsi, macd_hist, rel_vol):
            cond_price = close > ema50
            cond_golden = ema50 > ema200
            cond_adx = adx >= 20.0
            cond_rsi = 50.0 <= rsi <= 66.0
            cond_macd = macd_hist > 0
            cond_vol = rel_vol >= 0.85

            if cond_price and cond_golden and cond_adx and cond_rsi and cond_macd and cond_vol:
                matched.append(strat_b_name)
                details[strat_b_name] = [
                    f"Structural uptrend: Close > EMA50 (₹{ema50:.2f}) > EMA200 (₹{ema200:.2f})",
                    f"Strong trend strength (ADX {adx:.1f} > 20)",
                    f"Sustainable momentum (RSI {rsi:.1f} in 50–65 zone, MACD Hist > 0)",
                    f"Consistent volume support ({rel_vol:.2f}x 20D avg)",
                ]

    # -------------------------------------------------------------------------
    # Strategy C: Pullback Entry
    # - Strong established uptrend (EMA 20 > EMA 50 and Close > EMA 50)
    # - Price retraces towards EMA 20 or EMA 50 (low within 2.5% of EMA20 or EMA50)
    # - RSI recovers from a lower level (RSI > prev_rsi and RSI between 42 and 60)
    # - Bullish reversal confirmation (Close > Open and Close > prev Close)
    # - Volume confirmation (Relative volume >= 0.9)
    # -------------------------------------------------------------------------
    strat_c_name = "Strategy C: Pullback Entry"
    if enabled_strategies is None or strat_c_name in enabled_strategies:
        if valid(ema20, ema50, rsi, prev_rsi, rel_vol):
            cond_uptrend = (ema20 > ema50) and (close >= ema50 * 0.99)
            dist_to_ema20 = abs(low - ema20) / ema20
            dist_to_ema50 = abs(low - ema50) / ema50
            cond_retrace = (dist_to_ema20 <= 0.025) or (dist_to_ema50 <= 0.025)
            cond_rsi_recover = (42.0 <= rsi <= 62.0) and (rsi > prev_rsi)
            cond_reversal_candle = (close > open_p) and (close > float(prev["close"]))
            cond_vol = rel_vol >= 0.90

            if cond_uptrend and cond_retrace and cond_rsi_recover and cond_reversal_candle and cond_vol:
                matched.append(strat_c_name)
                details[strat_c_name] = [
                    f"Pullback to dynamic support (Low ₹{low:.2f} tested EMA20 ₹{ema20:.2f} / EMA50 ₹{ema50:.2f})",
                    f"Bullish reversal candle with RSI hooking up ({prev_rsi:.1f} → {rsi:.1f})",
                    f"Volume confirmation ({rel_vol:.2f}x 20D avg) in established uptrend",
                ]

    # -------------------------------------------------------------------------
    # Strategy D: Early Momentum
    # - RSI improving (RSI > prev RSI and between 48 and 62)
    # - MACD histogram turning positive or rising sharply
    # - Price recovering above EMA 20
    # - Relative volume increasing (rel_vol > prev_rel_vol and rel_vol >= 1.1)
    # - No major technical resistance immediately overhead (room of >= 2.5% to 20d resistance or fresh breakout)
    # -------------------------------------------------------------------------
    strat_d_name = "Strategy D: Early Momentum"
    if enabled_strategies is None or strat_d_name in enabled_strategies:
        if valid(ema20, rsi, prev_rsi, macd_hist, prev_macd_hist, rel_vol, prev_rel_vol, res20):
            cond_rsi_imp = (rsi > prev_rsi) and (48.0 <= rsi <= 64.0)
            cond_macd_turn = (macd_hist > prev_macd_hist) and (macd_hist > 0 or prev_macd_hist < 0)
            cond_ema20_rec = (close > ema20) and (float(prev["close"]) <= float(prev.get("ema_20", close)) * 1.015)
            cond_vol_inc = (rel_vol >= 1.1) and (rel_vol >= prev_rel_vol)
            room_to_res = ((res20 - close) / close) * 100.0 if res20 > close else 5.0
            cond_no_overhead = (room_to_res >= 2.5) or (close >= res20)

            if cond_rsi_imp and cond_macd_turn and cond_ema20_rec and cond_vol_inc and cond_no_overhead:
                matched.append(strat_d_name)
                details[strat_d_name] = [
                    f"Price reclaimed EMA20 (₹{ema20:.2f}) with rising RSI ({prev_rsi:.1f} → {rsi:.1f})",
                    f"MACD histogram Inflection ({prev_macd_hist:.2f} → {macd_hist:.2f})",
                    f"Expanding relative volume ({rel_vol:.2f}x vs prior {prev_rel_vol:.2f}x) with clear overhead room",
                ]

    # Primary category assignment
    if strat_a_name in matched:
        primary_cat = "Momentum Breakout"
    elif strat_b_name in matched:
        primary_cat = "Strong Bullish"
    elif strat_c_name in matched:
        primary_cat = "Pullback Opportunity"
    elif strat_d_name in matched:
        primary_cat = "Early Momentum"
    else:
        primary_cat = "Watchlist"

    return {
        "matched": matched,
        "details": details,
        "primary_category": primary_cat,
    }
