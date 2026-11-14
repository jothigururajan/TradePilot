"""
One-Step Local Folder Updater for TradePilot NSE (Free 24/7 GitHub Actions Automation).
Place inside your TradePilot_NSE folder (next to app.py) and run:
    python apply_github_actions_update.py
"""
import json
from pathlib import Path

PATCH_FILES = json.loads("{\".github/workflows/eod_trial.yml\": \"name: TradePilot NSE - Daily EOD Sync & 1-Month Paper Trial\\n\\non:\\n  schedule:\\n    # 10:45 UTC = 16:15 IST (Monday to Friday after NSE market close)\\n    - cron: \\\"45 10 * * 1-5\\\"\\n  workflow_dispatch:\\n    inputs:\\n      force_refresh:\\n        description: \\\"Force full OHLCV re-download\\\"\\n        required: false\\n        default: \\\"false\\\"\\n        type: boolean\\n\\npermissions:\\n  contents: write\\n\\njobs:\\n  eod-screener-and-trial:\\n    runs-on: ubuntu-latest\\n\\n    steps:\\n      - name: Checkout Private Repository\\n        uses: actions/checkout@v4\\n\\n      - name: Set up Python 3.11\\n        uses: actions/setup-python@v5\\n        with:\\n          python-version: \\\"3.11\\\"\\n          cache: \\\"pip\\\"\\n\\n      - name: Install Dependencies\\n        run: |\\n          python -m pip install --upgrade pip\\n          pip install -r requirements.txt\\n\\n      - name: Run EOD Market Sync, Screener, Paper Trial & Telegram Alert\\n        env:\\n          TRADEPILOT_TELEGRAM_BOT_TOKEN: ${{ secrets.TRADEPILOT_TELEGRAM_BOT_TOKEN }}\\n          TRADEPILOT_TELEGRAM_CHAT_ID: ${{ secrets.TRADEPILOT_TELEGRAM_CHAT_ID }}\\n        run: |\\n          if [ \\\"${{ github.event.inputs.force_refresh }}\\\" = \\\"true\\\" ]; then\\n            python eod_auto_update.py --force\\n          else\\n            python eod_auto_update.py\\n          fi\\n\\n      - name: Save Updated SQLite Database & Exports Back to Repo\\n        run: |\\n          git config user.name \\\"TradePilot Bot\\\"\\n          git config user.email \\\"tradepilot-bot@users.noreply.github.com\\\"\\n          git add data_store/tradepilot_nse.db exports/\\n          if git diff --staged --quiet; then\\n            echo \\\"No database or export changes to commit.\\\"\\n          else\\n            git commit -m \\\"Auto EOD Sync & Paper Trial Update [skip ci]\\\"\\n            git push\\n          fi\\n\", \".gitignore\": \"# Python & Virtual Environment\\nvenv/\\n__pycache__/\\n*.py[cod]\\n*$py.class\\n\\n# Secrets & Local Environment\\n.env\\n\\n# Logs & Temporary Exports\\nlogs/\\n*.log\\n.DS_Store\\nThumbs.db\\n\"}")

def apply_update():
    base_dir = Path(__file__).resolve().parent
    if not (base_dir / "app.py").exists():
        print("[ERROR] Place apply_github_actions_update.py inside your TradePilot_NSE folder (next to app.py).")
        return

    for rel_path, content in PATCH_FILES.items():
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [UPDATED] {rel_path}")

    print("\n[SUCCESS] Added .github/workflows/eod_trial.yml and .gitignore!")

if __name__ == "__main__":
    apply_update()