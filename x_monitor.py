import os
import re
import time
import requests
from datetime import datetime

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG
MIN_LIKES = 1        
ALERT_THRESHOLD = 5  
HOST = "twitter-x.p.rapidapi.com"

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "weight": 1.0},
    {"handle": "HindenburgRes", "name": "Hindenburg Research", "weight": 1.0},
    {"handle": "unusual_whales", "name": "Unusual Whales", "weight": 0.8},
]

TICKER_PATTERN = re.compile(r'\$[A-Z]{1,5}\b')

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def get_user_id(handle):
    url = f"https://{HOST}/user/details"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"username": handle}, timeout=15)
        # Search for numeric ID anywhere in the response text
        match = re.search(r'"rest_id":"(\d+)"', res.text)
        if not match: match = re.search(r'"id":"(\d+)"', res.text)
        return match.group(1) if match else None
    except:
        return None

def find_tweets_universal(data, tweets_list):
    """Deep search: finds every object that contains tweet-like content."""
    if isinstance(data, dict):
        # Look for the two common tweet text keys
        if "full_text" in data or "text" in data:
            tweets_list.append(data)
        for value in data.values():
            find_tweets_universal(value, tweets_list)
    elif isinstance(data, list):
        for item in data:
            find_tweets_universal(item, tweets_list)

def run():
    print(f"--- STARTING SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ ID not found for @{acc['handle']}")
            continue

        # Using /user/tweets (Better for main posts of big accounts)
        url = f"https://{HOST}/user/tweets"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            raw_data = res.json()
        except:
            continue

        tweets_found = []
        find_tweets_universal(raw_data, tweets_found)
        
        print(f"🔍 Found {len(tweets_found)} tweet objects for @{acc['handle']}")
        
        processed_ids = set()
        alerts_sent = 0

        for tweet in tweets_found:
            # Check both possible text fields
            text = tweet.get("full_text") or tweet.get("text") or ""
            likes = int(tweet.get("favorite_count", 0))
            t_id = tweet.get("id_str")

            if not text or not t_id or t_id in processed_ids:
                continue
            
            processed_ids.add(t_id)

            # Calculation
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 *High Signal* (@{acc['handle']})\n\n"
                    f"{text[:350]}...\n\n"
                    f"❤️ {likes:,} | [Link](https://x.com/i/web/status/{t_id})"
                )
                send_tg(msg)
                alerts_sent += 1
                if alerts_sent >= 2: break 

        print(f"✅ Finished @{acc['handle']} ({alerts_sent} alerts sent)")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
