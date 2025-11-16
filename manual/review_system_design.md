# Gemini Review Automation Design

このドキュメントは GitHub Actions ワークフロー `gemini-review.yml` と周辺スクリプトの役割をまとめた設計メモです。

## ワークフロー全体像

- **起点**: `.github/workflows/gemini-review.yml`
  - `workflow_dispatch` と `pull_request` をトリガーに実行される。
  - `tj-actions/changed-files` で変更ファイル一覧を抽出し、`scripts/decode_file_paths.py` でエンコード解除と対象拡張子フィルタを行う。
  - 生成したファイルリスト (`decoded_files.txt`) と OCR 対象 (`ocr_files_list.txt`) を成果物として保存し、レビュー実行ステップに渡す。
  - 必要な環境変数 (`GEMINI_API_KEY` など) を設定し、後述の Python スクリプトを順に呼び出す。

## Python スクリプトの役割

### `scripts/decode_file_paths.py`
- `tj-actions/changed-files` の出力を読み取り、以下を実施する。
  - Octal エスケープや UTF-8 をデコードして元のパスに復元。
  - `docs/target-extensions.csv` に記載された拡張子だけをフィルタして `decoded_files.txt` を生成。
  - 画像など OCR 対象の拡張子を `ocr_files_list.txt` に出力。

### `scripts/process_ocr.py`
- OCR 対象画像の前処理とテキスト化を担当。
  - 画像のグレースケール化や二値化などを行い精度を向上。
  - Tesseract (pyocr) を使って日本語 OCR を実行し、結果をテキストファイルとして保存。

### `scripts/load_extensions.py`
- `docs/target-extensions.csv` を読み込み、拡張子と使用するプロンプトファイルのマッピングを提供するユーティリティ。
  - 他スクリプトから再利用しやすいように単体機能に分離。

### `scripts/gemini_cli_wrapper.py`
- Gemini API (google-generativeai) を直接扱う CLI ラッパー。
  - プロンプト Markdown をアップロードし、ファイル ID を `file_data` としてレビューリクエストに添付。
  - `batch-review` サブコマンドで複数ファイルのレビューを一括生成する。
  - `docs/target-extensions.csv` から拡張子別のプロンプトセットを読み込み、該当すれば優先的に適用する。

### `scripts/run_reviews.py`
- GitHub Actions から呼び出される統括スクリプト。
  - `review/yyyyMMdd` (重複時はインデックス付き) の出力ディレクトリを作成。
  - `decoded_files.txt` (コード系) を `use_prompt_map=True` で `gemini_cli_wrapper.py batch-review` に渡し、拡張子ごとのプロンプトを利用したレビューを実行。
  - `ocr_files_list.txt` が存在すればデフォルトプロンプトのみで再度 `batch-review` を呼び出し、OCR 結果レビューを生成。
  - 変更: `run_reviews.py` はレビュー対象が無い場合に `GEMINI_API_KEY` を要求せず早期終了するようになりました（GitHub Actions上でキー未設定によるジョブ失敗を回避）。
  - 成果物 (`*.md`) の件数をカウントし、GitHub Actions の `files_to_commit` / `review_count` 出力に設定。

## プロンプト管理 (`docs/target-extensions.csv`)

- CSV 形式で `拡張子, ベースプロンプト Markdown, カスタムプロンプト Markdown` を定義。
- `gemini_cli_wrapper.py` で読み込まれ、該当拡張子のレビュー時に指定された Markdown が Gemini にアップロードされる。
  - 同一ワークフロー内で同一 Markdown を何度もアップロードしないため、アップロードしたプロンプトの File ID を `.prompt_upload_cache.json` に保存して再利用する仕組みを追加しています。
  - キャッシュはワークスペースルートに保存され、ワークフロー間の共有は行いません。ファイルは `.gitignore` に追加されています。
- CSV に未登録の拡張子はデフォルト (`instruction-review.md` / `instruction-review-custom.md`) を利用。

## 処理フロー概要

1. GitHub Actions が対象変更ファイルを決定し、`decoded_files.txt` / `ocr_files_list.txt` を生成。
2. `run_reviews.py` が出力ディレクトリを決定し、必要に応じてコードレビューと OCR レビューの 2 回 `gemini_cli_wrapper.py batch-review` を呼び出す。
3. `gemini_cli_wrapper.py` は該当プロンプト Markdown を Gemini にアップロードし、ファイル ID を添付してレビューを生成。アップロード時やその他の予期しない例外が発生した場合はエラーを stderr に出力し、プロセスは非ゼロで終了します。
  - 追加: また、同一ワークフロー内の重複アップロードを避けるため、アップロードした Markdown の File ID は `.prompt_upload_cache.json` に保存され、同一ワークフロー内で再利用されます（ワークフロー間共有は行いません）。
4. 生成されたレビュー Markdown は `review/yyyyMMdd[_N]/*.md` に保存され、件数が GitHub Actions の出力として公開される。
  - 変更: `process_ocr.py` は入力ファイルが存在するのに OCR 出力（`.txt`）が1つも生成されなかった場合、非ゼロで終了します。これにより、`set -o pipefail` が有効なステップでは OCR の失敗として検出されるようになりました。

これにより、対象拡張子ごとに適切なプロンプトを適用したレビューが自動生成される。