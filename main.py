import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
UPWORK_SEARCH_URLS = os.environ.get("UPWORK_SEARCH_URLS", "")

SENT_JOBS_FILE = "sent_jobs.json"
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

def load_sent_jobs() -> set:
    if os.path.exists(SENT_JOBS_FILE):
        with open(SENT_JOBS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("sent_ids", []))
    return set()

def save_sent_jobs(sent_ids: set) -> None:
    with open(SENT_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump({"sent_ids": list(sent_ids)[-1000:]}, f, ensure_ascii=False, indent=2)

def make_job_id(link: str, title: str) -> str:
    raw = link or title
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def convert_to_rss_url(original_url: str) -> str:
    # ユーザーが検索画面のURLを貼っても、裏側でAPI(RSS)のURLに自動変換するハック
    parsed = urlparse(original_url)
    if "/search/jobs" in parsed.path:
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            "/ab/feed/jobs/rss",
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
    return original_url

def fetch_jobs(search_url: str) -> list[dict]:
    rss_url = convert_to_rss_url(search_url)
    print(f"  [DEBUG] 変換後URL: {rss_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    response = requests.get(rss_url, headers=headers, timeout=15)
    response.raise_for_status()

    # XMLとして高速解析
    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')

    print(f"  [DEBUG] 取得できた案件数: {len(items)}件")

    jobs = []
    for item in items:
        title = item.title.text if item.title else ""
        link = item.link.text if item.link else ""
        description = item.description.text if item.description else ""

        if not title:
            continue

        # descriptionはHTMLタグが含まれるため、テキストのみ抽出
        desc_soup = BeautifulSoup(description, 'html.parser')
        clean_desc = desc_soup.get_text(separator=' ').strip()

        # 予算の抽出
        budget = ""
        if "Budget:" in clean_desc:
            try:
                budget = clean_desc.split("Budget:")[1].split("\n")[0].strip()
            except:
                pass
        elif "Hourly Range:" in clean_desc:
            try:
                budget = clean_desc.split("Hourly Range:")[1].split("\n")[0].strip()
            except:
                pass

        jobs.append({
            "id": make_job_id(link, title),
            "title": title,
            "link": link,
            "budget": budget[:50] if budget else "記載なし",
            "summary_short": clean_desc[:200] + "...",
        })

    return jobs

def build_line_message(job: dict) -> str:
    lines = ["【新着Upwork案件】", job["title"], ""]
    if job["budget"] != "記載なし":
        lines.append(f"予算: {job['budget']}")
    lines.append(f"\n{job['summary_short']}")
    lines.append(f"\n{job['link']}")
    return "\n".join(lines)

def send_line_message(text: str) -> None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"LINE送信エラー: {resp.status_code} {resp.text}")
        resp.raise_for_status()

def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] 監視開始")

    sent_ids = load_sent_jobs()
    
    # 改行区切りで安全に分割（カンマ分割によるURL破壊を防止）
    search_urls = [u.strip() for u in UPWORK_SEARCH_URLS.split("\n") if u.strip()]

    new_count = 0
    for search_url in search_urls:
        print(f"  スクレイピング中: {search_url[:70]}...")
        try:
            jobs = fetch_jobs(search_url)
        except Exception as e:
            print(f"  スクレイピングエラー: {e}")
            continue

        for job in jobs:
            if job["id"] in sent_ids:
                continue

            message = build_line_message(job)
            try:
                send_line_message(message)
                sent_ids.add(job["id"])
                new_count += 1
                print(f"  通知送信: {job['title'][:50]}")
            except Exception as e:
                print(f"  LINE送信エラー: {e}")

    save_sent_jobs(sent_ids)
    print(f"完了: {new_count}件の新着案件を通知しました")

if __name__ == "__main__":
    main()