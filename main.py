import asyncio
import os
import json
import hashlib
import requests
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# --- 環境変数（GitHub Secrets）から読み込み ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
UPWORK_SEARCH_URLS = os.environ["UPWORK_SEARCH_URLS"]  # カンマ区切りで複数URL指定可

SENT_JOBS_FILE = "sent_jobs.json"
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

# Upwork案件ページのセレクタ候補（構造変更に備えて複数用意）
TILE_SELECTORS = [
    "article[data-test='JobTile']",
    "section[data-test='job-tile']",
    "div[data-test='job-tile-list-item']",
    "article.job-tile",
]
TITLE_SELECTORS = [
    "h2 a[href*='/jobs/']",
    "a[href*='/jobs/~']",
    "[data-test='job-title'] a",
    "h2.job-title a",
]
DESC_SELECTORS = [
    "[data-test='job-description-text']",
    "p[data-test='description']",
    "div.description",
]
BUDGET_SELECTORS = [
    "[data-test='budget']",
    "[data-test='is-fixed-price']",
    "li[data-test='job-type-label']",
]
SKILL_SELECTORS = [
    "[data-test='TokenClamp'] span",
    "[data-test='skill']",
    "a[data-test='attr-item']",
    "span[data-test='attrs-list'] a",
]


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


async def query_first_text(element, selectors: list[str]) -> str:
    """セレクタ候補を順番に試して最初にマッチした要素のテキストを返す"""
    for sel in selectors:
        el = await element.query_selector(sel)
        if el:
            return (await el.inner_text()).strip()
    return ""


async def fetch_jobs(search_url: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        # 画像・フォントを読み込まないことで高速化
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )

        print(f"    ページ読み込み中...")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)

        # ログインリダイレクト検出
        if "/login" in page.url or "/signup" in page.url:
            print("    ⚠ ログインページにリダイレクトされました。URLを確認してください。")
            await browser.close()
            return []

        # 案件タイルが描画されるまで待機
        tile_appeared = False
        for sel in TILE_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=15000)
                tile_appeared = True
                break
            except Exception:
                continue

        if not tile_appeared:
            # JSレンダリングに少し時間を与えて再試行
            print("    タイルセレクタが見つからず、5秒待機して再試行...")
            await page.wait_for_timeout(5000)

        # 案件タイルを取得
        tiles = []
        matched_selector = ""
        for sel in TILE_SELECTORS:
            tiles = await page.query_selector_all(sel)
            if tiles:
                matched_selector = sel
                break

        print(f"    {len(tiles)}件の案件を検出（セレクタ: {matched_selector or 'なし'}）")

        jobs = []
        for tile in tiles:
            # タイトルとリンク
            title, link = "", ""
            for sel in TITLE_SELECTORS:
                el = await tile.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    href = (await el.get_attribute("href")) or ""
                    link = f"https://www.upwork.com{href}" if href.startswith("/") else href
                    break

            if not title:
                continue

            description = await query_first_text(tile, DESC_SELECTORS)
            budget = await query_first_text(tile, BUDGET_SELECTORS)

            # スキルは複数要素なので個別処理
            skills = ""
            for sel in SKILL_SELECTORS:
                els = await tile.query_selector_all(sel)
                if els:
                    texts = [(await e.inner_text()).strip() for e in els]
                    skills = ", ".join(t for t in texts if t)
                    break

            jobs.append({
                "id": make_job_id(link, title),
                "title": title,
                "link": link,
                "budget": budget,
                "skills": skills,
                "summary_short": description[:200],
            })

        await browser.close()
        return jobs


def build_line_message(job: dict) -> str:
    lines = ["【新着Upwork案件】", job["title"], ""]
    if job["budget"]:
        lines.append(f"予算: {job['budget']}")
    if job["skills"]:
        lines.append(f"スキル: {job['skills']}")
    if job["summary_short"]:
        lines.append(f"\n{job['summary_short']}...")
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


async def main_async():
    print(f"[{datetime.now(timezone.utc).isoformat()}] 監視開始")

    sent_ids = load_sent_jobs()
    search_urls = [u.strip() for u in UPWORK_SEARCH_URLS.split(",") if u.strip()]

    new_count = 0
    for search_url in search_urls:
        print(f"  スクレイピング中: {search_url[:70]}...")
        try:
            jobs = await fetch_jobs(search_url)
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


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
