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
        # Search for rest_id or id in the raw text
        match = re.search(r'"rest_id":"(\d+)"', res.text)
        if not match: match = re.search(r'"id":"(\d+)"', res.text)
        return match.group(1) if match else None
    except:
        return None

def run():
    print(f"--- STARTING SCAN: {datetime.now()} ---")
    
    for acc in WATCHLIST:
        print(f"Checking @{acc['handle']}...")
        user_id = get_user_id(acc['handle'])
        
        if not user_id:
            print(f"❌ Failed to get ID for @{acc['handle']}")
            continue

        url = f"https://{HOST}/user/tweets" # Switched to main Tweets for stability
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST}
        try:
            res = requests.get(url, headers=headers, params={"user_id": user_id, "limit": "20"}, timeout=15)
            raw_text = res.text
        except:
            continue

        # ── FIXED NUCLEAR PARSER: DOTALL FLAG ADDED ──
        # re.DOTALL allows the search to find text across multiple lines/paragraphs
        tweet_blocks = raw_text.split('"legacy":')
        
        valid_tweets = []
        for block in tweet_blocks[1:]:
            try:
                # Look for full_text or text
                text_match = re.search(r'"full_text":"(.*?)"', block, re.DOTALL)
                if not text_match:
                    text_match = re.search(r'"text":"(.*?)"', block, re.DOTALL)
                
                likes_match = re.search(r'"favorite_count":(\d+)', block)
                id_match = re.search(r'"id_str":"(\d+)"', block)
                
                if text_match and likes_match and id_match:
                    # Clean up unicode and line breaks
                    raw_text_val = text_match.group(1)
                    clean_text = raw_text_val.encode().decode('unicode_escape', 'ignore')
                    
                    valid_tweets.append({
                        "text": clean_text,
                        "likes": int(likes_match.group(1)),
                        "id": id_match.group(1)
                    })
            except:
                continue

        print(f"🔍 Found {len(valid_tweets)} tweets for @{acc['handle']}")
        
        processed_ids = set()
        alerts_sent = 0

        for tweet in valid_tweets:
            t_id = tweet["id"]
            if t_id in processed_ids: continue
            processed_ids.add(t_id)

            text = tweet["text"]
            likes = tweet["likes"]

            # Scoring
            tickers = TICKER_PATTERN.findall(text.upper())
            score = (likes / 1000) + (len(tickers) * 10) + (acc['weight'] * 20)
            score = round(min(100, score), 1)

            if likes >= MIN_LIKES and score >= ALERT_THRESHOLD:
                clean_msg = text.replace('\\n', '\n').replace('\\"', '"')
                msg = (
                    f"🚨 *High Signal* (@{acc['handle']})\n\n"
                    f"{clean_msg[:450]}...\n\n"
                    f"❤️ {likes:,} | [Link](https://x.com/any/status/{t_id})"
                )
                send_tg(msg)
                alerts_sent += 1
                if alerts_sent >= 2: break 

        print(f"✅ Finished @{acc['handle']} ({alerts_sent} alerts sent)")
        time.sleep(2)

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run()
