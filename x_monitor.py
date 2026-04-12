import os
import re
import time
import requests
import json
from datetime import datetime

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG
MIN_LIKES = 1          # Set to 500 later
ALERT_THRESHOLD = 5    # Set to 60 later
HOST = "twitter-x.p.rapidapi.com"

# 3. VERIFIED WATCHLIST
WATCHLIST = [
    {"handle": "BillAckman",       "name": "Bill Ackman",        "weight": 1.0},
    {"handle": "michaeljburry",    "name": "Michael Burry",      "weight": 1.0},
    {"handle": "RayDalio",         "name": "Ray Dalio",          "weight": 0.9},
    {"handle": "CathieDWood",      "name": "Cathie Wood",        "weight": 0.8},
    {"handle": "elonmusk",         "name": "Elon Musk",          "weight": 1.0},
    {"handle": "chamath",          "name": "Chamath Palihapitiya","weight": 0.9},
    {"handle": "HindenburgRes",    "name": "Hindenburg Research","weight": 1.0},
    {"handle": "unusual_whales",   "name": "Unusual Whales",     "weight": 0.8},
    {"handle": "zerohedge",        "name": "Zero Hedge",         "weight": 0.6},
    {"handle": "LynAldenContact",  "name": "Lyn Alden",          "weight": 0.8},
    {"handle": "KobeissiLetter",   "name": "The Kobeissi Letter","weight": 0.7},
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
        # Navigate the new Pro-Account JSON structure
        user_res = data.get("data", {}).get("user", {}).get("result", {})
        return user_res.get("rest_id") or user_res.get("id")
    except:
        return None

def run():
    print(f"--- STARTING CLEAN SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Scanning @{acc['handle']}...", end=" ", flush=True)
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print("❌ ID Not Found")
            continue

        url = f"https://{HOST}/user/tweets"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            data = res.json()
        except:
            print("❌ Connection Error")
            continue

        # Look for tweets in ALL possible locations (Instruction entries or list items)
        instructions = data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
        
        entries = []
        for instr in instructions:
            if instr.get("type") == "TimelineAddEntries":
                entries = instr.get("entries", [])
                break
        
        if not entries:
            # Fallback for Ackman/Musk special timelines
            print("Trying fallback parser...", end=" ")
            raw_text = json.dumps(data)
            tweet_blobs = re.findall(r'"full_text":"(.*?)"', raw_text)
            # Filter unique and non-empty
            entries = [{"text": t} for t in set(tweet_blobs) if len(t) > 5]

        alerts_sent = 0
        for entry in entries:
            try:
                # 1. Extract Text
                if "text" in entry: # Fallback path
                    text = entry["text"].encode('utf-8').decode('unicode_escape')
                    likes = 1000 # Dummy for fallback
                    t_id = "0"
                else: # Normal path
                    item = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
                    if "tweet" in item: item = item["tweet"]
                    legacy = item.get("legacy", {})
                    text = legacy.get("full_text", "")
                    likes = int(legacy.get("favorite_count", 0))
                    t_id = legacy.get("id_str", "0")

                # 2. FILTER NOISE
                if not text or text.startswith("RT @"): continue # Skip Retweets
                if likes < MIN_LIKES: continue

                # 3. CLEAN TEXT (Fixing the rubbish symbols)
                clean_text = text.replace('\\n', '\n').replace('\\"', '"')

                # 4. SCORING
                tickers = TICKER_PATTERN.findall(clean_text.upper())
                score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
                score = round(min(100, score), 1)

                if score >= ALERT_THRESHOLD:
                    msg = (
                        f"🚨 *SIGNAL: {acc['name']}*\n"
                        f"📊 Score: {score}/100\n\n"
                        f"{clean_text[:500]}\n\n"
                        f"❤️ {likes:,} | [View on X](https://x.com/i/web/status/{t_id})"
                    )
                    send_tg(msg)
                    alerts_sent += 1
                    if alerts_sent >= 2: break
            except:
                continue

        print(f"✅ Found {alerts_sent}")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
