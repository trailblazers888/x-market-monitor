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
        ids = re.findall(r'"(?:rest_id|id)":"(\d+)"', res.text)
        return ids[0] if ids else None
    except:
        return None

def run():
    print(f"--- STARTING SCAN: {datetime.now()} ---")
    
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY MISSING!")
        return

    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        # Using /user/tweets ( cleaner for mega-accounts )
        url = f"https://{HOST}/user/tweets"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            raw_data = res.text 
        except:
            continue

        # ── GLOBAL VACUUM SEARCH ──
        # Instead of parsing, we find ALL tweet IDs, texts, and likes in the whole string
        tweet_ids = re.findall(r'"id_str":"(\d+)"', raw_data)
        texts     = re.findall(r'"full_text":"(.*?)"', raw_data, re.DOTALL)
        likes     = re.findall(r'"favorite_count":(\d+)', raw_data)

        # We only care about unique tweets
        processed_ids = set()
        alerts_sent = 0

        # We iterate through the raw data looking for "blocks" manually
        # This is the only way to catch Elon/Ackman
        items = raw_data.split('"full_text":"')
        
        for item in items[1:]: # Skip the first part
            try:
                # Extract the text (until the next " quote)
                tweet_text = item.split('","')[0]
                
                # Look for the nearest ID and Like count in this specific chunk
                id_match = re.search(r'"id_str":"(\d+)"', item)
                lk_match = re.search(r'"favorite_count":(\d+)', item)
                
                if id_match and lk_match:
                    t_id = id_match.group(1)
                    if t_id in processed_ids: continue
                    processed_ids.add(t_id)

                    l_count = int(lk_match.group(1))
                    
                    if l_count >= MIN_LIKES:
                        # Clean text
                        clean_text = tweet_text.encode().decode('unicode_escape', 'ignore')
                        clean_text = clean_text.replace('\\n', '\n').replace('\\"', '"')
                        
                        msg = (
                            f"🚨 *Signal* (@{acc['handle']})\n\n"
                            f"{clean_text[:400]}...\n\n"
                            f"❤️ {l_count:,} | [Link](https://x.com/any/status/{t_id})"
                        )
                        send_tg(msg)
                        alerts_sent += 1
                        if alerts_sent >= 2: break
            except:
                continue

        print(f"✅ Finished @{acc['handle']} ({alerts_sent} alerts sent)")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
