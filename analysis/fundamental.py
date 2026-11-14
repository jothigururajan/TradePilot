"""
Fundamental Analysis Engine for TradePilot NSE.
Evaluates up to 14 fundamental metrics without rejecting stocks when individual metrics are unavailable.
Clearly distinguishes unavailable data from negative financial performance.
"""
from typing import Any, Dict, List, Optional
import numpy as np
from utils.helpers import now_ist


def _is_valid(val: Any) -> bool:
    if val is None:
        return False
    try:
        return not np.isnan(float(val))
    except (ValueError, TypeError):
        return False


def evaluate_fundamentals(symbol: str, raw_metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates available fundamental metrics on a 0-100 normalized scale and classifies into:
    - Strong Fundamentals (Normalized Score >= 70)
    - Average Fundamentals (Normalized Score 45 - 69.9)
    - Weak Fundamentals (Normalized Score < 45)
    - Insufficient Data (if fewer than 3 metrics are available)
    """
    raw = raw_metrics or {}
    points_earned = 0.0
    max_possible_points = 0.0
    notes: List[str] = []
    available_count = 0

    # 1. Revenue Growth YoY (%)
    rev_g = raw.get("revenue_growth_pct")
    if _is_valid(rev_g):
        available_count += 1
        max_possible_points += 10.0
        if rev_g >= 15.0:
            points_earned += 10.0
            notes.append(f"Strong revenue growth ({rev_g:.1f}%)")
        elif rev_g >= 5.0:
            points_earned += 6.5
        elif rev_g >= 0.0:
            points_earned += 3.5
        else:
            notes.append(f"Negative revenue growth ({rev_g:.1f}%)")

    # 2. Profit Growth YoY (%)
    prof_g = raw.get("profit_growth_pct")
    if _is_valid(prof_g):
        available_count += 1
        max_possible_points += 10.0
        if prof_g >= 18.0:
            points_earned += 10.0
            notes.append(f"Healthy profit growth ({prof_g:.1f}%)")
        elif prof_g >= 8.0:
            points_earned += 7.0
        elif prof_g >= 0.0:
            points_earned += 4.0
        else:
            notes.append(f"Earnings contraction ({prof_g:.1f}%)")

    # 3. EPS Growth (%)
    eps_g = raw.get("eps_growth_pct")
    if _is_valid(eps_g):
        available_count += 1
        max_possible_points += 8.0
        if eps_g >= 15.0:
            points_earned += 8.0
        elif eps_g >= 5.0:
            points_earned += 5.0
        elif eps_g >= 0.0:
            points_earned += 2.5

    # 4. Return on Equity - ROE (%)
    roe = raw.get("roe_pct")
    if _is_valid(roe):
        available_count += 1
        max_possible_points += 12.0
        if roe >= 18.0:
            points_earned += 12.0
            notes.append(f"Superior ROE ({roe:.1f}%)")
        elif roe >= 12.0:
            points_earned += 8.5
        elif roe >= 6.0:
            points_earned += 4.5
        else:
            notes.append(f"Low ROE ({roe:.1f}%)")

    # 5. Return on Capital Employed / Assets proxy - ROCE (%)
    roce = raw.get("roce_pct")
    if _is_valid(roce):
        available_count += 1
        max_possible_points += 10.0
        if roce >= 15.0:
            points_earned += 10.0
        elif roce >= 8.0:
            points_earned += 7.0
        elif roce >= 4.0:
            points_earned += 4.0

    # 6. Debt-to-Equity Ratio
    de = raw.get("debt_to_equity")
    if _is_valid(de):
        available_count += 1
        max_possible_points += 10.0
        if de <= 0.3:
            points_earned += 10.0
            notes.append(f"Low leverage (D/E {de:.2f}x)")
        elif de <= 0.8:
            points_earned += 7.5
        elif de <= 1.5:
            points_earned += 4.0
        else:
            notes.append(f"High debt-to-equity ({de:.2f}x)")

    # 7. Current Ratio
    cr = raw.get("current_ratio")
    if _is_valid(cr):
        available_count += 1
        max_possible_points += 6.0
        if cr >= 1.5:
            points_earned += 6.0
        elif cr >= 1.1:
            points_earned += 4.0
        else:
            points_earned += 1.5

    # 8. Operating Profit Margin (%)
    opm = raw.get("operating_margin_pct")
    if _is_valid(opm):
        available_count += 1
        max_possible_points += 8.0
        if opm >= 18.0:
            points_earned += 8.0
        elif opm >= 10.0:
            points_earned += 5.5
        elif opm > 0.0:
            points_earned += 3.0

    # 9. Net Profit Margin (%)
    npm = raw.get("net_margin_pct")
    if _is_valid(npm):
        available_count += 1
        max_possible_points += 8.0
        if npm >= 12.0:
            points_earned += 8.0
        elif npm >= 6.0:
            points_earned += 5.5
        elif npm > 0.0:
            points_earned += 2.5

    # 10. P/E Ratio
    pe = raw.get("pe_ratio")
    if _is_valid(pe):
        available_count += 1
        max_possible_points += 8.0
        if 5.0 <= pe <= 28.0:
            points_earned += 8.0
            notes.append(f"Reasonable valuation (P/E {pe:.1f}x)")
        elif 28.0 < pe <= 50.0:
            points_earned += 5.5
        elif 50.0 < pe <= 85.0:
            points_earned += 3.0
            notes.append(f"Rich P/E valuation ({pe:.1f}x)")
        else:
            points_earned += 1.0

    # 11. P/B Ratio
    pb = raw.get("pb_ratio")
    if _is_valid(pb):
        available_count += 1
        max_possible_points += 4.0
        if 0.5 <= pb <= 4.5:
            points_earned += 4.0
        elif pb <= 10.0:
            points_earned += 2.5
        else:
            points_earned += 1.0

    # 12. Promoter Holding (%)
    prom = raw.get("promoter_holding_pct")
    if _is_valid(prom):
        available_count += 1
        max_possible_points += 4.0
        if prom >= 45.0:
            points_earned += 4.0
        elif prom >= 25.0:
            points_earned += 2.5
        else:
            points_earned += 1.5

    # 13. Promoter Pledging (%)
    pledge = raw.get("promoter_pledging_pct")
    if _is_valid(pledge):
        available_count += 1
        max_possible_points += 4.0
        if pledge <= 2.0:
            points_earned += 4.0
        elif pledge <= 15.0:
            points_earned += 1.5
            notes.append(f"Moderate promoter pledging ({pledge:.1f}%)")
        else:
            notes.append(f"High promoter pledging warning ({pledge:.1f}%)")

    # 14. Institutional Ownership (%)
    inst = raw.get("institutional_holding_pct")
    if _is_valid(inst):
        available_count += 1
        max_possible_points += 4.0
        if inst >= 20.0:
            points_earned += 4.0
            notes.append(f"Solid institutional backing ({inst:.1f}%)")
        elif inst >= 8.0:
            points_earned += 2.5
        else:
            points_earned += 1.0

    if available_count < 3 or max_possible_points == 0:
        norm_score = None
        f_class = "Data Unavailable"
        notes.append("Fundamental metrics unavailable from free data provider; score normalized on technicals.")
    else:
        norm_score = round((points_earned / max_possible_points) * 100.0, 2)
        if norm_score >= 70.0:
            f_class = "Strong Fundamentals"
        elif norm_score >= 45.0:
            f_class = "Average Fundamentals"
        else:
            f_class = "Weak Fundamentals"

    missing_fields = [
        label
        for key, label in [
            ("revenue_growth_pct", "Revenue Growth"),
            ("profit_growth_pct", "Profit Growth"),
            ("roe_pct", "ROE"),
            ("debt_to_equity", "Debt/Equity"),
            ("pe_ratio", "P/E"),
            ("promoter_pledging_pct", "Promoter Pledging"),
        ]
        if not _is_valid(raw.get(key))
    ]
    if missing_fields:
        notes.append(f"Unavailable metrics (not penalized): {', '.join(missing_fields)}")

    return {
        "symbol": symbol,
        "updated_at": now_ist().isoformat(),
        "revenue_growth_pct": raw.get("revenue_growth_pct"),
        "profit_growth_pct": raw.get("profit_growth_pct"),
        "eps_growth_pct": raw.get("eps_growth_pct"),
        "roe_pct": raw.get("roe_pct"),
        "roce_pct": raw.get("roce_pct"),
        "debt_to_equity": raw.get("debt_to_equity"),
        "current_ratio": raw.get("current_ratio"),
        "operating_margin_pct": raw.get("operating_margin_pct"),
        "net_margin_pct": raw.get("net_margin_pct"),
        "pe_ratio": raw.get("pe_ratio"),
        "pb_ratio": raw.get("pb_ratio"),
        "promoter_holding_pct": raw.get("promoter_holding_pct"),
        "promoter_pledging_pct": raw.get("promoter_pledging_pct"),
        "institutional_holding_pct": raw.get("institutional_holding_pct"),
        "market_cap_cr": raw.get("market_cap_cr"),
        "fundamental_class": f_class,
        "fundamental_raw_score": norm_score,
        "metrics_available_count": available_count,
        "notes": " | ".join(notes),
    }
