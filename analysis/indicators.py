"""
Technical Analysis Engine for TradePilot NSE.
Computes all required Trend, Momentum, Volatility, and Volume indicators on daily OHLCV DataFrames
using pure vectorized Pandas/NumPy (zero C-compiler dependency on Windows, fully compatible with pandas-ta).
"""
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0).clip(0.0, 100.0)


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist}, index=close.index)


def compute_stoch_rsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> pd.DataFrame:
    rsi = compute_rsi(close, rsi_period)
    rsi_min = rsi.rolling(window=stoch_period, min_periods=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period, min_periods=stoch_period).max()
    denom = (rsi_max - rsi_min).replace(0, np.nan)
    stoch_raw = ((rsi - rsi_min) / denom) * 100.0
    k = stoch_raw.rolling(window=smooth_k, min_periods=1).mean()
    d = k.rolling(window=smooth_d, min_periods=1).mean()
    return pd.DataFrame({"stoch_rsi_k": k, "stoch_rsi_d": d}, index=close.index)


def compute_roc(close: pd.Series, period: int = 12) -> pd.Series:
    prev = close.shift(period)
    return ((close - prev) / prev.replace(0, np.nan)) * 100.0


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = compute_atr(high, low, close, period).replace(0, np.nan)
    plus_dm_series = pd.Series(plus_dm, index=close.index).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    minus_dm_series = pd.Series(minus_dm, index=close.index).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    plus_di = 100.0 * (plus_dm_series / atr)
    minus_di = 100.0 * (minus_dm_series / atr)
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return pd.DataFrame({"adx_14": adx, "plus_di": plus_di, "minus_di": minus_di}, index=close.index)


def compute_supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(close)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    supertrend = np.zeros(n)
    direction = np.ones(n, dtype=int)  # 1 = Bullish, -1 = Bearish

    close_arr = close.values
    bu_arr = basic_upper.values
    bl_arr = basic_lower.values

    for i in range(n):
        if i == 0 or np.isnan(bu_arr[i]) or np.isnan(bl_arr[i]):
            final_upper[i] = bu_arr[i] if not np.isnan(bu_arr[i]) else close_arr[i]
            final_lower[i] = bl_arr[i] if not np.isnan(bl_arr[i]) else close_arr[i]
            supertrend[i] = final_lower[i]
            direction[i] = 1
            continue

        if bu_arr[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1]:
            final_upper[i] = bu_arr[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if bl_arr[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1]:
            final_lower[i] = bl_arr[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if direction[i - 1] == -1 and close_arr[i] > final_upper[i - 1]:
            direction[i] = 1
        elif direction[i - 1] == 1 and close_arr[i] < final_lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        supertrend[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

    return pd.DataFrame(
        {"supertrend": supertrend, "supertrend_direction": direction},
        index=close.index,
    )


def compute_bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = compute_sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + (num_std * std)
    lower = mid - (num_std * std)
    width_pct = ((upper - lower) / mid.replace(0, np.nan)) * 100.0
    return pd.DataFrame(
        {"bb_upper": upper, "bb_middle": mid, "bb_lower": lower, "bb_width_pct": width_pct},
        index=close.index,
    )


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a historical OHLCV DataFrame (columns: trade_date, open, high, low, close, volume)
    and returns the enriched DataFrame with all Trend, Momentum, Volatility, and Volume indicators.
    """
    if df is None or df.empty or len(df) < 25:
        return pd.DataFrame()

    out = df.copy().sort_values("trade_date").reset_index(drop=True)
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    volume = out["volume"].astype(float)

    # 1. Trend Indicators
    out["ema_9"] = compute_ema(close, 9)
    out["ema_20"] = compute_ema(close, 20)
    out["ema_50"] = compute_ema(close, 50)
    out["ema_100"] = compute_ema(close, 100)
    out["ema_200"] = compute_ema(close, 200)

    out["sma_20"] = compute_sma(close, 20)
    out["sma_50"] = compute_sma(close, 50)
    out["sma_200"] = compute_sma(close, 200)

    adx_df = compute_adx(high, low, close, 14)
    out["adx_14"] = adx_df["adx_14"]
    out["plus_di"] = adx_df["plus_di"]
    out["minus_di"] = adx_df["minus_di"]

    st_df = compute_supertrend(high, low, close, 10, 3.0)
    out["supertrend"] = st_df["supertrend"]
    out["supertrend_direction"] = st_df["supertrend_direction"]

    # 2. Momentum Indicators
    out["rsi_14"] = compute_rsi(close, 14)
    macd_df = compute_macd(close, 12, 26, 9)
    out["macd"] = macd_df["macd"]
    out["macd_signal"] = macd_df["macd_signal"]
    out["macd_hist"] = macd_df["macd_hist"]

    stoch_df = compute_stoch_rsi(close, 14, 14, 3, 3)
    out["stoch_rsi_k"] = stoch_df["stoch_rsi_k"]
    out["stoch_rsi_d"] = stoch_df["stoch_rsi_d"]
    out["roc_12"] = compute_roc(close, 12)

    # 3. Volatility Indicators
    out["atr_14"] = compute_atr(high, low, close, 14)
    bb_df = compute_bollinger_bands(close, 20, 2.0)
    out["bb_upper"] = bb_df["bb_upper"]
    out["bb_middle"] = bb_df["bb_middle"]
    out["bb_lower"] = bb_df["bb_lower"]
    out["bb_width_pct"] = bb_df["bb_width_pct"]

    log_ret = np.log(close / close.shift(1))
    out["hist_volatility_20d"] = log_ret.rolling(window=20, min_periods=15).std() * np.sqrt(252) * 100.0

    # 4. Volume Indicators & Key Levels
    out["vol_sma_20"] = compute_sma(volume, 20)
    out["relative_volume"] = volume / out["vol_sma_20"].replace(0, np.nan)
    out["obv"] = compute_obv(close, volume)
    out["vol_breakout"] = np.where((out["relative_volume"] >= 1.5) & (close > close.shift(1)), 1, 0)

    # Prior 20-day Support & Resistance (shifted by 1 bar to prevent look-ahead in breakout detection)
    out["support_20d"] = low.shift(1).rolling(window=20, min_periods=10).min()
    out["resistance_20d"] = high.shift(1).rolling(window=20, min_periods=10).max()
    out["high_52w"] = high.rolling(window=252, min_periods=30).max()
    out["low_52w"] = low.rolling(window=252, min_periods=30).min()

    return out


def extract_latest_indicator_snapshot(symbol: str, enriched_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if enriched_df is None or enriched_df.empty:
        return None
    last = enriched_df.iloc[-1]

    def clean_val(val: Any) -> Any:
        if val is None or (isinstance(val, (float, np.floating)) and np.isnan(val)):
            return None
        if isinstance(val, (np.integer, int)):
            return int(val)
        if isinstance(val, (np.floating, float)):
            return round(float(val), 4)
        return val

    cols = [
        "trade_date",
        "ema_9",
        "ema_20",
        "ema_50",
        "ema_100",
        "ema_200",
        "sma_20",
        "sma_50",
        "sma_200",
        "adx_14",
        "plus_di",
        "minus_di",
        "supertrend",
        "supertrend_direction",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "stoch_rsi_k",
        "stoch_rsi_d",
        "roc_12",
        "atr_14",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "bb_width_pct",
        "hist_volatility_20d",
        "vol_sma_20",
        "relative_volume",
        "obv",
        "vol_breakout",
        "support_20d",
        "resistance_20d",
        "high_52w",
        "low_52w",
    ]
    snapshot = {"symbol": symbol}
    for c in cols:
        snapshot[c] = clean_val(last.get(c))
    return snapshot
