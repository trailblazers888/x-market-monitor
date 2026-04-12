import os
import re
import time
import random
import requests
from datetime import datetime, timezone

# Secrets (We only need Telegram now)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# Configuration
ALERT_THRESHOLD = 60
MIN_LIKES = 50

# List of working Nitter mirrors
NITTER_MIRRORS = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.no-logs.com",
    "https://nitter.projectsegfau.lt",
    "https://nitter.perennialte.ch"
]

WATCHLIST = [
    {"handle": "BillAckman", "name": "Bill Ackman", "weight": 1.0},
    {"handle": "HindenburgRes", "name": "Hindenburg Research", "weight": 1.0},
    {"handle": "elonmusk", "name": "Elon Musk", "weight": 1.0},
    {"handle": "unusual_whales", "name": "Unusual Whales", "weight": 0.8},
    {"handle": "zerohedge", "name": "Zero Hedge", "weight": 0.6},
]

TICKER_PATTERN = re.compile(r'\$[A-Z]{1,5}\b')

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        print("Failed to send Telegram")

def scrape_nitter(handle):
    """Tries multiple mirrors to find the user's latest posts."""
    random.shuffle(NITTER_MIRRORS)
    for mirror in NITTER_MIRRORS:
        url = f"{mirror}/{handle}"
        print(f"Trying {url}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200 and "timeline-item" in response.text:
                return response.text
        except:
            continue
    return None

def parse_posts(html, acc):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    posts_found = 0
    
    for item in soup.select(".timeline-item"):
        try:
            text = item.select_one(".tweet-content").text.strip()
            # Parse likes (usually looks like '1.2K' or '500')
            likes_str = item.select_one(".icon-heart").parent.text.strip().replace(",", "")
            if 'K' in likes_str: likes = int(float(likes_str.replace('K', '')) * 1000)
            elif 'M' in likes_str: likes = int(float(likes_str.replace('M', '')) * 1000000)
            else: likes = int(likes_str) if likes_str.isdigit() else 0
            
            if likes < MIN_LIKES: continue

            # Scoring
            score = round(min(100, (len(TICKER_PATTERN.findall(text.upper())) * 10) + (acc['weight'] * 20) + (likes / 500)), 1)
            
            if score >= ALERT_THRESHOLD:
                link = item.select_one(".tweet-link")['href']
                msg = (
                    f"🚨 *High Signal Detected*\n\n"
                    f"👤 *{acc['name']}* (@{acc['handle']})\n"
                    f"📊 Score: {score}/100\n"
                    f"❤️ Likes: {likes:,}\n\n"
                    f"📝 {text[:300]}...\n\n"
                    f"🔗 [View on X](https://x.com{link})"
                )
                send_tg(msg)
                posts_found += 1
        except:
            continue
    return posts_found

def run():
    print(f"Starting scan at {datetime.now()}")
    for acc in WATCHLIST:
        html = scrape_nitter(acc['handle'])
        if html:
            found = parse_posts(html, acc)
            print(f"Found {found} alerts for @{acc['handle']}")
        else:
            print(f"Could not scrape @{acc['handle']} (All mirrors failed)")
        time.sleep(random.uniform(2, 5))

if __name__ == "__main__":
    run()
