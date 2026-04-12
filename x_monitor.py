import os
import re
import time
import requests
from datetime import datetime, timezone

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG (Keep low for testing)
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
        return res.json().get("data", {}).get("user", {}).get("result", {}).get("rest_id")
    except:
        return None

def get_tweets(user_id):
    # Switching to /user/tweets (Cleaner than tweetsandreplies for market signals)
    url = f"https://{HOST}/user/tweets"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
        data = res.json()
        # Search for instructions in all possible locations
        res_data = data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {})
        return res_data.get("instructions", [])
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
        
        # COLLECT ALL ENTRIES FROM ALL INSTRUCTIONS
        all_entries = []
        for instr in instructions:
            if "entries" in instr:
                all_entries.extend(instr["entries"])
            elif "entry" in instr:
                all_entries.append(instr["entry"])

        print(f"🔍 Found {len(all_entries)} potential items for @{acc['handle']}...")
        found_count = 0

        for entry in all_entries:
            # Deep dive search for the 'legacy' object which contains the text and likes
            content = entry.get("content", {})
            item = content.get("itemContent", {}).get("tweet_results", {}).get("result", {})
            
            # If it's a retweet, the data is one level deeper
            if "tweet" in item: item = item["tweet"]
            if "core" not in item and "legacy" not in item:
                # Sometimes it's wrapped in another result object
                item = item.get("result", {})

            legacy = item.get("legacy", {})
            text = legacy.get("full_text", "")
            likes = int(legacy.get("favorite_count", 0))
            tweet_id = legacy.get("id_str")

            if not text or tweet_id is None:
                continue
            
            # Scoring
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 *High Signal Detected*\n\n"
                    f"👤 *{acc['name']}* (@{acc['handle']})\n"
                    f"📊 Score: {score}/100 | ❤️ {likes:,}\n\n"
                    f"📝 {text[:350]}...\n\n"
                    f"🔗 [View on X](https://x.com/i/web/status/{tweet_id})"
                )
                send_tg(msg)
                found_
