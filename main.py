from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import time
from datetime import date
import numpy as np
import os
import google.generativeai as genai

app = FastAPI()

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 5  # seconds

ALERTS = []

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # safer

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# =========================
# CACHE
# =========================
def get_cache(key):
    if key in CACHE:
        data, expiry = CACHE[key]
        if time.time() < expiry:
            return data
    return None


def set_cache(key, value, ttl=CACHE_TTL):
    CACHE[key] = (value, time.time() + ttl)


# =========================
# MARKET SCRAPER
# =========================
def fetch_market():
    url = "https://nepalipaisa.com/live-market"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    stocks = []

    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        try:
            stocks.append({
                "symbol": cols[0].text.strip(),
                "ltp": float(cols[1].text.replace(",", "")),
                "change": float(cols[2].text.replace(",", "")),
                "percent": float(cols[3].text.replace("%", ""))
            })
        except:
            continue

    return stocks


# =========================
# TOP GAINERS / LOSERS
# =========================
@app.get("/top-gainers")
def top_gainers():
    cache = get_cache("gainers")
    if cache:
        return cache

    data = fetch_market()
    result = sorted(data, key=lambda x: x["percent"], reverse=True)[:10]

    set_cache("gainers", result)
    return result


@app.get("/top-losers")
def top_losers():
    cache = get_cache("losers")
    if cache:
        return cache

    data = fetch_market()
    result = sorted(data, key=lambda x: x["percent"])[:10]

    set_cache("losers", result)
    return result


# =========================
# MARKET SUMMARY
# =========================
@app.get("/market-summary")
def market_summary():
    data = fetch_market()

    return {
        "total": len(data),
        "gainers": len([x for x in data if x["percent"] > 0]),
        "losers": len([x for x in data if x["percent"] < 0]),
        "unchanged": len([x for x in data if x["percent"] == 0]),
    }


# =========================
# INDICATORS
# =========================
def rsi(prices, period=14):
    prices = np.array(prices)
    deltas = np.diff(prices)

    gain = np.where(deltas > 0, deltas, 0)
    loss = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ema(data, period):
    data = np.array(data)

    if len(data) == 0:
        return 0

    k = 2 / (period + 1)
    ema_val = data[0]

    for price in data[1:]:
        ema_val = price * k + ema_val * (1 - k)

    return ema_val


# =========================
# HISTORY (NepseAlpha)
# =========================
def fetch_history(symbol):
    url = f"https://nepsealpha.com/search?q={symbol}"
    session = requests.Session()

    html = session.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
    soup = BeautifulSoup(html, "html.parser")

    token = soup.find("meta", {"name": "csrf-token"})
    if not token:
        return {}

    payload = {
        "symbol": symbol,
        "start_date": "2024-01-01",
        "end_date": date.today().strftime("%Y-%m-%d"),
        "filter_type": "date-range",
        "price_type": "unadjusted",
        "time_frame": "daily",
        "_token": token["content"]
    }

    r = session.post("https://nepsealpha.com/nepse-data", data=payload)

    try:
        return r.json()
    except:
        return {}


def extract_closes(data):
    if not data or "data" not in data:
        return []

    return [
        float(c["close"])
        for c in data["data"]
        if "close" in c
    ]


# =========================
# TREND ANALYSIS
# =========================
def detect_trend(closes):
    if len(closes) < 20:
        return "INSUFFICIENT_DATA"

    ema20 = ema(closes[-20:], 20)
    ema50 = ema(closes[-50:] if len(closes) >= 50 else closes, 10)

    momentum = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0

    if ema20 > ema50 and momentum > 0:
        return "BULLISH"

    if ema20 < ema50 and momentum < 0:
        return "BEARISH"

    return "SIDEWAYS"


# =========================
# SUPPORT / RESISTANCE
# =========================
def find_swing_points(closes, window=3):
    highs, lows = [], []

    for i in range(window, len(closes) - window):
        left = closes[i - window:i]
        right = closes[i + 1:i + window + 1]
        current = closes[i]

        if current > max(left) and current > max(right):
            highs.append(current)

        if current < min(left) and current < min(right):
            lows.append(current)

    return highs, lows


def cluster(levels, tolerance=1.0):
    if not levels:
        return []

    levels.sort()
    clusters = [[levels[0]]]

    for p in levels[1:]:
        if abs(p - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    return [sum(c) / len(c) for c in clusters]


def get_sr(closes):
    highs, lows = find_swing_points(closes)

    resistance = sorted(cluster(highs), reverse=True)[:3]
    support = sorted(cluster(lows))[:3]

    return support, resistance


# =========================
# BREAKOUT
# =========================
def detect_breakout(closes, support, resistance):
    last = closes[-1]
    prev = closes[-2]

    res = max(resistance) if resistance else None
    sup = min(support) if support else None

    if res and last > res:
        return "BREAKOUT_UP"

    if sup and last < sup:
        return "BREAKDOWN"

    return "NO_BREAKOUT"


# =========================
# API ROUTES
# =========================
@app.get("/history/{symbol}")
def history(symbol: str):
    return fetch_history(symbol)


@app.get("/trend/{symbol}")
def trend(symbol: str):
    data = fetch_history(symbol)
    closes = extract_closes(data)

    return {
        "symbol": symbol,
        "trend": detect_trend(closes),
        "last_price": closes[-1] if closes else None
    }


@app.get("/sr/{symbol}")
def support_resistance(symbol: str):
    data = fetch_history(symbol)
    closes = extract_closes(data)

    support, resistance = get_sr(closes)

    return {
        "symbol": symbol,
        "support": support,
        "resistance": resistance
    }


@app.get("/breakout/{symbol}")
def breakout(symbol: str):
    data = fetch_history(symbol)
    closes = extract_closes(data)

    support, resistance = get_sr(closes)

    return {
        "symbol": symbol,
        "breakout": detect_breakout(closes, support, resistance),
        "support": support,
        "resistance": resistance
    }


@app.get("/indicators/{symbol}")
def indicators(symbol: str):
    data = fetch_history(symbol)
    closes = extract_closes(data)

    return {
        "symbol": symbol,
        "rsi": rsi(closes) if len(closes) >= 14 else None,
        "ema20": ema(closes[-20:], 20) if len(closes) >= 20 else None
    }


# =========================
# ALERT SYSTEM
# =========================
@app.get("/add-alert")
def add_alert(symbol: str, price: float):
    ALERTS.append({"symbol": symbol, "price": price})
    return {"status": "added"}


@app.get("/check-alerts/{symbol}/{current_price}")
def check_alerts(symbol: str, current_price: float):
    triggered = [
        a for a in ALERTS
        if a["symbol"] == symbol and current_price >= a["price"]
    ]

    return {"triggered": triggered}


# =========================
# AI SIGNAL (SAFE PLACEHOLDER)
# =========================
@app.get("/ai-signal/{symbol}")
def ai_signal(symbol: str):
    return {
        "symbol": symbol,
        "signal": "BUY",
        "confidence": 0.70,
        "reason": "Momentum + trend alignment"
    }