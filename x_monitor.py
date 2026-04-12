import os
import re
import time
import requests
from datetime import datetime, timezone

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG
MIN_LIKES = 1        # Set to 1 for testing!
ALERT_THRESHOLD = 10 # Set to 10 for testing!
HOST = "twitter-x.p.rapidapi.com"

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "weight": 1.0},
]

TICKER_PATTERN = re.compile(r'\$[A-Z]{1,5}\b')

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def get_user_id(handle):
    url = f"https://{HOST}/user/details"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"username": handle}, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ API Error {res.status_code}: {res.text}")
            return None
        
        data = res.json()
        # Trying two different JSON paths just in case
        user_id = data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
        if not user_id:
            user_id = data.get("rest_id") or data.get("id")
        
        return user_id
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None

def get_tweets(user_id):
    url = f"https://{HOST}/user/tweetsandreplies"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "10"}, timeout=15)
        data = res.json()
        return data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
    except:
        return []

def run():
    print(f"🚀 Scan started at {datetime.now()}")
    if not RAPIDAPI_KEY:
        print("❌ ERROR: RAPIDAPI_KEY secret is missing!")
        return

    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Could not find ID for @{acc['handle']}")
            continue

        print(f"✅ Found ID {user_id}. Fetching tweets...")
        instructions = get_tweets(user_id)
        entries = []
        for instr in instructions:
            if instr.get("type") == "TimelineAddEntries":
                entries = instr.get("entries", [])
                break

        for entry in entries[:5]:
            item = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
            if not item: continue
            
            # Handle possible nested 'tweet' object
            if "tweet" in item: item = item["tweet"]
            
            legacy = item.get("legacy", {})
            text = legacy.get("full_text", "")
            likes = int(legacy.get("favorite_count", 0))
            tweet_id = legacy.get("id_str")

            if likes < MIN_LIKES: continue

            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if score >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 *High Signal Detected*\n\n"
                    f"👤 *{acc['name']}* (@{acc['handle']})\n"
                    f"📊 Score: {score}/100 | ❤️ {likes:,}\n\n"
                    f"📝 {text[:300]}...\n\n"
                    f"🔗 [View on X](https://x.com/any/status/{tweet_id})"
                )
                send_tg(msg)
                print(f"📬 Alert sent for @{acc['handle']}")
        
        time.sleep(2)

if __name__ == "__main__":
    run()
