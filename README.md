# obatahi.github.io
Just obatahi

## 公開

`index.html` が各単位の原本です。下記の初回設定を終えると、従来どおりここに追加するだけで
GitHub Actions が番号ごとの個別ページ、一覧からのリンク、サイトマップ、robots.txt を自動生成します。
生成物は `_site/` に置き、原本は変更しません。

初回導入時は Settings → Pages → Build and deployment → Source を
**GitHub Actions** に変更してください。main への変更または Actions の
「Publish obatahi」→「Run workflow」で公開します。

初回公開分（001〜083）はリポジトリ直下にも生成済みです。設定変更前は従来の
ブランチ公開でこのファイル群が配信されます。その間、ワークフローは生成と検証だけを実行し、
自動デプロイをスキップします。新しい単位も自動で公開するため、初回設定を完了してください。

手元での生成と検証：

```sh
python3 scripts/verify.py
python3 -m http.server 8000 --directory _site
```

検証に失敗した場合は公開しません。各単位の原文一致、一覧の表示テキスト、
個別ページの正規URL、内部リンク、サイトマップの全件収録を確認します。
`nehan/` はそのままコピーし、サイトマップには追加しません。

## Google Search Console

公開確認後、所有権を確認済みのプロパティで `https://obatahi.com/sitemap.xml` を送信します。
トップと個別ページをURL検査し、必要なURLのインデックス登録をリクエストします。
登録を保証する仕組みではないため、登録状況と除外理由をSearch Consoleで確認します。
