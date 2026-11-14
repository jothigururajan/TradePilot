# TradePilot NSE — Short-Term NSE Stock Trading Analysis Platform

**TradePilot NSE** is a modular, local-first Python & Streamlit web application designed for systematic short-term technical, fundamental, volume, and risk/reward analysis of stocks listed on the **National Stock Exchange of India (NSE)**.

> **Important Disclaimer:** TradePilot NSE is a quantitative stock screening and decision-support research tool. It does **not** guarantee profits or assured execution prices. All technical indicators, fundamental classifications, 100-point scores, entry zones, stop-losses, targets, and historical backtests are analytical estimates based on historical data.

---

## 1. System Architecture & Project Structure

```text
TradePilot_NSE/
│
├── app.py                              # Main Streamlit multi-page web application (http://localhost:8501)
├── config.py                           # Centralized configuration, 100-pt weights, risk & backtest defaults
├── eod_auto_update.py                  # Automated End-of-Day data sync, screening & CSV/XLSX export script
├── run_tradepilot.bat                  # One-click Windows launcher (auto-creates venv & launches browser)
├── schedule_eod_task_windows.bat       # One-click Windows Task Scheduler registration (Mon-Fri 16:15 IST)
├── requirements.txt                    # Python package dependencies
├── .env.example                        # Sample environment configuration for API keys & provider selection
├── README.md                           # Complete setup, troubleshooting & cloud migration guide
│
├── data/
│   ├── __init__.py
│   ├── database.py                     # SQLite engine (WAL mode) managing all 10 normalized tables
│   ├── market_data.py                  # Pluggable data provider (YahooFinance .NS, Local CSV, Paid Broker API)
│   └── stock_universe.py               # Default NSE liquid universe (Large, Mid, Small cap) + Nifty indices
│
├── analysis/
│   ├── __init__.py
│   ├── indicators.py                   # Trend, Momentum, Volatility & Volume indicator calculation engine
│   ├── fundamental.py                  # 14-metric fundamental evaluator with missing-data normalization
│   ├── strategies.py                   # 4 configurable strategies (Breakout, Trend, Pullback, Early Momentum)
│   ├── scoring.py                      # Transparent 100-point scoring & ATR/Support Entry/SL/Target engine
│   ├── risk_management.py              # Position-sizing & portfolio heat/concentration risk calculator
│   ├── backtesting.py                  # Event-driven backtester (next-bar open execution, STT/slippage, Nifty alpha)
│   └── pipeline.py                     # End-to-end universe screening orchestrator
│
├── dashboard/
│   ├── __init__.py
│   ├── overview.py                     # Page 1: NSE Market Overview, Nifty 50 / Bank Regime & Top Setups
│   ├── screener.py                     # Page 2: Interactive Stock Screener with filters, sorting & CSV/XLSX export
│   ├── stock_detail.py                 # Page 3: Multi-panel Candlestick/EMA/RSI/MACD chart & Position Calculator
│   ├── opportunities.py                # Page 4: Categorized Opportunities (Strong Bullish, Breakout, Pullback, etc.)
│   ├── portfolio.py                    # Page 5: Watchlist, Open Paper Portfolio & Realized Trade History
│   ├── backtesting_page.py             # Page 6: Interactive Historical Strategy Backtesting UI
│   └── settings_page.py                # Page 7: Custom Horizons, Thresholds, 100-pt Weights & Stock Universe
│
├── utils/
│   ├── __init__.py
│   ├── helpers.py                      # Indian Rupee (₹ / Cr) formatting, IST time & data freshness evaluators
│   └── logging_config.py               # Rotating file and console logger (`logs/tradepilot_nse.log`)
│
├── tests/
│   ├── __init__.py
│   └── test_core.py                    # Automated pytest suite verifying indicators, scoring, risk & SQLite CRUD
│
├── data_store/                         # Local SQLite database (`tradepilot_nse.db`) and optional CSV imports
├── exports/                            # Daily automated CSV and Excel screening exports
└── logs/                               # Application and EOD sync logs
```

---

## 2. Step-by-Step Windows Installation Instructions (ASUS Vivobook / Windows 11)

### Prerequisites
- **Windows 10 or Windows 11**
- **Python 3.10, 3.11, or 3.12** installed from [python.org](https://www.python.org/downloads/windows/).
  - *Important:* During Python installation, check the box **"Add python.exe to PATH"**.

### Option A: One-Click Windows Launch (Recommended)
1. Extract `TradePilot_NSE.zip` to a folder on your laptop (for example, `C:\TradePilot_NSE\`).
2. Double-click **`run_tradepilot.bat`**.
3. On the first run, the launcher automatically:
   - Creates an isolated Python virtual environment (`venv\`).
   - Installs all required libraries from `requirements.txt`.
   - Initializes the SQLite database (`data_store/tradepilot_nse.db`) with all 10 tables and seeds the NSE stock universe.
   - Opens your default web browser to **`http://localhost:8501`**.
4. In the left sidebar of the dashboard, click **⚡ Smart Sync** (or **🔁 Force Refresh** on your very first run) to download 2 years of daily NSE OHLCV history and fundamental metrics from Yahoo Finance (`.NS`) and compute all indicators and rankings.

### Option B: Manual Command Prompt / PowerShell Setup
```cmd
cd C:\TradePilot_NSE
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

### Option C: Automated End-of-Day Windows Task Scheduler Setup
To automatically refresh NSE data and run the daily screener every weekday at **16:15 IST** (after NSE market close at 15:30 IST):
1. Right-click **`schedule_eod_task_windows.bat`** and select **Run as administrator**.
2. Windows Task Scheduler will register the task `TradePilot_NSE_EOD_Sync` to execute `eod_auto_update.py` every Monday–Friday at 16:15 and save dated CSV/Excel reports in `exports/`.

---

## 3. Running Automated Tests

To verify all technical indicator calculations, missing-data normalization, entry/stop-loss/target formulas, position sizing, and SQLite CRUD operations:

```cmd
venv\Scripts\activate
pytest tests/test_core.py -v
```

---

## 4. Free Market Data Limitations & Paid Broker API Upgrade Path

### Free Yahoo Finance (`yfinance`) Limitations
- **End-of-Day / Delayed Feed:** Free `.NS` data is ideal for after-market-close short-term swing analysis (3–5 days to 2–6 weeks), but intraday quotes during market hours may be delayed by up to 15 minutes.
- **Fundamental Coverage Gaps:** Free feeds occasionally omit Indian-specific ownership fields such as **Promoter Pledging %** or standalone ROCE. TradePilot NSE explicitly flags unavailable fields without penalizing the stock, normalizing the 100-point score across verified categories.
- **Offline / Bhavcopy CSV Fallback:** You can also place daily OHLCV CSV files named `<SYMBOL>.csv` inside `data_store/csv_import/` and set `TRADEPILOT_DATA_PROVIDER=local_csv` in `.env`.

### Future Cloud Deployment & Paid API Migration (Phase 4)
1. **Paid Broker API Integration:** Implement `fetch_ohlcv` in `PaidBrokerAPIProvider` inside `data/market_data.py` using Zerodha Kite Connect (`kiteconnect`), Upstox API v2, or TrueData, storing `TRADEPILOT_API_KEY` and `TRADEPILOT_API_SECRET` in `.env`.
2. **Database Migration to PostgreSQL / Supabase:** Replace `sqlite3.connect` in `DatabaseManager.get_connection()` (`data/database.py`) with a SQLAlchemy / PostgreSQL connection URI while keeping all analysis and dashboard modules unchanged.
3. **Cloud Hosting:** Deploy the repository directly to **Streamlit Community Cloud**, **Render**, **Railway**, or an **AWS EC2 / DigitalOcean Docker container** (`streamlit run app.py --server.port=8501 --server.address=0.0.0.0`), and enable Streamlit native authentication (`st.login`) for multi-user access.

---

## 5. Troubleshooting Guide

| Symptom / Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| `'python' is not recognized as an internal or external command` | Python is not added to Windows `PATH` | Re-run the Python installer -> Select **Modify** -> Check **Add Python to environment variables**. |
| Dashboard shows `"No screening results found"` on first launch | Local SQLite DB is initialized empty (zero fabricated data) | Click **⚡ Smart Sync** or **🔁 Force Refresh** in the left sidebar while connected to the internet. |
| Yahoo Finance rate-limit or timeout on a specific ticker | Temporary Yahoo Finance API throttling | Wait 60 seconds and click **⚡ Smart Sync**; already-fetched tickers are cached in SQLite and skipped automatically. |
| Port `8501` is already in use | Another Streamlit instance is running | Close the existing terminal window or run `streamlit run app.py --server.port=8502`. |
