# Upwork Job Monitor → LINE通知

UpworkのRSSフィードを監視して、新着案件をLINEに自動通知するツールです。
**PCなし・完全無料**でGitHub Actionsを使って15分おきに動きます。

---

## セットアップ手順（スマホのみでOK）

### Step 1: このリポジトリをGitHubにアップロード

1. [GitHub](https://github.com) でアカウントを作成（無料）
2. 新しいリポジトリを作成（名前は何でもOK、例: `upwork-bot`）
3. このフォルダの全ファイルをアップロード

---

### Step 2: UpworkのRSS URLを取得

1. [Upwork](https://www.upwork.com) にログイン
2. 「Find Work（仕事を探す）」→ キーワードや条件で検索
3. 検索結果ページのURLをコピー
   例: `https://www.upwork.com/nx/search/jobs/?q=python&sort=recency`
4. URLの末尾に `&rss=1` を付けるとRSSフィードになります
   例: `https://www.upwork.com/nx/search/jobs/?q=python&sort=recency&rss=1`

> 複数のRSSを監視したい場合は、カンマ区切りで並べます（後述）

---

### Step 3: LINE Messaging APIのトークンを取得

1. [LINE Developers](https://developers.line.biz/) にアクセス（LINEアカウントでログイン）
2. 「新規プロバイダー作成」→ 適当な名前を入力
3. 「Messaging API チャンネル」を作成
4. チャンネル設定 → 「Messaging API設定」タブ
5. **チャンネルアクセストークン**（長期）を発行してコピー → `LINE_CHANNEL_ACCESS_TOKEN`
6. [LINE Official Account Manager](https://manager.line.biz/) で作成したアカウントのQRコードを友達追加

#### LINE User IDの取得

1. LINE Developersの「Messaging API設定」タブ
2. Webhook URLに一時的に `https://webhook.site/` などを設定
3. 自分のLINEアカウントからそのボットにメッセージを送信
4. Webhookに届いたJSONの中の `source.userId` が `LINE_USER_ID` です

> 簡単な方法: チャンネル設定の「あなたのユーザーID」欄に記載されています

---

### Step 4: GitHubのSecretsに登録

1. GitHubのリポジトリ画面 → **Settings（設定）** タブ
2. 左メニュー → **Secrets and variables** → **Actions**
3. **New repository secret** ボタンを押して以下の3つを登録：

| Name（名前）| Value（値）|
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEのチャンネルアクセストークン |
| `LINE_USER_ID` | あなたのLINE User ID（`U`から始まる文字列）|
| `UPWORK_RSS_URLS` | UpworkのRSS URL（複数の場合はカンマ区切り）|

**UPWORK_RSS_URLS の例（複数監視する場合）:**
```
https://www.upwork.com/ab/feed/jobs/rss?q=python&sort=recency,https://www.upwork.com/ab/feed/jobs/rss?q=javascript&sort=recency
```

---

### Step 5: GitHub Actionsを有効化して動作確認

1. GitHubのリポジトリ → **Actions** タブ
2. 「I understand my workflows, go ahead and enable them」をクリック
3. 左メニューから **Upwork Job Monitor** を選択
4. **Run workflow** ボタンで手動実行してテスト
5. 成功すればLINEに通知が届きます！

---

## ファイル構成

```
upwork-bot/
├── main.py                          # メインスクリプト
├── requirements.txt                 # 依存ライブラリ
├── sent_jobs.json                   # 送信済みジョブID（自動生成）
└── .github/
    └── workflows/
        └── monitor.yml              # GitHub Actions設定（15分おき実行）
```

---

## よくある質問

**Q: 無料で使えますか？**
A: はい。GitHub Actionsは月2000分まで無料、LINE Messaging APIも月200通まで無料です。15分おきの実行なら月約1440回 × 数秒 = 問題なく無料枠に収まります。

**Q: 通知が来ない場合は？**
A: GitHubのActionsタブでログを確認してください。エラーメッセージが表示されます。

**Q: 監視を止めたいときは？**
A: Actions タブ → Upwork Job Monitor → 右上の「...」→「Disable workflow」

**Q: 特定のキーワードだけ通知したい場合は？**
A: UpworkのRSS URLの `q=` パラメータでキーワードを指定できます。
