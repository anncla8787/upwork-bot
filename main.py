import os
import json
import hashlib
import feedparser
import requests
from datetime import datetime, timezone

# --- 環境変数（GitHub Secrets）から読み込み ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
UPWORK_RSS_URLS = os.environ["UPWORK_RSS_URLS"]  # カンマ区切りで複数URL指定可

# 既送信ジョブIDを保存するファイル（GitHub ActionsのWorkspace内）
SENT_JOBS_FILE = "sent_jobs.json"

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def load_sent_jobs() -> set:
    """送信済みジョブIDをファイルから読み込む"""
    if os.path.exists(SENT_JOBS_FILE):
        with open(SENT_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("sent_ids", []))
    return set()


def save_sent_jobs(sent_ids: set) -> None:
    """送信済みジョブIDをファイルに保存する"""
    # 最新1000件だけ保持してファイルが肥大化しないようにする
    ids_list = list(sent_ids)[-1000:]
    with open(SENT_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump({"sent_ids": ids_list}, f, ensure_ascii=False, indent=2)


def make_job_id(entry) -> str:
    """エントリからユニークなIDを生成する"""
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def fetch_jobs(rss_url: str) -> list[dict]:
    """RSSフィードから案件一覧を取得する"""
    feed = feedparser.parse(rss_url)
    jobs = []
    for entry in feed.entries:
        # HTMLタグを除去してプレーンテキスト化
        summary_html = entry.get("summary", "")
        summary = strip_html(summary_html)

        # 予算・スキルなどをsummaryから抽出
        budget = extract_field(summary, "Budget")
        skills = extract_field(summary, "Skills")

        jobs.append({
            "id": make_job_id(entry),
            "title": entry.get("title", "(タイトルなし)"),
            "link": entry.get("link", ""),
            "budget": budget,
            "skills": skills,
            "published": entry.get("published", ""),
            "summary_short": summary[:200].strip(),
        })
    return jobs


def strip_html(html: str) -> str:
    """簡易HTMLタグ除去"""
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


def extract_field(text: str, field: str) -> str:
    """
    Upwork RSSのsummaryから特定フィールドを抽出する。
    例: "Budget: $500\n" -> "$500"
    """
    import re
    pattern = rf"{field}:\s*(.+?)(?:\n|$)"
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def build_line_message(job: dict) -> str:
    """LINEに送るメッセージ文字列を組み立てる"""
    lines = [
        f"【新着Upwork案件】",
        f"{job['title']}",
        "",
    ]
    if job["budget"]:
        lines.append(f"予算: {job['budget']}")
    if job["skills"]:
        lines.append(f"スキル: {job['skills']}")
    if job["summary_short"]:
        lines.append(f"\n{job['summary_short']}...")
    lines.append(f"\n{job['link']}")
    return "\n".join(lines)


def send_line_message(text: str) -> None:
    """LINE Messaging API でプッシュメッセージを送信する"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }
    response = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
    if response.status_code != 200:
        print(f"LINE送信エラー: {response.status_code} {response.text}")
        response.raise_for_status()


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] 監視開始")

    sent_ids = load_sent_jobs()
    rss_urls = [url.strip() for url in UPWORK_RSS_URLS.split(",") if url.strip()]

    new_count = 0
    for rss_url in rss_urls:
        print(f"  RSS取得中: {rss_url[:60]}...")
        try:
            jobs = fetch_jobs(rss_url)
        except Exception as e:
            print(f"  RSS取得エラー: {e}")
            continue

        for job in jobs:
            if job["id"] in sent_ids:
                continue  # 送信済みはスキップ

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
