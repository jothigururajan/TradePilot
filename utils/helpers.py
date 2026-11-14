"""
Helper functions for formatting Indian Rupees (INR / Lakhs / Crores), dates, and data freshness checks.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def format_inr(value: Optional[float], decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "N/A"
    sign = "-" if val < 0 else ""
    val = abs(val)
    s = f"{val:.{decimals}f}"
    parts = s.split(".")
    integer_part = parts[0]
    decimal_part = "." + parts[1] if len(parts) > 1 and decimals > 0 else ""

    if len(integer_part) > 3:
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_int = ",".join(groups) + "," + last3
    else:
        formatted_int = integer_part
    return f"{sign}₹{formatted_int}{decimal_part}"


def format_pct(value: Optional[float], decimals: int = 2, show_plus: bool = True) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "N/A"
    prefix = "+" if (val > 0 and show_plus) else ""
    return f"{prefix}{val:.{decimals}f}%"


def evaluate_data_freshness(last_date_str: Optional[str]) -> Tuple[str, str]:
    """
    Evaluates whether the latest available OHLCV date is Fresh, Delayed/Weekend, or Stale.
    Returns (status_label, badge_color).
    """
    if not last_date_str:
        return ("UNAVAILABLE", "red")
    try:
        last_dt = pd.to_datetime(last_date_str).date()
        today = now_ist().date()
        delta_days = (today - last_dt).days
        if delta_days <= 1:
            return ("FRESH (EOD)", "green")
        elif delta_days <= 4 and today.weekday() in (5, 6, 0):
            return ("WEEKEND / LAST CLOSE", "green")
        elif delta_days <= 5:
            return (f"DELAYED ({delta_days}d old)", "orange")
        else:
            return (f"STALE ({delta_days}d old)", "red")
    except Exception:
        return ("UNKNOWN", "orange")
