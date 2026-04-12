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
# CHANGE MIN_LIKES TO 1 TO TEST AND MAKE SURE YOU GET A MESSAGE!
MIN_LIKES = 50 
ALERT_THRESHOLD = 60
HOST = "twitter-x.p.rapidapi.com"

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "weight": 1.0},
    {"handle": "HindenburgRes", "name": "Hindenburg Research", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "weight": 1.0},
    {"handle": "unusual_whales", "name": "Unusual Whales", "weight": 0.8},
]

TICKER_PATTERN = re.compile(r'\$[A-Z]{1,5}\b')

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def get_user_id(handle):
    """Converts a handle like 'elonmusk' to a numeric User ID."""
    url = f"https://{HOST}/user/details"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"username": handle}, timeout=15)
        return res.json().get("data", {}).get("user", {}).get("result", {}).get("rest_id")
    except Exception as e:
        print(f"Error getting ID for @{handle}: {e}")
        return None

def get_tweets(user_id):
    """Fetches the latest tweets and replies for a numeric User ID."""
    url = f"https://{HOST}/user/tweetsandreplies"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    querystring = {"user_id": user_id, "limit": "10"}
    try:
        res = requests.get(url, headers=headers, params=querystring, timeout=15)
        data = res.json()
        return data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
    except Exception as e:
        print(f"Error getting tweets: {e}")
        return []

def run():
    print(f"🚀 Scan started at {datetime.now()}")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Could not find ID for @{acc['handle']}")
            continue

        instructions = get_tweets(user_id)
        entries = []
        for instr in instructions:
            if instr.get("type") == "TimelineAddEntries":
                entries = instr.get("entries", [])
                break

        for entry in entries[:5]:
            content = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
            if not content: continue
            
            legacy = content.get("legacy", {})
            text = legacy.get("full_text", "")
            likes = int(legacy.get("favorite_count", 0))
            tweet_id = legacy.get("id_str")

            if likes < MIN_LIKES: continue

            # Scoring
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if score >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 *High Signal Detected*\n\n"
                    f"👤 *{acc['name']}* (@{acc['handle']})\n"
                    f"📊 Score: {score}/100\n"
                    f"❤️ Likes: {likes:,}\n\n"
                    f"📝 {text[:300]}...\n\n"
                    f"🔗 [View on X](https://x.com/any/status/{tweet_id})"
                )
                send_tg(msg)
                print(f"✅ Alert sent for @{acc['handle']}")
        
        time.sleep(2) # Pause briefly between accounts

if __name__ == "__main__":
    run()
