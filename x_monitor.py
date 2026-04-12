import os
import re
import requests
from datetime import datetime, timezone
from apify_client import ApifyClient

# Secrets pulled from GitHub Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
APIFY_TOKEN        = os.getenv("APIFY_TOKEN")

# Configuration
ALERT_THRESHOLD = 60
MIN_LIKES = 50

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "type": "activist", "weight": 1.0},
    {"handle": "HindenburgRes", "name": "Hindenburg Research", "type": "short", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "type": "activist", "weight": 1.0},
    {"handle": "unusual_whales", "name": "Unusual Whales", "type": "options", "weight": 0.8},
    {"handle": "zerohedge", "name": "Zero Hedge", "type": "media", "weight": 0.6},
]

TICKER_PATTERN = re.compile(r'\$[A-Z]{1,5}\b')

def get_sentiment(text):
    bull = ["undervalued", "buying", "long", "upside", "conviction"]
    bear = ["short", "fraud", "overvalued", "bubble", "sell", "warning"]
    t = text.lower()
    b_score = sum(1 for w in bull if w in t)
    s_score = sum(1 for w in bear if w in t)
    return "bullish" if b_score > s_score else ("bearish" if s_score > b_score else "neutral")

def calculate_score(likes, reposts, text, weight):
    import math
    eng = math.log1p(likes + (reposts * 3)) * 4
    tickers = len(TICKER_PATTERN.findall(text.upper())) * 5
    return round(min(100, eng + tickers + (weight * 10)), 1)

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def run():
    client = ApifyClient(APIFY_TOKEN)
    handles = [a["handle"] for a in WATCHLIST]
    
    print("Starting Apify Scraper...")
    run_input = {"twitterHandles": handles, "maxItems": 5}
    # Using a reliable third-party scraper on Apify
    run = client.actor("apidojo/twitter-scraper-lite").call(run_input=run_input)
    
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        text = item.get("full_text") or ""
        likes = item.get("favorite_count", 0)
        reposts = item.get("retweet_count", 0)
        handle = item.get("user", {}).get("screen_name")
        
        if likes < MIN_LIKES: continue

        # Find matching account in watchlist
        acc = next((a for a in WATCHLIST if a["handle"].lower() == handle.lower()), None)
        if not acc: continue

        score = calculate_score(likes, reposts, text, acc["weight"])
        
        if score >= ALERT_THRESHOLD:
            sentiment = get_sentiment(text)
            emoji = "🟢" if sentiment == "bullish" else ("🔴" if sentiment == "bearish" else "⚪")
            url = f"https://x.com/i/web/status/{item.get('id_str')}"
            
            msg = (
                f"🚨 *High Signal Detected*\n\n"
                f"👤 *{acc['name']}* (@{handle})\n"
                f"📊 Score: {score}/100\n"
                f"{emoji} Sentiment: {sentiment.capitalize()}\n\n"
                f"📝 {text[:250]}...\n\n"
                f"🔗 [View Post]({url})"
            )
            send_tg(msg)
            print(f"Alert sent for @{handle}")

if __name__ == "__main__":
    run()
send_tg("🤖 Connection Test: The bot is working!")
run()
