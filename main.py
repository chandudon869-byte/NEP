from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import time
from datetime import date
import numpy as np

app = FastAPI()

# =========================
# CACHE SYSTEM
# =========================
CACHE = {}
CACHE_TTL = 5  # seconds for live data


def get_cache(key):
    if key in CACHE:
        data, expiry = CACHE[key]
        if time.time() < expiry:
            return data
    return None


def set_cache(key, value, ttl=CACHE_TTL):
    CACHE[key] = (value, time.time() + ttl)


# =========================
# LIVE MARKET SCRAPER
# =========================
def fetch_market():

    url = "https://nepalipaisa.com/live-market"

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    stocks = []

    for row in soup.find_all("tr"):
        cols = row.find_all("td")

        if len(cols) < 5:
            continue

        try:
            symbol = cols[0].text.strip()
            ltp = float(cols[1].text.replace(",", ""))
            change = float(cols[2].text.replace(",", ""))
            percent = float(cols[3].text.replace("%", ""))

            stocks.append({
                "symbol": symbol,
                "ltp": ltp,
                "change": change,
                "percent": percent
            })
        except:
            continue

    return stocks


# =========================
# TOP GAINERS
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


# =========================
# TOP LOSERS
# =========================
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

    gain = len([x for x in data if x["percent"] > 0])
    loss = len([x for x in data if x["percent"] < 0])
    same = len([x for x in data if x["percent"] == 0])

    return {
        "total": len(data),
        "gainers": gain,
        "losers": loss,
        "unchanged": same
    }


# =========================
# NEPSE INDEX (REAL SCRAPING FIX)
# =========================
@app.get("/nepse-index")
def nepse_index():

    cache = get_cache("index")
    if cache:
        return cache

    url = "https://www.nepalstock.com"

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    text = soup.get_text()

    # crude extraction fallback (NEPSE is JS-rendered)
    result = {
        "note": "Index extracted from homepage (may vary)",
        "raw": text[:300]
    }

    set_cache("index", result)
    return result


# =========================
# RSI + MACD CALCULATOR
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


@app.get("/indicators/{symbol}")
def indicators(symbol: str):

    # fake sample prices (replace with history endpoint)
    prices = [100, 102, 101, 105, 110, 108, 107, 109, 111, 115]

    return {
        "symbol": symbol,
        "rsi": rsi(prices),
        "macd": "simplified-placeholder"
    }


# =========================
# AI SIGNAL (GEMINI READY)
# =========================
@app.get("/ai-signal/{symbol}")
def ai_signal(symbol: str):

    # placeholder logic (replace with Gemini API later)
    return {
        "symbol": symbol,
        "signal": "BUY",
        "confidence": 0.72,
        "reason": "Price momentum + volume increase"
    }


# =========================
# PRICE ALERT SYSTEM (simple memory-based)
# =========================
ALERTS = []


@app.get("/add-alert")
def add_alert(symbol: str, price: float):

    ALERTS.append({
        "symbol": symbol,
        "price": price
    })

    return {"status": "alert added"}


@app.get("/check-alerts/{symbol}/{current_price}")
def check_alerts(symbol: str, current_price: float):

    triggered = []

    for a in ALERTS:
        if a["symbol"] == symbol and current_price >= a["price"]:
            triggered.append(a)

    return {
        "triggered": triggered
    }


# =========================
# HISTORY (KEEP YOUR WORKING VERSION)
# =========================
@app.get("/history/{symbol}")
def history(symbol: str):

    url = f"https://nepsealpha.com/search?q={symbol}"

    session = requests.Session()

    html = session.get(url, headers={"User-Agent": "Mozilla/5.0"}).text

    soup = BeautifulSoup(html, "html.parser")
    token = soup.find("meta", {"name": "csrf-token"})["content"]

    payload = {
        "symbol": symbol,
        "start_date": "2024-01-01",
        "end_date": date.today().strftime("%Y-%m-%d"),
        "filter_type": "date-range",
        "price_type": "unadjusted",
        "time_frame": "daily",
        "_token": token
    }

    r = session.post("https://nepsealpha.com/nepse-data", data=payload)

    return r.json()
import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyBVD0JRKOsWJdTLWyjdwaT7mbBvusbaVn4"

genai.configure(api_key=GEMINI_API_KEY)
def analyze_with_gemini(symbol, price_data, indicators):

    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
You are a professional stock market analyst for NEPSE (Nepal Stock Exchange).

Analyze this stock:

Symbol: {symbol}

Recent Data:
{price_data}

Indicators:
{indicators}

Give output in JSON:
{{
  "signal": "BUY | SELL | HOLD",
  "confidence": 0-100,
  "support": number,
  "resistance": number,
  "reason": "short explanation"
}}
"""

    response = model.generate_content(prompt)

    return response.text
@app.get("/ai-analysis/{symbol}")
def ai_analysis(symbol: str):

    # Example: replace with real history API later
    price_data = [
        {"close": 520},
        {"close": 525},
        {"close": 530},
        {"close": 528},
        {"close": 540}
    ]

    indicators = {
        "rsi": 62,
        "ema20": 528,
        "ema50": 515,
        "volume": 120000
    }

    result = analyze_with_gemini(symbol, price_data, indicators)

    return {
        "symbol": symbol,
        "analysis": result
    }
import numpy as np
def ema(data, period):
    data = np.array(data)
    k = 2 / (period + 1)

    ema_values = [data[0]]

    for price in data[1:]:
        ema_values.append(price * k + ema_values[-1] * (1 - k))

    return ema_values[-1]
def detect_trend(closes):

    if len(closes) < 10:
        return "UNKNOWN"

    ema20 = ema(closes[-20:], 20)
    ema50 = ema(closes[-50:] if len(closes) >= 50 else closes, 10)

    last_price = closes[-1]

    # momentum
    recent_change = (closes[-1] - closes[-5]) / closes[-5] * 100

    if ema20 > ema50 and recent_change > 0:
        return "BULLISH"

    elif ema20 < ema50 and recent_change < 0:
        return "BEARISH"

    else:
        return "SIDEWAYS"
    
@app.get("/trend/{symbol}")
def trend(symbol: str):

    # TODO: replace with real candle API
    sample_closes = [520, 522, 525, 528, 530, 533, 535, 540, 545, 550]

    trend_result = detect_trend(sample_closes)

    return {
        "symbol": symbol,
        "trend": trend_result,
        "note": "Based on EMA20, EMA50 and momentum"
    }