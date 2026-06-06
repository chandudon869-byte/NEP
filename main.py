from fastapi import FastAPI
import requests

app = FastAPI()

@app.get("/")
def home():
    return {"status": "running"}
@app.get("/history/{symbol}")
def history(symbol: str):
    return {"symbol": symbol}
from bs4 import BeautifulSoup

def get_token():

    session = requests.Session()

    html = session.get(
        "https://nepsealpha.com/search?q=NABIL",
        headers={"User-Agent":"Mozilla/5.0"}
    ).text

    soup = BeautifulSoup(html, "html.parser")

    token = soup.find("meta", {"name":"csrf-token"})

    return token["content"], session
@app.get("/history/{symbol}")
def history(symbol: str):

    token, session = get_token()

    payload = {
        "symbol": symbol,
        "filter_type": "date-range",
        "price_type": "unadjusted",
        "time_frame": "daily",
        "start_date": "2026-01-01",
        "end_date": "2026-06-06",
        "_token": token
    }

    response = session.post(
        "https://nepsealpha.com/nepse-data",
        data=payload,
        headers={
            "User-Agent":"Mozilla/5.0"
        }
    )

    return response.json()