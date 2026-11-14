"""
Configuration module for TradePilot NSE.
Loads settings from environment variables (.env) with sensible defaults for NSE short-term trading analysis.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data_store"
EXPORTS_DIR = BASE_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
ASSETS_DIR = BASE_DIR / "assets"

for directory in (DATA_DIR, EXPORTS_DIR, LOGS_DIR, ASSETS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("TRADEPILOT_DB_PATH", str(DATA_DIR / "tradepilot_nse.db")))


@dataclass
class ScoringWeights:
    trend_strength: float = 20.0
    momentum: float = 20.0
    volume_confirmation: float = 15.0
    breakout_potential: float = 15.0
    fundamental_strength: float = 15.0
    risk_reward_suitability: float = 15.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "trend_strength": self.trend_strength,
            "momentum": self.momentum,
            "volume_confirmation": self.volume_confirmation,
            "breakout_potential": self.breakout_potential,
            "fundamental_strength": self.fundamental_strength,
            "risk_reward_suitability": self.risk_reward_suitability,
        }


@dataclass
class ScreenerDefaults:
    trading_horizon: str = "1-2 Weeks"  # Options: "3-5 Days", "1-2 Weeks", "2-6 Weeks"
    min_overall_score: float = 60.0
    min_avg_volume_20d: int = 150_000
    min_daily_turnover_cr: float = 5.0  # Minimum daily traded value in Crores INR
    rsi_min: float = 40.0
    rsi_max: float = 75.0
    adx_min: float = 18.0
    min_relative_volume: float = 1.0
    min_risk_reward: float = 2.0
    preferred_risk_reward: float = 3.0
    market_cap_categories: List[str] = field(default_factory=lambda: ["Large Cap", "Mid Cap", "Small Cap"])
    enabled_strategies: List[str] = field(
        default_factory=lambda: [
            "Strategy A: Momentum Breakout",
            "Strategy B: Trend-Following",
            "Strategy C: Pullback Entry",
            "Strategy D: Early Momentum",
        ]
    )


@dataclass
class RiskConfig:
    default_risk_pct_per_trade: float = 1.0  # 1% of capital per trade
    max_open_positions: int = 8
    max_portfolio_heat_pct: float = 6.0  # Max total portfolio risk across all open trades
    max_single_position_allocation_pct: float = 20.0  # Max 20% capital in one stock
    atr_stop_multiplier_short: float = 1.5  # 3-5 days
    atr_stop_multiplier_medium: float = 2.0  # 1-2 weeks
    atr_stop_multiplier_swing: float = 2.5  # 2-6 weeks


@dataclass
class BacktestConfig:
    default_initial_capital: float = 100_000.0
    brokerage_and_taxes_pct: float = 0.18  # Approx STT + Exchange + GST + Stamp Duty round-trip %
    slippage_pct: float = 0.10  # 0.10% slippage per side
    max_holding_days: int = 15


@dataclass
class MarketDataConfig:
    provider: str = os.getenv("TRADEPILOT_DATA_PROVIDER", "yfinance")  # 'yfinance', 'nse_bhavcopy', 'kite', 'upstox'
    default_history_years: int = int(os.getenv("TRADEPILOT_HISTORY_YEARS", "2"))
    stale_data_threshold_hours: int = 28
    market_close_hour_ist: int = 15
    market_close_minute_ist: int = 45
    request_timeout_sec: int = 15
    batch_size: int = 15
    paid_api_key: str = os.getenv("TRADEPILOT_API_KEY", "")
    paid_api_secret: str = os.getenv("TRADEPILOT_API_SECRET", "")


SCORING_WEIGHTS = ScoringWeights()
SCREENER_DEFAULTS = ScreenerDefaults()
RISK_CONFIG = RiskConfig()
BACKTEST_CONFIG = BacktestConfig()
MARKET_DATA_CONFIG = MarketDataConfig()

DISCLAIMER_TEXT = (
    "DISCLAIMER: TradePilot NSE is a quantitative stock screening and decision-support research tool. "
    "All technical indicators, fundamental classifications, scores, entry zones, stop-losses, targets, "
    "and backtest results are analytical estimates based on historical data and do NOT guarantee future "
    "profits or execution prices. Financial markets carry substantial risk of loss."
)
