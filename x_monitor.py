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
    # This matches the endpoint from your curl command
    url = f"https://{HOST}/user/tweetsandreplies"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
    try:
        res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
        return res.json()
    except:
        return {}

def run():
    print(f"--- STARTING SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        raw_data = get_tweets(user_id)
        
        # ── NEW ROBUST PARSING LOGIC ──
        # Find instructions in the JSON regardless of deep path changes
        try:
            instructions = raw_data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
        except:
            instructions = []

        all_entries = []
        for instr in instructions:
            # We take entries from ANY instruction that contains them
            if "entries" in instr:
                all_entries.extend(instr["entries"])
            elif "entry" in instr:
                all_entries.append(instr["entry"])

        print(f"🔍 Found {len(all_entries)} items to analyze for @{acc['handle']}...")
        
        alerts_sent = 0
        for entry in all_entries:
            try:
                # Dig for tweet content (handles both normal and nested structures)
                content = entry.get("content", {})
                item = content.get("itemContent", {}).get("tweet_results", {}).get("result", {})
                
                if not item: continue
                if "tweet" in item: item = item["tweet"]
                
                legacy = item.get("legacy", {})
                text = legacy.get("full_text", "")
                likes = int(legacy.get("favorite_count", 0))
                tweet_id = legacy.get("id_str")

                if not text or not tweet_id: continue

                # Scoring
                tickers = TICKER_PATTERN.findall(text.upper())
                score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
                score = round(min(100, score), 1)

                if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                    msg = (
                        f"🚨 *High Signal* (@{acc['handle']})\n\n"
                        f"{text[:350]}...\n\n"
                        f"❤️ {likes:,} | [Link](https://x.com/i/web/status/{tweet_id})"
                    )
                    send_tg(msg)
                    alerts_sent += 1
            except:
                continue

        print(f"✅ Finished @{acc['handle']} ({alerts_sent} alerts sent)")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
