"""
Stock Scoring, Ranking & Entry/Stop-Loss/Target Calculator Engine for TradePilot NSE.
Implements a transparent 100-point scoring model across 6 categories:
- Trend Strength (20 pts)
- Momentum (20 pts)
- Volume Confirmation (15 pts)
- Breakout Potential (15 pts)
- Fundamental Strength (15 pts)
- Risk/Reward Suitability (15 pts)

Uses normalized available weights when fundamental metrics are missing and never assigns artificial high scores.
"""
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from config import SCORING_WEIGHTS, RISK_CONFIG
from analysis.strategies import evaluate_strategies_on_bar
from utils.helpers import now_ist


def _is_num(val: Any) -> bool:
    if val is None:
        return False
    try:
        return not np.isnan(float(val))
    except (ValueError, TypeError):
        return False


def calculate_entry_sl_targets(
    close: float,
    atr: Optional[float],
    ema20: Optional[float],
    support20: Optional[float],
    resistance20: Optional[float],
    horizon: str = "1-2 Weeks",
) -> Dict[str, Any]:
    """
    Calculates suggested entry zone, ATR + swing support blended Stop-Loss, and Targets 1, 2, 3.
    Clearly documents the methodology used.
    """
    atr_val = float(atr) if (_is_num(atr) and float(atr) > 0) else (close * 0.02)

    if horizon == "3-5 Days":
        atr_mult = RISK_CONFIG.atr_stop_multiplier_short
    elif horizon == "2-6 Weeks":
        atr_mult = RISK_CONFIG.atr_stop_multiplier_swing
    else:
        atr_mult = RISK_CONFIG.atr_stop_multiplier_medium

    # Entry Zone: slight pullback buffer (-0.4% to +0.5% around current close)
    entry_low = round(close - (0.25 * atr_val), 2)
    entry_high = round(close + (0.15 * atr_val), 2)
    mid_entry = close

    atr_stop = close - (atr_mult * atr_val)
    if _is_num(support20) and float(support20) < close:
        # Place stop slightly below 20-day support or ATR stop, whichever provides tighter structural invalidation
        swing_stop = float(support20) - (0.35 * atr_val)
        # Ensure stop is at least 1.0 ATR away so normal noise doesn't prematurely stop out
        min_distance_stop = close - (1.1 * atr_val)
        raw_stop = min(max(atr_stop, swing_stop), min_distance_stop)
        stop_method = f"Blended ATR({atr_mult}x = ₹{atr_stop:.2f}) & 20D Support (₹{float(support20):.2f})"
    else:
        raw_stop = atr_stop
        stop_method = f"Volatility-adjusted {atr_mult}x ATR(14) below close"

    stop_loss = round(max(raw_stop, close * 0.85), 2)
    risk_per_share = round(max(mid_entry - stop_loss, close * 0.01), 2)

    # Targets based on R-multiples and overhead resistance structure
    t1_r = mid_entry + (1.5 * risk_per_share)
    t2_r = mid_entry + (2.5 * risk_per_share)
    t3_r = mid_entry + (3.5 * risk_per_share)

    if _is_num(resistance20) and float(resistance20) > (close + 1.1 * risk_per_share):
        res_val = float(resistance20)
        # If 20d resistance offers > 1.8R, anchor Target 1 near resistance and T2/T3 at R-extensions
        if res_val <= t2_r:
            target_1 = round(max(t1_r, res_val * 0.995), 2)
            target_2 = round(max(t2_r, target_1 + risk_per_share), 2)
            target_3 = round(max(t3_r, target_2 + risk_per_share), 2)
        else:
            target_1 = round(t1_r, 2)
            target_2 = round(t2_r, 2)
            target_3 = round(t3_r, 2)
    else:
        target_1 = round(t1_r, 2)
        target_2 = round(t2_r, 2)
        target_3 = round(t3_r, 2)

    reward_t2 = round(target_2 - mid_entry, 2)
    rr_ratio = round(reward_t2 / risk_per_share, 2) if risk_per_share > 0 else 0.0
    upside_pct = round(((target_2 - mid_entry) / mid_entry) * 100.0, 2)
    downside_pct = round(((mid_entry - stop_loss) / mid_entry) * 100.0, 2)

    methodology = (
        f"Entry Zone: ₹{entry_low:.2f}–₹{entry_high:.2f} (Close ± ATR buffer) | "
        f"Stop-Loss: ₹{stop_loss:.2f} via {stop_method} | "
        f"Targets: T1 ₹{target_1:.2f} (1.5R), T2 ₹{target_2:.2f} (2.5R primary), T3 ₹{target_3:.2f} (3.5R extension)."
    )

    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "target_3": target_3,
        "risk_per_share": risk_per_share,
        "reward_per_share_t2": reward_t2,
        "risk_reward_ratio": rr_ratio,
        "upside_pct": upside_pct,
        "downside_pct": downside_pct,
        "price_methodology": methodology,
    }


def score_and_evaluate_stock(
    symbol: str,
    enriched_df: pd.DataFrame,
    fundamental_row: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    horizon: str = "1-2 Weeks",
    enabled_strategies: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Computes the 100-point breakdown, strategy matches, entry/SL/targets, and BUY WATCH / HOLD WATCH / AVOID signal.
    """
    if enriched_df is None or enriched_df.empty:
        return None

    w = weights or SCORING_WEIGHTS.as_dict()
    last = enriched_df.iloc[-1]
    prev = enriched_df.iloc[-2] if len(enriched_df) >= 2 else last

    close = float(last["close"])
    daily_pct = float(last["daily_pct_change"]) if _is_num(last.get("daily_pct_change")) else 0.0

    ema20 = last.get("ema_20")
    ema50 = last.get("ema_50")
    ema200 = last.get("ema_200")
    adx = last.get("adx_14")
    plus_di = last.get("plus_di")
    minus_di = last.get("minus_di")
    st_dir = last.get("supertrend_direction")
    rsi = last.get("rsi_14")
    macd = last.get("macd")
    macd_sig = last.get("macd_signal")
    macd_hist = last.get("macd_hist")
    prev_macd_hist = prev.get("macd_hist")
    roc = last.get("roc_12")
    rel_vol = last.get("relative_volume")
    obv = last.get("obv")
    atr = last.get("atr_14")
    sup20 = last.get("support_20d")
    res20 = last.get("resistance_20d")
    high52 = last.get("high_52w")

    reasons: List[str] = []
    warnings: List[str] = []

    # -------------------------------------------------------------------------
    # 1. Trend Strength Score (0 - 100 raw, weighted by w['trend_strength'])
    # -------------------------------------------------------------------------
    trend_pts = 0.0
    if _is_num(ema20) and close > float(ema20):
        trend_pts += 20.0
    if _is_num(ema50) and close > float(ema50):
        trend_pts += 20.0
    if _is_num(ema200) and close > float(ema200):
        trend_pts += 20.0
    elif not _is_num(ema200):
        warnings.append("EMA 200 unavailable (<200 bars of history)")

    if _is_num(ema20) and _is_num(ema50) and float(ema20) > float(ema50):
        trend_pts += 15.0
        reasons.append("Bullish EMA20 > EMA50 alignment")
    if _is_num(adx):
        if float(adx) >= 25.0 and _is_num(plus_di) and _is_num(minus_di) and float(plus_di) > float(minus_di):
            trend_pts += 15.0
            reasons.append(f"Strong directional trend (ADX {float(adx):.1f}, +DI > -DI)")
        elif float(adx) >= 18.0 and _is_num(plus_di) and _is_num(minus_di) and float(plus_di) > float(minus_di):
            trend_pts += 10.0
    if st_dir == 1:
        trend_pts += 10.0

    # -------------------------------------------------------------------------
    # 2. Momentum Score (0 - 100 raw, weighted by w['momentum'])
    # -------------------------------------------------------------------------
    mom_pts = 0.0
    if _is_num(rsi):
        r_val = float(rsi)
        if 54.0 <= r_val <= 68.0:
            mom_pts += 40.0
            reasons.append(f"Constructive RSI momentum ({r_val:.1f})")
        elif 48.0 <= r_val < 54.0 or 68.0 < r_val <= 74.0:
            mom_pts += 28.0
        elif r_val > 74.0:
            mom_pts += 15.0
            warnings.append(f"RSI overbought territory ({r_val:.1f})")
        elif r_val < 40.0:
            mom_pts += 5.0

    if _is_num(macd) and _is_num(macd_sig) and _is_num(macd_hist):
        if float(macd) > float(macd_sig) and float(macd_hist) > 0:
            mom_pts += 35.0
            if _is_num(prev_macd_hist) and float(macd_hist) > float(prev_macd_hist):
                mom_pts += 10.0
                reasons.append("Expanding positive MACD histogram")
        elif _is_num(prev_macd_hist) and float(macd_hist) > float(prev_macd_hist):
            mom_pts += 18.0

    if _is_num(roc) and float(roc) > 2.0:
        mom_pts += 15.0

    mom_pts = min(mom_pts, 100.0)

    # -------------------------------------------------------------------------
    # 3. Volume Confirmation Score (0 - 100 raw, weighted by w['volume_confirmation'])
    # -------------------------------------------------------------------------
    vol_pts = 0.0
    if _is_num(rel_vol):
        rv = float(rel_vol)
        if rv >= 1.8 and daily_pct > 0:
            vol_pts += 75.0
            reasons.append(f"High institutional volume surge ({rv:.2f}x 20D avg)")
        elif rv >= 1.3 and daily_pct > 0:
            vol_pts += 60.0
            reasons.append(f"Above-average volume accumulation ({rv:.2f}x)")
        elif rv >= 1.0 and daily_pct >= 0:
            vol_pts += 45.0
        elif rv >= 0.8:
            vol_pts += 30.0
        else:
            vol_pts += 15.0

    # OBV 10-day slope check
    if len(enriched_df) >= 10 and _is_num(obv):
        obv_10_ago = enriched_df.iloc[-10].get("obv")
        if _is_num(obv_10_ago) and float(obv) > float(obv_10_ago):
            vol_pts += 25.0

    vol_pts = min(vol_pts, 100.0)

    # -------------------------------------------------------------------------
    # 4. Breakout Potential Score (0 - 100 raw, weighted by w['breakout_potential'])
    # -------------------------------------------------------------------------
    brk_pts = 0.0
    if _is_num(res20) and float(res20) > 0:
        r20 = float(res20)
        if close >= r20:
            brk_pts += 70.0
            reasons.append(f"Price broke above 20-day high resistance (₹{r20:.2f})")
        elif close >= r20 * 0.98:
            brk_pts += 55.0
            reasons.append(f"Within 2% of 20-day breakout level (₹{r20:.2f})")
        elif close >= r20 * 0.95:
            brk_pts += 35.0
        else:
            brk_pts += 15.0

    if _is_num(high52) and float(high52) > 0:
        if close >= float(high52) * 0.95:
            brk_pts += 30.0
            reasons.append("Trading near 52-week high strength zone")
        elif close >= float(high52) * 0.85:
            brk_pts += 15.0

    brk_pts = min(brk_pts, 100.0)

    # -------------------------------------------------------------------------
    # 5. Fundamental Strength Score (0 - 100 raw, weighted by w['fundamental_strength'])
    # -------------------------------------------------------------------------
    fund_raw = fundamental_row.get("fundamental_raw_score") if fundamental_row else None
    has_fundamentals = _is_num(fund_raw)
    if has_fundamentals:
        fund_pts = float(fund_raw)
        f_class = fundamental_row.get("fundamental_class", "Average Fundamentals")
        if fund_pts >= 70.0:
            reasons.append(f"Strong fundamentals ({fund_pts:.0f}/100)")
        elif fund_pts < 45.0:
            warnings.append(f"Weak fundamental score ({fund_pts:.0f}/100)")
    else:
        fund_pts = 0.0
        warnings.append("Fundamental metrics unavailable; overall score normalized across available categories")

    # -------------------------------------------------------------------------
    # 6. Entry / Stop-Loss / Target & Risk/Reward Score (0 - 100 raw)
    # -------------------------------------------------------------------------
    levels = calculate_entry_sl_targets(
        close=close,
        atr=atr,
        ema20=ema20,
        support20=sup20,
        resistance20=res20,
        horizon=horizon,
    )
    rr = levels["risk_reward_ratio"]
    downside_pct = levels["downside_pct"]

    rr_pts = 0.0
    if rr >= 3.0:
        rr_pts += 70.0
    elif rr >= 2.2:
        rr_pts += 55.0
    elif rr >= 1.8:
        rr_pts += 35.0
    else:
        rr_pts += 15.0

    # Reward controlled downside risk (1.2% to 4.5% stop distance is ideal for short-term NSE swing)
    if 1.0 <= downside_pct <= 4.5:
        rr_pts += 30.0
    elif downside_pct <= 6.5:
        rr_pts += 15.0
    else:
        warnings.append(f"Wide volatility stop-loss ({downside_pct:.1f}% risk distance)")

    rr_pts = min(rr_pts, 100.0)

    # -------------------------------------------------------------------------
    # Weighted Normalization (No artificial scores for missing data)
    # -------------------------------------------------------------------------
    cat_trend = round((trend_pts / 100.0) * w["trend_strength"], 2)
    cat_mom = round((mom_pts / 100.0) * w["momentum"], 2)
    cat_vol = round((vol_pts / 100.0) * w["volume_confirmation"], 2)
    cat_brk = round((brk_pts / 100.0) * w["breakout_potential"], 2)
    cat_fund = round((fund_pts / 100.0) * w["fundamental_strength"], 2) if has_fundamentals else 0.0
    cat_rr = round((rr_pts / 100.0) * w["risk_reward_suitability"], 2)

    total_possible_weight = (
        w["trend_strength"]
        + w["momentum"]
        + w["volume_confirmation"]
        + w["breakout_potential"]
        + (w["fundamental_strength"] if has_fundamentals else 0.0)
        + w["risk_reward_suitability"]
    )
    earned_weight = cat_trend + cat_mom + cat_vol + cat_brk + cat_fund + cat_rr
    overall_score = round((earned_weight / total_possible_weight) * 100.0, 2) if total_possible_weight > 0 else 0.0

    # Data coverage calculation
    total_check_items = 6
    avail_items = 5 + (1 if has_fundamentals else 0)
    if not _is_num(ema200):
        avail_items -= 0.5
    data_coverage_pct = round((avail_items / total_check_items) * 100.0, 1)

    # Evaluate screening strategies
    strat_eval = evaluate_strategies_on_bar(enriched_df, idx=-1, enabled_strategies=enabled_strategies)
    matched_strats = strat_eval["matched"]
    primary_cat = strat_eval["primary_category"]

    # Determine Signal (BUY WATCH, HOLD WATCH, AVOID)
    if overall_score >= 68.0 and len(matched_strats) >= 1 and rr >= 2.0:
        signal = "BUY WATCH"
        if primary_cat == "Watchlist":
            primary_cat = "Strong Bullish"
    elif overall_score >= 52.0 or len(matched_strats) >= 1:
        signal = "HOLD WATCH"
    else:
        signal = "AVOID"
        primary_cat = "Avoid"

    if not reasons:
        if signal == "AVOID":
            reasons.append("Weak trend alignment and insufficient momentum/volume confirmation")
        else:
            reasons.append("Neutral consolidation; awaiting stronger volume or breakout trigger")

    return {
        "symbol": symbol,
        "trade_date": str(last["trade_date"]),
        "computed_at": now_ist().isoformat(),
        "close_price": round(close, 2),
        "daily_pct_change": round(daily_pct, 2),
        "trend_score": cat_trend,
        "momentum_score": cat_mom,
        "volume_score": cat_vol,
        "breakout_score": cat_brk,
        "fundamental_score": cat_fund,
        "risk_reward_score": cat_rr,
        "overall_score": overall_score,
        "data_coverage_pct": data_coverage_pct,
        "signal": signal,
        "opportunity_category": primary_cat,
        "matched_strategies": ", ".join(matched_strats) if matched_strats else "None",
        "score_reasons": " | ".join(reasons[:5]),
        "missing_data_warnings": " | ".join(warnings) if warnings else "Complete",
        **levels,
    }
