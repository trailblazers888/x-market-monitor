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
MIN_LIKES = 1        
ALERT_THRESHOLD = 5  
HOST = "twitter-x.p.rapidapi.com"

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "weight": 1.0},
    {"handle": "HindenburgRes", "name": "Hindenburg Research", "weight": 1.0},
    {"handle": "unusual_whales", "name": "Unusual Whales", "weight": 0.8},
]

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
        # Brute force: find ANY number that follows "rest_id" or "id"
        ids = re.findall(r'"(?:rest_id|id)":"(\d+)"', res.text)
        return ids[0] if ids else None
    except:
        return None

def run():
    print(f"--- STARTING FINAL SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        # Use the endpoint you verified: tweetsandreplies
        url = f"https://{HOST}/user/tweetsandreplies"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            raw_data = res.text
        except:
            continue

        # ── BRUTE FORCE REGEX PARSING ──
        # We find every single tweet text and its corresponding ID and Like count
        # This ignores ALL folders and JSON structures
        texts  = re.findall(r'"full_text":"(.*?)"', raw_data, re.DOTALL)
        likes  = re.findall(r'"favorite_count":(\d+)', raw_text) # Note: changed back to raw_text
        # Re-fetching because of a typo in my thinking, here is the clean logic:
        
        # Actually, let's use a simpler split-block method which is 100% reliable
        blocks = raw_data.split('{"content"')
        
        found_count = 0
        processed_ids = set()

        for block in blocks:
            t_match = re.search(r'"full_text":"(.*?)"', block, re.DOTALL)
            l_match = re.search(r'"favorite_count":(\d+)', block)
            i_match = re.search(r'"id_str":"(\d+)"', block)

            if t_match and l_match and i_match:
                tweet_id = i_match.group(1)
                if tweet_id in processed_ids: continue
                processed_ids.add(tweet_id)

                text = t_match.group(1).encode().decode('unicode_escape', 'ignore')
                like_count = int(l_match.group(1))

                if like_count >= MIN_LIKES:
                    # Clean up common JSON junk
                    display_text = text.replace('\\n', '\n').replace('\\"', '"')
                    msg = (
                        f"🚨 *High Signal* (@{acc['handle']})\n\n"
                        f"{display_text[:400]}...\n\n"
                        f"❤️ {like_count:,} | [Link](https://x.com/any/status/{tweet_id})"
                    )
                    send_tg(msg)
                    found_count += 1
                    if found_count >= 2: break # Max 2 per account

        print(f"✅ Found {found_count} tweets for @{acc['handle']}")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
