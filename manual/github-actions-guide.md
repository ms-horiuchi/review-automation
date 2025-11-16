# GitHub Actions 利用ガイド

## 概要
このリポジトリでは、プッシュされたコミットを対象に Gemini API を用いた自動コードレビューを実行し、結果をレポジトリ内にコミットします。ワークフロー定義は `.github/workflows/gemini-review.yml` にあり、変更差分の抽出からレビュー生成、コミットまでをフルオートで行います。

## 前提条件
- **Secrets**:
  - `GEMINI_API_KEY` (必須): Google Gemini API キー。
  - `GEMINI_MODEL` (任意): 使用したいモデル名。未設定時は `scripts/gemini_cli_wrapper.py` が `gemini-2.5-flash` を既定で利用します。
- **依存ファイル**:
  - `docs/target-extensions.csv`: 監視対象のファイル拡張子を列挙した CSV。**推奨:1 行目にヘッダー**(`extension,base_prompt,custom_prompt`) を置いてください。古いフォーマット（ヘッダー無し）の CSV もサポートしますが、ヘッダー付きが推奨です（CRLF/LF どちらでも可）。
  - `docs/instruction-review.md`: 基本プロンプト。
  - `docs/instruction-review-custom.md`: ファイル種別ごとの追加指示（任意）。
- **スクリプト**: 
  - `scripts/decode_file_paths.py`: GitHub Actions の出力からファイルパスを安全に復元し、`decoded_files.txt` を生成します。
  - `scripts/gemini_cli_wrapper.py`: Gemini API にまとめて問い合わせ、レビュー結果を保存します（ただし `scripts/` 配下のコードはレビュー対象から除外されています）。

## トリガーと動作フロー
ワークフローはすべてのブランチへの Push をトリガーに実行されます。処理は以下のステップで構成されています。

1. **チェックアウト**: `actions/checkout@v4` でリポジトリを取得し、再コミット用に資格情報を保持します。
2. **Python セットアップ**: `actions/setup-python@v5` で Python 3.11 を使用。
3. **依存パッケージのインストール**: `pip install google-generativeai` を実行します。バージョンを固定したい場合は `requirements.txt` を用意し、`pip install -r` に置き換えてください。
4. **Git 設定**: `core.quotepath=false` を設定し、日本語などのファイル名をエスケープしないようにします。
5. **レビュー対象拡張子の読み込み**: `docs/target-extensions.csv` を読み込み、`tj-actions/changed-files` の `files` 入力に渡す glob パターン（`**/*.ts` など）を生成します。`tr -d '\r'` を挿んでいるため、CRLF と LF のどちらでも安全に動作します。
6. **変更ファイルの抽出**: `tj-actions/changed-files@v45` で対象拡張子の変更を洗い出し、カンマ区切りの一覧を出力します。`.d.ts` や `scripts/` 配下のファイルは明示的に除外しています。
  - 参照: 画像ファイルは `changed-images` ステップで別途抽出します。拡張子に大文字（例: `.PNG`）がある場合もカバーするため、`**/*.PNG` なども含めています。
7. **ファイル名デコード**: 変更ファイルが存在する場合のみ `scripts/decode_file_paths.py` を実行し、`decoded_files.txt` に UTF-8 のファイルリストを落とします。
8. **レビュー実行** (`review_process` step):
   - `review/YYYYMMDD` をベースに、同日に複数実行された場合は `_1`, `_2` ... を付与してユニークなディレクトリを作成します。
  - `scripts/gemini_cli_wrapper.py batch-review docs/instruction-review.md decoded_files.txt <出力パス> --custom-prompt docs/instruction-review-custom.md` を呼び出し、各ファイルのレビュー結果 (`.md`) を出力します。
  - `review_process` ステップに `set -o pipefail` を追加しているため、`scripts/run_reviews.py` や `scripts/gemini_cli_wrapper.py` の非ゼロ終了はステップ失敗として検出されます。
  - 出力された `.md` ファイル数を計測し、1 件以上あれば次ステップへディレクトリパスを共有します。
9. **コミット&プッシュ**: `stefanzweifel/git-auto-commit-action@v5` がレビュー結果ディレクトリ全体をコミットし、トリガー元と同じブランチにプッシュします。コミットメッセージは `feat: Geminiによる自動コードレビュー結果を追加 (<sha>)` です。

## 実行結果の確認
- `review/<日付>[_N]/` 配下にファイル単位のレビュー (`.md`) が保存されます。
- Actions 実行ログでは `生成されたレビューファイル数` として作成件数が表示されます。
- コミットは `gemini-cli-reviewer[bot]` ユーザーで行われます。

## カスタマイズのヒント
- **対象ファイルの変更**: `docs/target-extensions.csv` に拡張子を追記/削除してください。ヘッダーを残したままにしておけば問題ありません。
- **プロンプト変更**: `docs/instruction-review.md` または `docs/instruction-review-custom.md` を編集。`--custom-prompt` を外せばカスタム指示を無効化できます。
- **ジョブの手動実行**: `workflow_dispatch` をトリガーに追加すると Actions から手動で再実行できます。
- **出力ディレクトリ**: 別の場所へ結果を保存したい場合は `REVIEW_BASE_DIR` 環境変数を変更してください。

## トラブルシューティング
- `GEMINI_API_KEY is not set` と表示された場合は Secrets の設定を再確認してください。
  - 備考: `run_reviews.py` はレビュー対象がない場合は早期終了（非エラー）するようになっています。レビュー対象がある場合は `GEMINI_API_KEY` 未設定で `Error: GEMINI_API_KEY is not set` を出力し、非ゼロで終了します（`set -o pipefail` のためワークフローも失敗します）。
- `decoded_files.txt not found` が発生する場合、`decode-files` ステップがスキップされていないかログを確認し、`changed-files` の対象拡張子設定を見直してください。
- API 呼び出しエラーで `.md` が生成されない場合は、`review_process` ステップのログを展開し、`scripts/gemini_cli_wrapper.py` の例外メッセージを確認してください。
  - OCR について: `ocr_process` ステップは `set -o pipefail` を有効化しています。OCR の入力があるのに出力が生成されない場合、`process_ocr.py` は非ゼロで終了し、ステップは失敗します。
