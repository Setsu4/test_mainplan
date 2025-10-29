# News summarization prompt experiment

このリポジトリは、ChatGPT（OpenAI API）を使ったニュース記事要約プロンプトの実験用スキャフォールドです。

README に記載する主な内容:
- 依存インストールと実行手順
- `prompts/` にあるテンプレートを編集することで API に送るプロンプトを変更する方法
- テンプレートの拡張（プレースホルダ、Jinja2）や運用上の注意点

## クイックスタート（Python）

1. 仮想環境を作って依存をインストール:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. `.env` を作成して API キーを設定:

```bash
cp .env.example .env
# .env を編集して OPENAI_API_KEY を設定してください
```

3. プロンプトテンプレートを編集（必要に応じて）:

`prompts/summarize.txt` に書いたテキストが、そのまま API に渡されます。テンプレート内の `{{ARTICLE}}` は記事本文に置換されます。

4. 動作確認（API 呼び出しをしない dry-run）:

```bash
python src/run_summary.py --csv data/sample.csv --prompt prompts/summarize.txt --dry-run
```

--dry-run ではテンプレートに差し替えたプロンプトのプレビューが表示され、CSV は編集されますが実際の API 呼び出しは行われません。

5. 実行（API キーが `.env` に設定されている場合）:

```bash
python src/run_summary.py --csv data/sample.csv --prompt prompts/summarize.txt
```

成功すると、`data/sample.csv` の `summary` カラムが埋まり、CSV は原子的に置き換えられます。

## 重要なファイルと役割
- `data/sample.csv` — 入力記事と出力要約を保持する CSV（推奨ヘッダ: `id,article,summary`）。`summary` は空で開始します。
- `prompts/summarize.txt` — 要約用のプロンプトテンプレート（ここを編集すると API に送る文面が変わります）。
- `src/run_summary.py` — CSV 読み込み → プロンプト生成 → API 呼び出し → CSV 上書き の実行ロジック。
- `src/utils.py` — `load_prompt`, `render_prompt`, `retry_backoff` を提供。テンプレートの読み込みとプレースホルダ置換を行います。
- `.env.example` — 環境変数の例（`OPENAI_API_KEY`, `OPENAI_MODEL`）

## プロンプト（テンプレート）を変更する方法

最も簡単で推奨される方法は、`prompts/summarize.txt` を編集することです。たとえば文体を変えたり、出力の長さやフォーマットを明示したりできます。

現在のテンプレートの例:

```
あなたは熟練の要約者です。以下のニュース記事を日本語で簡潔に要約してください（3 文以内）。
記事:
{{ARTICLE}}
注意: 事実を捏造しないでください。重要度の高い構成要素（いつ・どこで・誰が・何を）を必ず含めてください。
```

変更例:
- 箇条書きで出力させたい場合: 「3つの箇条書きにまとめてください」などを追加
- 出力言語を変えたい場合: 「英語で要約してください」と書く

テンプレートを複数用意して比較する場合は、`prompts/summarize_v1.txt`、`prompts/summarize_v2.txt` のようにファイルを増やし、`--prompt` で指定します。

## プレースホルダの拡張（extras）と高度化

`src/utils.py` の `render_prompt` は現在シンプルな置換を行います（`{{ARTICLE}}` と `extras` のキーを置換可能）。

例: テンプレート中に `{{LENGTH}}` を使う場合、`run_summary.py` 側で以下のように `extras` を渡す必要があります:

```py
prompt = render_prompt(prompt_template, article, extras={"LENGTH": "短め（1文）"})
```

さらに複雑なロジック（条件分岐、ループ、より安全なエスケープなど）が必要なら、`Jinja2` を導入してテンプレートレンダリングを行うことを検討してください（メリット: 表現力・可読性、デメリット: 依存追加と学習コスト）。

## 運用上の注意
- 長文記事はトークン制限にかかる可能性があるため、分割→段階的要約（セクション要約→再要約）を検討してください。
- バッチ処理時はレート制限に注意（`--batch-size` を小さく、`time.sleep` を長めに調整）。
- ローカルではまず `--dry-run` でテンプレートの挙動を確認してから実行してください。
- エラーは `errors.log` に追記されます。`OPENAI_API_KEY` の設定や `openai` パッケージのバージョンを確認してください。

## よくある変更例（すぐ使えるテンプレート案）

1) 一文要約（短く）:

```
以下のニュースを一文で簡潔にまとめてください（事実を捏造しないでください）。
記事:
{{ARTICLE}}
```

2) 3点箇条書き:

```
以下のニュースを日本語で重要な点を3つの箇条書きでまとめてください。
記事:
{{ARTICLE}}
```

3) LENGTH プレースホルダ使用例（テンプレート）:

```
要約（長さ指定: {{LENGTH}}）:
{{ARTICLE}}
```

## トラブルシュート
- 「API 呼び出しでエラー」: `errors.log` を確認。`OPENAI_API_KEY` が設定されているか、`openai` のバージョンが要件に合っているか確認してください。
- 「期待したプロンプトにならない」: `--dry-run` でテンプレートプレビューを確認。テンプレート内のプレースホルダ名の綴りをチェック。
- 「出力が長すぎる」: テンプレートで文数や文字数を明示、または `call_openai_chat` の `max_tokens` を調整。

---

必要なら、`run_summary.py` に `--length` のような CLI オプションを追加して `extras` を渡す小さなパッチを作成できます。希望があればそのパッチとテスト（`--dry-run`）を作成して動作確認まで行います。

