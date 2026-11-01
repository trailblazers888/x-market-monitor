import os
import html
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
APIFY_TOKEN        = os.getenv("APIFY_TOKEN")
EMAIL_USER         = os.getenv("EMAIL_USER")          # Gmail address that sends
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")  # Gmail App Password
EMAIL_TO           = os.getenv("EMAIL_TO") or EMAIL_USER

# 2. CONFIG
MIN_LIKES = 1
MAX_PER_ACCOUNT = 2          # best posts kept per account
FETCH_PER_ACCOUNT = 15       # tweets read per account (cost: ~$0.00015 each)
ACTOR = "xquik~x-tweet-scraper"

# 3. WATCHLIST
WATCHLIST = [
    {"handle": "elonmusk",       "name": "Elon Musk"},
    {"handle": "BillAckman",     "name": "Bill Ackman"},
    {"handle": "unusual_whales", "name": "Unusual Whales"},
    {"handle": "zerohedge",      "name": "Zero Hedge"},
]


class ApifyProblem(Exception):
    """Raised when Apify cannot be used (credits, token, outage)."""


def send_tg(msg):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                                 "disable_web_page_preview": True}, timeout=10)
    except Exception:
        pass


def fetch_tweets(handle):
    url = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
    body = {
        "mode": "profileTweets",
        "twitterHandles": [handle],
        "maxItems": FETCH_PER_ACCOUNT,
        "tweetTypes": {"excludeReplies": True, "excludeRetweets": True},
    }
    res = requests.post(url, json=body, timeout=180,
                        headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
    if res.status_code in (402, 429):
        raise ApifyProblem("Out of Apify credits (monthly free $5 used up).")
    if res.status_code in (401, 403):
        raise ApifyProblem("Apify token rejected - please check the APIFY_TOKEN secret.")
    if res.status_code not in (200, 201):
        raise ApifyProblem(f"Apify error (HTTP {res.status_code}).")
    data = res.json()
    return data if isinstance(data, list) else []


def parse_time(value):
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        return None


def pick_posts(tweets, cutoff):
    fresh = []
    for t in tweets:
        text = (t.get("text") or "").strip()
        likes = int(t.get("likeCount") or 0)
        created = parse_time(t.get("createdAt") or "")
        if not text or text.startswith("RT @") or likes < MIN_LIKES:
            continue
        if created and created < cutoff:
            continue
        fresh.append((likes, t))
    fresh.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in fresh[:MAX_PER_ACCOUNT]]


def send_email(items, problem=None):
    if not (EMAIL_USER and EMAIL_APP_PASSWORD):
        print("Email not configured, skipping")
        return
    date = datetime.now().strftime("%d %b %Y")
    parts = []
    if problem:
        parts.append(
            "<div style='margin:0 0 18px;padding:12px;background:#fff3cd;border-left:4px solid #e0a800'>"
            f"<b>&#9888; Problem:</b> {html.escape(problem)}</div>")
    for i in items:
        parts.append(
            "<div style='margin:0 0 18px;padding:12px;border-left:4px solid #1d9bf0;background:#f7f9fa'>"
            f"<b>{html.escape(i['name'])}</b><br>"
            f"<div style='white-space:pre-wrap;margin:6px 0'>{html.escape(i['text'])}</div>"
            f"<small>&#10084; {i['likes']:,} &nbsp;|&nbsp; <a href='{html.escape(i['url'])}'>Open on X</a></small></div>")
    if not items and not problem:
        parts.append("<p>No new posts found today.</p>")
    body = ("<div style='font-family:Arial,sans-serif;max-width:640px'>"
            f"<h2>X Market Monitor &mdash; {date}</h2>{''.join(parts)}</div>")
    msg = MIMEText(body, "html", "utf-8")
    if problem and not items:
        msg["Subject"] = f"X Market Monitor: PROBLEM - {date}"
    else:
        msg["Subject"] = f"X Market Monitor: {len(items)} posts - {date}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.sendmail(EMAIL_USER, [a.strip() for a in EMAIL_TO.split(",")], msg.as_string())
    print(f"Email sent to {EMAIL_TO}")


def run():
    now = datetime.now(timezone.utc)
    print(f"--- SCAN START: {now} ---")
    items, problem = [], None

    if not APIFY_TOKEN:
        problem = "APIFY_TOKEN secret is missing."
    else:
        # Monday run also covers the weekend
        hours = 78 if now.weekday() == 0 else 30
        cutoff = now - timedelta(hours=hours)
        for acc in WATCHLIST:
            print(f"Scanning {acc['name']}...")
            try:
                tweets = fetch_tweets(acc["handle"])
            except ApifyProblem as e:
                problem = str(e)
                print(f"Problem: {problem}")
                break
            except Exception as e:
                print(f"Error on {acc['name']}: {e}")
                problem = problem or f"Could not read {acc['name']}."
                continue
            picked = pick_posts(tweets, cutoff)
            for t in picked:
                tid = str(t.get("id", ""))
                url = t.get("url") or f"https://x.com/{acc['handle']}/status/{tid}"
                text = (t.get("text") or "").strip()[:450]
                likes = int(t.get("likeCount") or 0)
                items.append({"name": acc["name"], "text": text, "likes": likes, "url": url})
                send_tg(f"\U0001F6A8 {acc['name']}\n\n{text}\n\n❤ {likes:,} | {url}")
            print(f"Found {len(picked)}")

    try:
        send_email(items, problem)
    except Exception as e:
        print(f"Email failed: {e}")
        raise


if __name__ == "__main__":
    run()
