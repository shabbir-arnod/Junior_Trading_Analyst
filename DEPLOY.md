# Putting your dashboard online (free)

This guide gets your dashboard on the internet with a shareable link like
`https://your-app-name.streamlit.app`, using Streamlit Community Cloud.
It's free, requires no coding, and takes about 5 minutes.

## What you need

- A GitHub account (you already have one — this code lives on GitHub).
- That's it.

## Step-by-step

1. **Open** [share.streamlit.io](https://share.streamlit.io) in your browser.

2. **Sign in with GitHub.** Click "Continue with GitHub" and approve the
   permissions it asks for. If your repository is private, it will ask to
   be granted access to your repositories — approve that too.

3. **Click "Create app"** (top right), then choose
   **"Deploy a public app from GitHub"**.

4. **Fill in the form:**
   - **Repository:** `shabbir-arnod/Junior_Trading_Analyst`
   - **Branch:** `main` (after your pull request is merged — or pick the
     `claude/ai-stock-analyst-agent-nwzutx` branch to try it before merging)
   - **Main file path:** `app.py`
   - **App URL:** pick any available name you like, e.g.
     `junior-trading-analyst`

5. **Click "Deploy".** The first build takes a few minutes while it
   installs everything. Then your dashboard is live at your chosen link.

## Optional: unlock the AI-written analyst notes

The dashboard works immediately with no keys. To enable the AI analyst
notes on the deployed app:

1. Get a free Gemini API key from
   [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (just a
   Google account, no credit card).
2. On your app's page at share.streamlit.io, click the **⋮ menu → Settings
   → Secrets**.
3. Paste this (with your real key) and save:

   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```

4. The app restarts automatically and the AI note toggle lights up.

You can add the other optional keys the same way (`FINNHUB_API_KEY`,
`NEWSAPI_KEY`, `FRED_API_KEY`). **Never** put these keys in the code or
in GitHub — the Secrets box is the safe place for them.

## Optional: real background alerts (even when the app isn't open)

The Alerts tab works immediately inside the app, but a Streamlit Cloud app
only runs while a page is actually open in someone's browser — it can't
notify you in the background on its own. A scheduled GitHub Actions job
(already included: `.github/workflows/alerts.yml`) closes that gap by
checking your alert rules on a timer and posting to a webhook, independent
of whether the app is open.

1. **Create a webhook** — takes about a minute:
   - **Slack**: your workspace → Apps → search "Incoming Webhooks" → Add to
     Slack → pick a channel → copy the Webhook URL.
   - **Discord**: a channel's settings → Integrations → Webhooks → New
     Webhook → copy the Webhook URL.
2. **Add it as a GitHub secret** (not a Streamlit secret — this one's for
   the GitHub Actions job): on your repo page, go to **Settings → Secrets
   and variables → Actions → New repository secret**. Name it
   `ALERT_WEBHOOK_URL` and paste the webhook URL as the value.
3. **Commit real alert rules to `config/alerts.yaml`.** Rules added
   through the deployed app don't persist (same ephemeral-filesystem
   caveat as the Watchlist tab below) — edit `config/alerts.yaml` directly
   on GitHub, or run the app locally and `git push` the file it writes.
4. That's it — the workflow runs on its own schedule (roughly market open
   and close on weekdays) and messages your Slack/Discord channel whenever
   a rule triggers. You can also trigger it manually any time from the
   repo's **Actions** tab → "Check price/signal alerts" → **Run workflow**.

## Things worth knowing

- **Public link**: anyone with the URL can open your app. In the app's
  Settings you can restrict it to only people you invite by email.
- **Watchlist edits don't stick online.** The deployed app runs on a
  temporary computer: stocks you add/remove in the Watchlist tab reset
  whenever the app restarts. To change the watchlist permanently, edit
  `config/watchlist.yaml` in GitHub (open the file, click the pencil icon,
  commit) — the app redeploys automatically.
- **Data hiccups can happen.** Free market-data sources sometimes
  rate-limit cloud servers. If stocks fail to load, wait a minute and
  press "Run analysis" again.
- **Sleeping apps.** If nobody visits for a while, the free tier puts the
  app to sleep; the next visitor sees a "wake up" button and waits ~1
  minute.
- **Updates are automatic.** Every time new code is pushed to the branch
  you deployed, the app updates itself.
