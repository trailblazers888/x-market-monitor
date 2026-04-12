import os
import re
import time
import requests
from datetime import datetime

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")

# 2. CONFIG (Set these to your preference)
MIN_LIKES = 1        
ALERT_THRESHOLD = 5  
HOST = "twitter-x.p.rapidapi.com"

# 3. FULL WATCHLIST (The initial 20 accounts)
WATCHLIST = [
    {"handle": "BillAckman",       "name": "Bill Ackman",        "weight": 1.0},
    {"handle": "michaeljburry",    "name": "Michael Burry",      "weight": 1.0},
    {"handle": "RayDalio",         "name": "Ray Dalio",          "weight": 0.9},
    {"handle": "CathieDWood",      "name": "Cathie Wood",        "weight": 0.8},
    {"handle": "elonmusk",         "name": "Elon Musk",          "weight": 1.0},
    {"handle": "chamath",          "name": "Chamath Palihapitiya","weight": 0.9},
    {"handle": "StanDruckenmiller","name": "Stan Druckenmiller", "weight": 1.0},
    {"handle": "muddywatersre",    "name": "Muddy Waters",       "weight": 1.0},
    {"handle": "HindenburgRes",    "name": "Hindenburg Research","weight": 1.0},
    {"handle": "unusual_whales",   "name": "Unusual Whales",     "weight": 0.8},
    {"handle": "zerohedge",        "name": "Zero Hedge",         "weight": 0.6},
    {"handle": "KobeissiLetter",   "name": "The Kobeissi Letter","weight": 0.7},
    {"handle": "DeItaone",         "name": "Walter Bloomberg",   "weight": 0.7},
    {"handle": "LynAldenContact",  "name": "Lyn Alden",          "weight": 0.8},
    {"handle": "CitronResearch",   "name": "Citron Research",    "weight": 0.9},
    {"handle": "GothamCityRes",    "name": "Gotham City Research","weight": 0.9},
    {"handle": "NorthmanTrader",   "name": "Sven Henrich",       "weight": 0.7},
    {"handle": "ScionAsset",       "name": "Scion (Burry)",      "weight": 1.0},
    {"handle": "ScorpionReport",   "name": "Scorpion Capital",   "weight": 1.0},
    {"handle": "WolfPack_Res",     "name": "Wolfpack Research",  "weight": 1.0},
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

def run():
    print(f"--- STARTING FULL SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Scanning @{acc['handle']}...", end=" ", flush=True)
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print("❌ ID Error")
            continue

        url = f"https://{HOST}/user/tweets"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            raw_data = res.text
        except:
            print("❌ API Error")
            continue

        # DUAL-ENGINE PARSER
        # Engine 1: Find everything with 'full_text' and 'favorite_count'
        # This bypasses the Elon/Ackman folder blocks
        blocks = raw_data.split('"full_text":"')
        
        found_count = 0
        processed_ids = set()

        for block in blocks[1:]:
            try:
                text_content = block.split('","')[0]
                # Look for likes and ID in the vicinity of the text
                lk_match = re.search(r'"favorite_count":(\d+)', block)
                id_match = re.search(r'"id_str":"(\d+)"', block)
                
                if lk_match and id_match:
                    t_id = id_match.group(1)
                    if t_id in processed_ids: continue
                    processed_ids.add(t_id)

                    l_count = int(lk_match.group(1))
                    if l_count >= MIN_LIKES:
                        clean_text = text_content.encode().decode('unicode_escape', 'ignore').replace('\\n', '\n').replace('\\"', '"')
                        
                        score = (l_count / 1000) + (len(TICKER_PATTERN.findall(clean_text.upper())) * 10) + (acc['weight'] * 20)
                        score = round(min(100, score), 1)

                        if score >= ALERT_THRESHOLD:
                            msg = (f"🚨 *Signal* (@{acc['handle']})\n\n{clean_text[:400]}...\n\n"
                                   f"❤️ {l_count:,} | [Link](https://x.com/any/status/{t_id})")
                            send_tg(msg)
                            found_count += 1
                            if found_count >= 2: break
            except:
                continue

        print(f"✅ Found {found_count}")
        time.sleep(1.5) # Polite delay

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
