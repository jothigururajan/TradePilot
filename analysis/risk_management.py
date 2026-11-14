"""
Risk Management & Position Sizing Calculator for TradePilot NSE.
Computes exact share quantity, maximum acceptable monetary loss, capital allocation,
and portfolio-level risk warnings without assuming user capital.
"""
from typing import Any, Dict, List, Optional
import math
from config import RISK_CONFIG


def calculate_position_size(
    total_capital: float,
    risk_pct_per_trade: float,
    entry_price: float,
    stop_loss_price: float,
    target_price: Optional[float] = None,
    current_open_positions: int = 0,
    current_portfolio_risk_inr: float = 0.0,
    max_open_positions: int = RISK_CONFIG.max_open_positions,
) -> Dict[str, Any]:
    """
    Calculates position size and evaluates portfolio-level risk constraints.
    """
    warnings: List[str] = []

    if total_capital <= 0:
        return {"error": "Total trading capital must be greater than ₹0."}
    if risk_pct_per_trade <= 0 or risk_pct_per_trade > 10.0:
        warnings.append(f"Risk per trade ({risk_pct_per_trade:.2f}%) is outside typical 0.5%–2.0% institutional guidelines.")
    if entry_price <= 0 or stop_loss_price <= 0:
        return {"error": "Entry price and Stop-Loss price must be greater than ₹0."}
    if stop_loss_price >= entry_price:
        return {"error": "For a long NSE equity trade, Stop-Loss price must be strictly below Entry price."}

    max_acceptable_loss = total_capital * (risk_pct_per_trade / 100.0)
    risk_per_share = entry_price - stop_loss_price

    raw_qty = math.floor(max_acceptable_loss / risk_per_share)

    # Check single-position capital concentration cap (e.g. max 25% of capital in a single stock)
    max_capital_per_pos = total_capital * (RISK_CONFIG.max_single_position_allocation_pct / 100.0)
    max_qty_by_capital = math.floor(max_capital_per_pos / entry_price)

    recommended_qty = max(0, min(raw_qty, int(total_capital // entry_price)))
    capital_capped_qty = max(0, min(recommended_qty, max_qty_by_capital))

    if raw_qty > int(total_capital // entry_price):
        warnings.append(
            f"Stop-loss is very tight ({((risk_per_share / entry_price) * 100):.2f}%), so risk-based quantity ({raw_qty} shares) "
            f"exceeds 100% of total capital. Capped to {recommended_qty} shares."
        )
    if recommended_qty > max_qty_by_capital and max_qty_by_capital > 0:
        warnings.append(
            f"Position requires {((recommended_qty * entry_price) / total_capital * 100):.1f}% of capital, exceeding the "
            f"{RISK_CONFIG.max_single_position_allocation_pct:.0f}% single-stock concentration guideline ({capital_capped_qty} shares)."
        )

    total_investment = round(recommended_qty * entry_price, 2)
    actual_potential_loss = round(recommended_qty * risk_per_share, 2)

    if target_price and target_price > entry_price:
        reward_per_share = target_price - entry_price
        potential_profit = round(recommended_qty * reward_per_share, 2)
        rr_ratio = round(reward_per_share / risk_per_share, 2)
    else:
        reward_per_share = 0.0
        potential_profit = 0.0
        rr_ratio = 0.0

    # Portfolio-level risk checks
    if current_open_positions >= max_open_positions:
        warnings.append(
            f"Portfolio Limit Reached: You already have {current_open_positions} open positions (configured limit: {max_open_positions})."
        )

    new_total_portfolio_risk = current_portfolio_risk_inr + actual_potential_loss
    portfolio_heat_pct = (new_total_portfolio_risk / total_capital) * 100.0
    if portfolio_heat_pct > RISK_CONFIG.max_portfolio_heat_pct:
        warnings.append(
            f"High Portfolio Heat Warning: Adding this trade brings total open portfolio risk to {portfolio_heat_pct:.2f}% "
            f"(₹{new_total_portfolio_risk:,.2f}), above the {RISK_CONFIG.max_portfolio_heat_pct:.1f}% safety threshold."
        )

    return {
        "total_capital": round(total_capital, 2),
        "risk_pct_per_trade": round(risk_pct_per_trade, 2),
        "max_acceptable_loss": round(max_acceptable_loss, 2),
        "entry_price": round(entry_price, 2),
        "stop_loss_price": round(stop_loss_price, 2),
        "target_price": round(target_price, 2) if target_price else None,
        "risk_per_share": round(risk_per_share, 2),
        "reward_per_share": round(reward_per_share, 2),
        "risk_reward_ratio": rr_ratio,
        "quantity": int(recommended_qty),
        "concentration_capped_quantity": int(capital_capped_qty),
        "total_investment": total_investment,
        "capital_allocation_pct": round((total_investment / total_capital) * 100.0, 2),
        "potential_loss": actual_potential_loss,
        "potential_profit": potential_profit,
        "portfolio_heat_pct": round(portfolio_heat_pct, 2),
        "warnings": warnings,
    }
