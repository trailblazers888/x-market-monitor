import os
import re
import json
import html
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

# 1. SECRETS
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
APIFY_TOKEN        = os.getenv("APIFY_TOKEN")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")      # optional: turns on the AI market filter
GEMINI_MODELS      = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-3.6-flash"]  # tried in order
EMAIL_USER         = os.getenv("EMAIL_USER")          # Gmail address that sends
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")  # Gmail App Password
EMAIL_TO           = os.getenv("EMAIL_TO") or EMAIL_USER

# 2. CONFIG
MIN_LIKES = 1
MIN_TEXT_CHARS = 25          # posts shorter than this (after removing links) are junk
FETCH_PER_ACCOUNT = 25       # tweets read per account (cost: ~$0.00015 each)
HOURS = 30                   # only look at posts from the last 30 hours
MAX_PICKS = 8                # max posts in the email
FALLBACK_PER_ACCOUNT = 2     # used when the AI filter is off or fails
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


def readable_length(text):
    """Length of the text once links are removed."""
    return len(re.sub(r"https?://\S+", "", text or "").strip())


def keep_tweet(t, cutoff):
    text = (t.get("text") or "").strip()
    likes = int(t.get("likeCount") or 0)
    created = parse_time(t.get("createdAt") or "")
    if text.startswith("RT @") or likes < MIN_LIKES:
        return False
    if readable_length(text) < MIN_TEXT_CHARS:
        return False
    if created and created < cutoff:
        return False
    return True


def curate_with_ai(cands):
    """Ask Gemini to keep only posts that matter for financial markets."""
    lines = []
    for n, c in enumerate(cands):
        lines.append(f"[{n}] {c['name']} ({c['likes']} likes): {c['text'][:400]}")
    prompt = (
        "You help a financial planner and fund manager scan X posts for items that could "
        "move financial markets (stocks, rates, currencies, oil/commodities, crypto, major "
        "companies, central banks, tariffs, geopolitics only when it clearly affects markets).\n"
        "Skip memes, personal chatter, one-word replies, ads, and politics with no market link.\n"
        f"Choose at most {MAX_PICKS} posts, most important first. If nothing matters, return no picks.\n"
        "Reply with JSON only, in this shape:\n"
        '{"summary": "1-2 sentences on the market themes today", '
        '"picks": [{"i": 0, "why": "one short line: why it matters to markets", '
        '"watch": "assets or sectors affected"}]}\n\n'
        "POSTS:\n" + "\n".join(lines)
    )
    data, last_err = None, "no model tried"
    for model in GEMINI_MODELS:
        try:
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "content-type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json",
                                           "temperature": 0.2}},
                timeout=90)
            if res.status_code != 200:
                last_err = f"{model} HTTP {res.status_code}"
                print(f"Gemini {last_err}")
                continue
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            print(f"Gemini model used: {model}")
            break
        except Exception as e:
            last_err = f"{model}: {e}"
            print(f"Gemini error {last_err}")
    if data is None:
        raise RuntimeError(f"Gemini API failed ({last_err})")
    picks = []
    for p in (data.get("picks") or [])[:MAX_PICKS]:
        c = dict(cands[int(p["i"])])
        c["why"] = str(p.get("why", "")).strip()
        c["watch"] = str(p.get("watch", "")).strip()
        picks.append(c)
    return str(data.get("summary", "")).strip(), picks


def fallback_picks(cands):
    """Top posts by likes, a few per account."""
    picks, per = [], {}
    for c in sorted(cands, key=lambda x: x["likes"], reverse=True):
        if per.get(c["name"], 0) < FALLBACK_PER_ACCOUNT:
            per[c["name"]] = per.get(c["name"], 0) + 1
            picks.append(c)
    return picks


def send_email(picks, summary="", notes=None, ai_used=False):
    if not (EMAIL_USER and EMAIL_APP_PASSWORD):
        print("Email not configured, skipping")
        return
    notes = notes or []
    date = datetime.now().strftime("%d %b %Y")
    parts = []
    for n in notes:
        parts.append(
            "<div style='margin:0 0 14px;padding:10px 12px;background:#fff3cd;border-left:4px solid #e0a800'>"
            f"<b>&#9888;</b> {html.escape(n)}</div>")
    if summary:
        parts.append(
            "<div style='margin:0 0 18px;padding:12px;background:#eef6ff;border-left:4px solid #0b5ed7'>"
            f"<b>Market take:</b> {html.escape(summary)}</div>")
    for i in picks:
        why = ""
        if i.get("why"):
            why = f"<div style='margin:4px 0;color:#0b5ed7'><b>Why it matters:</b> {html.escape(i['why'])}</div>"
        watch = ""
        if i.get("watch"):
            watch = f"<div style='margin:2px 0;color:#555'><b>Watch:</b> {html.escape(i['watch'])}</div>"
        parts.append(
            "<div style='margin:0 0 18px;padding:12px;border-left:4px solid #1d9bf0;background:#f7f9fa'>"
            f"<b>{html.escape(i['name'])}</b><br>"
            f"<div style='white-space:pre-wrap;margin:6px 0'>{html.escape(i['text'])}</div>"
            f"{why}{watch}"
            f"<small>&#10084; {i['likes']:,} &nbsp;|&nbsp; <a href='{html.escape(i['url'])}'>Open on X</a></small></div>")
    if not picks and not notes:
        msg_line = "Nothing market-relevant today." if ai_used else "No new posts found today."
        parts.append(f"<p>{msg_line}</p>")
    body = ("<div style='font-family:Arial,sans-serif;max-width:640px'>"
            f"<h2>X Market Monitor &mdash; {date}</h2>{''.join(parts)}</div>")
    msg = MIMEText(body, "html", "utf-8")
    if notes and not picks:
        msg["Subject"] = f"X Market Monitor: PROBLEM - {date}"
    else:
        label = "market-relevant posts" if ai_used else "posts"
        msg["Subject"] = f"X Market Monitor: {len(picks)} {label} - {date}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.sendmail(EMAIL_USER, [a.strip() for a in EMAIL_TO.split(",")], msg.as_string())
    print(f"Email sent to {EMAIL_TO}")


def run():
    now = datetime.now(timezone.utc)
    print(f"--- SCAN START: {now} ---")
    cands, notes = [], []

    if not APIFY_TOKEN:
        notes.append("APIFY_TOKEN secret is missing.")
    else:
        cutoff = now - timedelta(hours=HOURS)
        seen = set()
        for acc in WATCHLIST:
            print(f"Scanning {acc['name']}...")
            try:
                tweets = fetch_tweets(acc["handle"])
            except ApifyProblem as e:
                notes.append(str(e))
                print(f"Problem: {e}")
                break
            except Exception as e:
                print(f"Error on {acc['name']}: {e}")
                notes.append(f"Could not read {acc['name']}.")
                continue
            kept = 0
            for t in tweets:
                if not keep_tweet(t, cutoff):
                    continue
                tid = str(t.get("id", ""))
                url = t.get("url") or f"https://x.com/{acc['handle']}/status/{tid}"
                if url in seen:
                    continue
                seen.add(url)
                cands.append({"name": acc["name"], "text": (t.get("text") or "").strip()[:450],
                              "likes": int(t.get("likeCount") or 0), "url": url})
                kept += 1
            print(f"Kept {kept} of {len(tweets)}")

    summary, picks, ai_used = "", [], False
    if cands and GEMINI_API_KEY:
        try:
            summary, picks = curate_with_ai(cands)
            ai_used = True
            print(f"AI picked {len(picks)} of {len(cands)}")
        except Exception as e:
            print(f"AI filter failed: {e}")
            notes.append(f"AI filter unavailable ({e}). Showing top posts by likes instead.")
            picks = fallback_picks(cands)
    else:
        picks = fallback_picks(cands)

    for p in picks:
        why = f"\n\nWhy: {p['why']}" if p.get("why") else ""
        send_tg(f"\U0001F6A8 {p['name']}\n\n{p['text']}{why}\n\n❤ {p['likes']:,} | {p['url']}")

    try:
        send_email(picks, summary, notes, ai_used)
    except Exception as e:
        print(f"Email failed: {e}")
        raise


if __name__ == "__main__":
    run()
