#!/usr/bin/env python3
"""
Stock Drop Alert Bot
Checks if watched stocks dropped more than THRESHOLD% over the last LOOKBACK_HOURS
trading hours (including pre/post market), and sends a Telegram message if they did.
"""

import os
import requests
from datetime import datetime

import yfinance as yf


# ── Configuration ─────────────────────────────────────────────────────────────

# Tickers are read from the TICKERS GitHub Actions Variable (set in GitHub UI).
# Format: comma-separated, e.g. "AAPL,NVDA,TSLA,D05.SI"
# Falls back to the default list below if the variable isn't set.
_tickers_env = os.environ.get("TICKERS", "AAPL,NVDA,TSLA")
TICKERS = [t.strip().upper() for t in _tickers_env.split(",") if t.strip()]

THRESHOLD_PCT  = -3.0  # Alert if a stock drops more than this % (keep negative)
LOOKBACK_HOURS = 6     # How many hourly bars to look back

# ─────────────────────────────────────────────────────────────────────────────


def get_price_change(ticker: str) -> tuple[float | None, float | None, float | None]:
    """
    Fetch hourly bars for `ticker` and return:
        (current_price, price_N_hours_ago, pct_change)
    Returns (None, None, None) on failure.
    """
    try:
        # Fetch 5 days of hourly data including pre/post market bars.
        # 5 days ensures we always have 6+ bars even early in the session.
        df = yf.download(
            ticker,
            period="5d",
            interval="1h",
            progress=False,
            auto_adjust=True,
            prepost=True,     # includes pre-market and after-hours bars
        )

        if df.empty or len(df) < LOOKBACK_HOURS:
            print(f"  {ticker}: not enough data ({len(df)} bars), skipping.")
            return None, None, None

        # .squeeze() handles newer yfinance versions that return a DataFrame
        # instead of a Series for single-ticker downloads.
        close   = df["Close"].squeeze()
        current = float(close.iloc[-1])
        past    = float(close.iloc[-LOOKBACK_HOURS])
        pct     = (current - past) / past * 100

        return current, past, pct

    except Exception as exc:
        print(f"  {ticker}: error fetching data — {exc}")
        return None, None, None


def send_telegram_alert(alerts: list[dict]) -> None:
    """Send a Telegram message via the Bot API for all triggered alerts."""
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    rows = "\n".join(
        f"  `{a['ticker']:<6}` {a['pct']:+.2f}%   ${a['past']:.2f} → ${a['now']:.2f}"
        for a in alerts
    )
    text = (
        f"🚨 *Stock Drop Alert*\n\n"
        f"Dropped >{abs(THRESHOLD_PCT):.0f}% in last {LOOKBACK_HOURS}h:\n\n"
        f"{rows}\n\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_"
    )

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    response.raise_for_status()
    print(f"Telegram alert sent for: {[a['ticker'] for a in alerts]}")


def main() -> None:
    print(f"\n=== Stock alert check @ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    print(f"    Watching: {TICKERS}")
    alerts = []

    for ticker in TICKERS:
        now, past, pct = get_price_change(ticker)

        if pct is None:
            continue

        print(f"  {ticker}: {pct:+.2f}% over last {LOOKBACK_HOURS}h  "
              f"(${past:.2f} → ${now:.2f})")

        if pct <= THRESHOLD_PCT:
            alerts.append({"ticker": ticker, "now": now, "past": past, "pct": pct})

    if alerts:
        send_telegram_alert(alerts)
    else:
        print("No alerts triggered.")


if __name__ == "__main__":
    main()
