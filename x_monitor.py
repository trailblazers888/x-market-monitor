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
        ids = re.findall(r'"(?:rest_id|id)":"(\d+)"', res.text)
        return ids[0] if ids else None
    except:
        return None

def harvest_tweets(obj, results):
    """Deep-dives into ANY JSON structure to find tweets."""
    if isinstance(obj, dict):
        # If we found a 'legacy' block, it's a tweet. 
        if "legacy" in obj and isinstance(obj["legacy"], dict):
            leg = obj["legacy"]
            if "full_text" in leg or "text" in leg:
                results.append(leg)
        # Some APIs don't use 'legacy', they put text/likes directly in the result
        elif ("full_text" in obj or "text" in obj) and "favorite_count" in obj:
            results.append(obj)
        
        # Keep digging
        for v in obj.values():
            harvest_tweets(v, results)
    elif isinstance(obj, list):
        for i in obj:
            harvest_tweets(i, results)

def run():
    print(f"--- STARTING FINAL SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        # Using /user/tweetsandreplies - it's the most data-rich endpoint
        url = f"https://{HOST}/user/tweetsandreplies"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            data = res.json()
        except:
            continue

        tweets_found = []
        harvest_tweets(data, tweets_found)
        
        print(f"🔍 Found {len(tweets_found)} tweet objects for @{acc['handle']}")
        
        processed_ids = set()
        alerts_sent = 0

        for tweet in tweets_found:
            t_id = tweet.get("id_str")
            if not t_id or t_id in processed_ids: continue
            processed_ids.add(t_id)

            text = tweet.get("full_text") or tweet.get("text") or ""
            likes = int(tweet.get("favorite_count", 0))

            if not text: continue

            # Calculation
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                # Basic cleaning for JSON text
                clean_text = text.encode().decode('unicode_escape', 'ignore').replace('\\n', '\n').replace('\\"', '"')
                msg = (
                    f"🚨 *Signal* (@{acc['handle']})\n\n"
                    f"{clean_text[:400]}...\n\n"
                    f"❤️ {likes:,} | [Link](https://x.com/i/web/status/{t_id})"
                )
                send_tg(msg)
                alerts_sent += 1
                if alerts_sent >= 3: break 

        print(f"✅ Finished @{acc['handle']} ({alerts_sent} alerts sent)")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
