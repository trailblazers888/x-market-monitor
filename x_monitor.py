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
HOST = "twitter-x.p.rapidapi.com"

# 3. WATCHLIST WITH FIXED IDs
WATCHLIST = [
    {"id": "44196397",         "handle": "elonmusk",       "name": "Elon Musk"},
    {"id": "880412538625810432", "handle": "BillAckman",     "name": "Bill Ackman"},
    {"id": "839178970088235008", "handle": "HindenburgRes", "name": "Hindenburg Research"},
    {"id": "225130450",        "handle": "michaeljburry",  "name": "Michael Burry"},
    {"id": "131435777",        "handle": "RayDalio",       "name": "Ray Dalio"},
    {"id": "1333467482",       "handle": "unusual_whales", "name": "Unusual Whales"},
    {"id": "18839785",         "handle": "zerohedge",      "name": "Zero Hedge"}
]

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def run():
    print(f"--- SCAN START: {datetime.now()} ---")
    if not RAPIDAPI_KEY:
        print("Error: Missing RAPIDAPI_KEY")
        return

    for acc in WATCHLIST:
        print(f"Scanning {acc['name']}...")
        
        url = f"https://{HOST}/user/tweets"
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": HOST
        }
        
        try:
            res = requests.get(url, headers=headers, params={"user_id": acc['id'], "limit": "15"}, timeout=15)
            
            if res.status_code == 429:
                print("❌ Out of API Credits!")
                return
            
            raw_data = res.text
            
            # Use split and regex for high reliability across account types
            blocks = raw_data.split('"full_text":"')
            
            found = 0
            processed_ids = set()

            for block in blocks[1:]:
                try:
                    # Extract the components
                    tweet_text = block.split('","')[0]
                    lk_match = re.search(r'"favorite_count":(\d+)', block)
                    id_match = re.search(r'"id_str":"(\d+)"', block)

                    if not lk_match or not id_match:
                        continue

                    tweet_id = id_match.group(1)
                    if tweet_id in processed_ids:
                        continue
                    processed_ids.add(tweet_id)

                    likes_count = int(lk_match.group(1))

                    # ── CLEAN TEXT LOGIC (FIXES RUBBISH SYMBOLS) ──
                    # Decode unicode escapes and fix JSON artifacts
                    clean_text = tweet_text.encode().decode('unicode_escape', 'ignore')
                    clean_text = clean_text.replace('\\n', '\n').replace('\\"', '"')

                    # ── FILTERS ──
                    if "RT @" in clean_text or likes_count < MIN_LIKES:
                        continue

                    # Create final message string safely
                    display_content = clean_text[:450]
                    name_header = acc['name']
                    
                    msg = (
                        f"🚨 *{name_header}*\n\n"
                        f"{display_content}\n\n"
                        f"❤️ {likes_count:,} | [Link](https://x.com/any/status/{tweet_id})"
                    )
                    
                    send_tg(msg)
                    found += 1
                    if found >= 2: break
                except:
                    continue
            
            print(f"✅ Found {found}")
            time.sleep(2)

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    run()
