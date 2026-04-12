import os
import re
import time
import requests
from datetime import datetime, timezone

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG (Keep these low for the first test!)
MIN_LIKES = 1        
ALERT_THRESHOLD = 5 
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
        data = res.json()
        return data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
    except:
        return None

def get_tweets(user_id):
    url = f"https://{HOST}/user/tweetsandreplies"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "10"}, timeout=15)
        return res.json().get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
    except:
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

        print(f"🔍 Analyzing {len(entries)} items for @{acc['handle']}...")
        found_count = 0

        for entry in entries:
            # Step 1: Find the tweet data inside the entry
            result = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
            if not result: continue
            
            # Step 2: Handle "Tweet" vs "Retweet" structure
            if "tweet" in result: result = result["tweet"]
            
            legacy = result.get("legacy", {})
            text = legacy.get("full_text", "")
            likes = int(legacy.get("favorite_count", 0))
            tweet_id = legacy.get("id_str")

            if not text: continue
            
            # Step 3: Scoring
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 *High Signal Detected*\n\n"
                    f"👤 *{acc['name']}* (@{acc['handle']})\n"
                    f"📊 Score: {score}/100 | ❤️ {likes:,}\n\n"
                    f"📝 {text[:350]}...\n\n"
                    f"🔗 [View on X](https://x.com/any/status/{tweet_id})"
                )
                send_tg(msg)
                found_count += 1
                print(f"📬 Alert sent for: {text[:30]}...")
        
        if found_count == 0:
            print(f"ℹ️ No high-signal posts found for @{acc['handle']} this run.")
        
        time.sleep(2)

if __name__ == "__main__":
    run()
