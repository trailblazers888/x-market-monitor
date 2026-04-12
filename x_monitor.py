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
        ids = re.findall(r'"(?:rest_id|id)":"(\d+)"', res.text)
        return ids[0] if ids else None
    except:
        return None

def run():
    print(f"--- STARTING FINAL SCAN: {datetime.now()} ---")
    
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY is missing!")
        return

    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        url = f"https://{HOST}/user/tweetsandreplies"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            # This is the variable name that caused the previous error
            full_api_response = res.text 
        except Exception as e:
            print(f"❌ API Request failed: {e}")
            continue

        # ── BRUTE FORCE PARSER ──
        # Split the raw data into individual blocks based on the word 'legacy'
        blocks = full_api_response.split('"legacy":')
        
        found_count = 0
        processed_ids = set()

        # Skip the first block because it's just header data
        for block in blocks[1:]:
            # Use Regex to find the three things we need
            t_match = re.search(r'"full_text":"(.*?)"', block, re.DOTALL)
            l_match = re.search(r'"favorite_count":(\d+)', block)
            i_match = re.search(r'"id_str":"(\d+)"', block)

            if t_match and l_match and i_match:
                tweet_id = i_match.group(1)
                
                # Don't process the same tweet twice
                if tweet_id in processed_ids: 
                    continue
                processed_ids.add(tweet_id)

                # Clean up the text
                raw_text = t_match.group(1).encode().decode('unicode_escape', 'ignore')
                likes = int(l_match.group(1))

                if likes >= MIN_LIKES:
                    # Clean common escape characters
                    display_text = raw_text.replace('\\n', '\n').replace('\\"', '"')
                    
                    # Send alert
                    msg = (
                        f"🚨 *High Signal* (@{acc['handle']})\n\n"
                        f"{display_text[:400]}...\n\n"
                        f"❤️ {likes:,} | [Link](https://x.com/any/status/{tweet_id})"
                    )
                    send_tg(msg)
                    found_count += 1
                    
                    # Stop after 2 alerts per account to keep it fast
                    if found_count >= 2: 
                        break

        print(f"✅ Found {found_count} tweets for @{acc['handle']}")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
