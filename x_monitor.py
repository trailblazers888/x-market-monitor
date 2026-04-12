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
MIN_LIKES = 1        # Low for testing
ALERT_THRESHOLD = 5  # Low for testing
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
    except Exception as e:
        print(f"Error getting ID for {handle}: {e}")
        return None

def get_tweets(user_id):
    url = f"https://{HOST}/user/tweetsandreplies"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "10"}, timeout=15)
        return res.json()
    except Exception as e:
        print(f"Error getting tweets: {e}")
        return {}

def run():
    print(f"--- STARTING SCAN: {datetime.now()} ---")
    
    if not RAPIDAPI_KEY:
        print("CRITICAL ERROR: RAPIDAPI_KEY secret is not set in GitHub!")
        return

    for acc in WATCHLIST:
        print(f"Processing @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"Could not get user_id for @{acc['handle']}")
            continue

        print(f"Found ID {user_id} for @{acc['handle']}. Searching for tweets...")
        raw_data = get_tweets(user_id)
        
        # Navigate the JSON data
        instructions = raw_data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
        
        entries = []
        for instr in instructions:
            if instr.get("type") == "TimelineAddEntries":
                entries = instr.get("entries", [])
                break

        print(f"Analyzing {len(entries)} items for @{acc['handle']}...")
        
        for entry in entries:
            try:
                # Find the tweet result
                result = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
                if "tweet" in result: result = result["tweet"]
                
                legacy = result.get("legacy", {})
                text = legacy.get("full_text", "")
                likes = int(legacy.get("favorite_count", 0))
                tweet_id = legacy.get("id_str")

                if not text: continue

                # Basic Score
                score = (likes / 1000) + (acc['weight'] * 20)
                
                if likes >= MIN_LIKES:
                    msg = (
                        f"🚨 *High Signal* (@{acc['handle']})\n\n"
                        f"{text[:300]}...\n\n"
                        f"❤️ {likes} | [Link](https://x.com/i/web/status/{tweet_id})"
                    )
                    send_tg(msg)
                    print(f"Alert sent for a tweet by @{acc['handle']}")
            except:
                continue

    print("--- SCAN COMPLETE ---")

# THIS PART IS THE MOST IMPORTANT - IT TELLS THE SCRIPT TO RUN!
if __name__ == "__main__":
    run()
