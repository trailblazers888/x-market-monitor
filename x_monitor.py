import os
import re
import time
import requests
import smtplib
import html
from email.mime.text import MIMEText
from datetime import datetime

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY")
EMAIL_USER         = os.getenv("EMAIL_USER")          # Gmail address that sends
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")  # Gmail App Password
EMAIL_TO           = os.getenv("EMAIL_TO") or EMAIL_USER

# 2. CONFIG
MIN_LIKES = 1
HOST = "twitter-x.p.rapidapi.com"

# 3. WATCHLIST WITH FIXED IDs
WATCHLIST = [
    {"id": "44196397",         "handle": "elonmusk",       "name": "Elon Musk"},
    {"id": "880412538625810432", "handle": "BillAckman",     "name": "Bill Ackman"},
    {"id": "1333467482",       "handle": "unusual_whales", "name": "Unusual Whales"},
    {"id": "18839785",         "handle": "zerohedge",      "name": "Zero Hedge"}
]

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def send_email(items):
    if not (EMAIL_USER and EMAIL_APP_PASSWORD):
        print("Email not configured, skipping")
        return
    date = datetime.now().strftime("%d %b %Y")
    if items:
        rows = "".join(
            f"<div style='margin:0 0 18px;padding:12px;border-left:4px solid #1d9bf0;background:#f7f9fa'>"
            f"<b>{html.escape(i['name'])}</b><br>"
            f"<div style='white-space:pre-wrap;margin:6px 0'>{html.escape(i['text'])}</div>"
            f"<small>❤️ {i['likes']:,} &nbsp;|&nbsp; <a href='https://x.com/{i['handle']}/status/{i['id']}'>Open on X</a></small></div>"
            for i in items)
    else:
        rows = "<p>No new posts found today.</p>"
    body = f"<div style='font-family:Arial,sans-serif;max-width:640px'><h2>X Market Monitor — {date}</h2>{rows}</div>"
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"X Market Monitor: {len(items)} posts — {date}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.sendmail(EMAIL_USER, [a.strip() for a in EMAIL_TO.split(",")], msg.as_string())
    print(f"📧 Email sent to {EMAIL_TO}")

def run():
    items = []
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
                break
            
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
                    
                    if TELEGRAM_BOT_TOKEN:
                        send_tg(msg)
                    items.append({"name": name_header, "handle": acc['handle'], "text": display_content, "likes": likes_count, "id": tweet_id})
                    found += 1
                    if found >= 2: break
                except:
                    continue
            
            print(f"✅ Found {found}")
            time.sleep(2)

        except Exception as e:
            print(f"❌ Error: {e}")

    send_email(items)

if __name__ == "__main__":
    run()
