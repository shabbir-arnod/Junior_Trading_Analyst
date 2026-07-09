@echo off
REM One-click launcher for the Junior Trading Analyst dashboard (Windows).
REM First run: installs dependencies. Then opens the app in your browser.
cd /d "%~dp0"

python -c "import streamlit" 2>NUL
if errorlevel 1 (
    echo First-time setup: installing dependencies, this can take a minute...
    python -m pip install -r requirements.txt
)

echo Starting the dashboard... your browser should open automatically.
python -m streamlit run app.py
pause
