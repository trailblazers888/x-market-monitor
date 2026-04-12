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

# 3. WATCHLIST WITH FIXED IDs (Saves credits and prevents errors)
WATCHLIST = [
    {"id": "44196397",         "handle": "elonmusk",       "name": "Elon Musk"},
    {"id": "880412538625810432", "handle": "BillAckman",     "name": "Bill Ackman"},
    {"id": "839178970088235008", "handle": "HindenburgRes", "name": "Hindenburg Research"},
    {"id": "225130450",        "handle": "michaeljburry",  "name": "Michael Burry"},
    {"id": "131435777",        "handle": "RayDalio",       "name": "Ray Dalio"},
    {"id": "1333467482",       "handle": "unusual_whales", "name": "Unusual Whales"},
    {"handle": "zerohedge",    "id": "18839785",           "name": "Zero Hedge"}
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
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        
        try:
            res = requests.get(url, headers=headers, params={"user_id": acc['id'], "limit": "10"}, timeout=15)
            if res.status_code == 429:
                print("❌ Out of API Credits! Stop the script.")
                return
            
            raw_text = res.text
            
            # Find everything that looks like a tweet text and an ID
            # This ignores all JSON structure
            texts  = re.findall(r'"full_text":"(.*?)"', raw_text, re.DOTALL)
            ids    = re.findall(r'"id_str":"(\d+)"', raw_text)
            likes  = re.findall(r'"favorite_count":(\d+)', raw_text)

            found = 0
            for i in range(len(texts)):
                try:
                    tweet_text = texts[i].encode().decode('unicode_escape', 'ignore')
                    tweet_likes = int(likes[i]) if i < len(likes) else 0
                    tweet_id = ids[i] if i < len(ids) else "0"

                    if "RT @" in tweet_text or tweet_likes < MIN_LIKES:
                        continue

                    msg = (f"🚨 *{acc['name']}*\n\n"
                           f"{tweet_text[:400].replace('\\n', '\n')}\n\n"
                           f"❤️ {tweet_likes:,} | [Link](https://x.com/any/status/{tweet_id})")
                    
                    send_tg(msg)
                    found += 1
                    if found >= 2: break # Max 2 per person
                except:
                    continue
            
            print(f"✅ Found {found}")
            time.sleep(2)

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    run()
