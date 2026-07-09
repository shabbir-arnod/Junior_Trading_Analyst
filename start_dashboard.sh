#!/usr/bin/env bash
# One-click launcher for the Junior Trading Analyst dashboard (Mac/Linux).
# First run: installs dependencies. Then opens the app in your browser.
set -e
cd "$(dirname "$0")"

if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "First-time setup: installing dependencies (this can take a minute)..."
    python3 -m pip install -r requirements.txt
fi

echo "Starting the dashboard... your browser should open automatically."
python3 -m streamlit run app.py
