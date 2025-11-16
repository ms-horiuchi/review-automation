#!/usr/bin/env python3
import sys
import os
import time
import json
import csv
from pathlib import Path
import google.generativeai as genai
import traceback

def setup_genai():
    # 環境変数からGEMINI_API_KEYを取得
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

def wait_for_file_active(file_name, timeout=120, interval=2):
    """アップロード済みファイルが ACTIVE になるまで定期的に確認する"""
    deadline = time.time() + timeout
    while True:
        file = genai.get_file(file_name)
        state = getattr(file, "state", None)
        state_name = getattr(state, "name", state)
        if not state_name or state_name == "ACTIVE":
            return file
        if state_name == "FAILED":
            print(f"Error: File processing failed for {file_name}", file=sys.stderr)
            sys.exit(1)
        if time.time() >= deadline:
            print(f"Error: Timed out waiting for file to become ACTIVE: {file_name}", file=sys.stderr)
            sys.exit(1)
        time.sleep(interval)


PROMPT_CACHE_FILE = Path('.prompt_upload_cache.json')


def _load_prompt_cache():
    try:
        if PROMPT_CACHE_FILE.exists():
            return json.loads(PROMPT_CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:
        # 読み込み失敗時は空のキャッシュとして扱う
        pass
    return {}


def _save_prompt_cache(cache):
    try:
        PROMPT_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        # キャッシュ保存失敗は致命的ではない。ログのみ出力する
        print("Warning: Failed to write prompt cache", file=sys.stderr)


def upload_prompt_file(prompt_file_path):
    """プロンプトファイルをアップロードして file_id を返す（内部用、標準出力なし）"""
    if not os.path.exists(prompt_file_path):
        print(f"Error: Prompt file does not exist: {prompt_file_path}", file=sys.stderr)
        sys.exit(1)
    # キャッシュからチェック
    cache = _load_prompt_cache()
    abs_path = os.path.abspath(prompt_file_path)
    cached = cache.get(abs_path)
    if cached:
        try:
            # キャッシュされた file_id がすでに ACTIVE か確認
            wait_for_file_active(cached)
            print(f"Using cached prompt file ID for {prompt_file_path}: {cached}", file=sys.stderr)
            return cached
        except Exception:
            # キャッシュが無効な場合は再アップロードを行う
            pass
    file = genai.upload_file(prompt_file_path)
    file = wait_for_file_active(file.name)
    file_id = getattr(file, "name", None) or getattr(file, "file_id", None)
    if not file_id:
        print("Error: Unable to determine uploaded prompt file ID", file=sys.stderr)
        sys.exit(1)
    # キャッシュに保存
    cache[abs_path] = file_id
    _save_prompt_cache(cache)
    print(f"Uploaded prompt file. File ID: {file_id}", file=sys.stderr)
    return file_id


def upload_prompt_file_cli(prompt_file_path):
    """CLI用: プロンプトファイルをアップロードして file_id を標準出力に出力"""
    file_id = upload_prompt_file(prompt_file_path)
    print(file_id)
    return file_id


def build_prompt_file_parts(prompt_file_ids):
    """プロンプトファイル ID を Gemini で利用可能なパーツへ変換する"""
    if not prompt_file_ids:
        return []
    if isinstance(prompt_file_ids, str):
        prompt_file_ids = [prompt_file_ids]

    parts = []
    for file_id in prompt_file_ids:
        try:
            uploaded_file = wait_for_file_active(file_id)
            # Python SDK では File オブジェクトをそのまま使用する
            parts.append(uploaded_file)
        except Exception:
            print(f"Warning: Failed to load prompt file {file_id}, skipping", file=sys.stderr)
            continue
    return parts


def load_prompt_mapping(csv_path):
    """拡張子からベース/カスタムプロンプトパスへの対応表を読み込む"""
    mapping = {}
    if not csv_path:
        return mapping
    csv_path = os.path.abspath(csv_path)
    base_dir = os.path.dirname(csv_path)
    if not os.path.exists(csv_path):
        print(f"Warning: prompt map not found: {csv_path}", file=sys.stderr)
        return mapping

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            ext = row[0].strip().lower()
            if not ext:
                continue
            base_prompt = row[1].strip() if len(row) > 1 else ''
            custom_prompt = row[2].strip() if len(row) > 2 else ''
            base_path = os.path.abspath(os.path.join(base_dir, base_prompt)) if base_prompt else None
            custom_path = os.path.abspath(os.path.join(base_dir, custom_prompt)) if custom_prompt else None
            mapping[ext] = (base_path, custom_path)
    return mapping


def upload_prompt_files(prompt_paths):
    """プロンプトファイルをアップロードしてパスと file_id の対応表を返す"""
    uploaded = {}
    # 既存のキャッシュを先にロード
    cache = _load_prompt_cache()

    for prompt_path in sorted({os.path.abspath(p) for p in prompt_paths if p}):
        if not os.path.exists(prompt_path):
            print(f"Warning: Prompt file not found: {prompt_path}", file=sys.stderr)
            continue
        # キャッシュに存在すればキャッシュ値を利用
        if prompt_path in cache:
            uploaded[prompt_path] = cache.get(prompt_path)
            continue
        uploaded[prompt_path] = upload_prompt_file(prompt_path)
    return uploaded


def get_prompt_parts_for_paths(prompt_paths, uploaded_ids, cache):
    """指定したプロンプトファイルパスに対応するパーツをキャッシュ経由で取得する"""
    parts = []
    for prompt_path in prompt_paths:
        if not prompt_path:
            continue
        abs_path = os.path.abspath(prompt_path)
        file_id = uploaded_ids.get(abs_path)
        if not file_id:
            print(f"Warning: Prompt file not uploaded: {abs_path}", file=sys.stderr)
            continue
        if file_id not in cache:
            cache[file_id] = build_prompt_file_parts([file_id])
        parts.extend(cache[file_id])
    return parts

def run_review(prompt, file_path=None, model_name=None, prompt_file_ids=None):
    # 呼び出し側でモデルの明示がない場合
    if not model_name:
        # 環境変数からモデル情報を取得
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    model = genai.GenerativeModel(model_name)
    file_content = ""
    # レビュー対象のファイルがある場合、読み取り
    if file_path:
        if not os.path.exists(file_path):
            print(f"Error: File does not exist: {file_path}", file=sys.stderr)
            print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
            sys.exit(1)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                print(f"Successfully read file: {file_path} ({len(file_content)} bytes)", file=sys.stderr)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}", file=sys.stderr)
    if file_path:
        full_prompt = f"{prompt}\n\nFile: {file_path}\n\n```\n{file_content}\n```"
    else:
        full_prompt = prompt

    # prompt_file_idsが指定されている場合（リストまたは単一の文字列）
    contents = [full_prompt]
    contents.extend(build_prompt_file_parts(prompt_file_ids))
    # Print model info and the contents passed to the Gemini SDK so we can
    # verify exactly what is being sent.
    print(f"Model name variable: {model_name}", file=sys.stderr)
    print(f"Model object repr: {repr(model)}", file=sys.stderr)
    print("Contents passed to model.generate_content:", contents, file=sys.stderr)
    response = model.generate_content(contents)
    print(response.text)

def batch_review_files(
    file_list_path,
    output_dir,
    default_prompt_path=None,
    default_custom_prompt_path=None,
    prompt_map_path=None,
    model_name=None,
):
    """複数ファイルを一括レビュー（genaiの初期化は1回のみ）"""
    setup_genai()
    print("✅ Gemini APIのセットアップ完了", file=sys.stderr)

    prompt_map = load_prompt_mapping(prompt_map_path) if prompt_map_path else {}
    docs_dir = os.path.dirname(os.path.abspath(prompt_map_path)) if prompt_map_path else os.path.abspath('docs')

    prompt_paths = set()
    for path in (default_prompt_path, default_custom_prompt_path):
        if path:
            prompt_paths.add(os.path.abspath(path))

    # prompt_mapに指定されているファイルを収集
    for base_path, custom_path in prompt_map.values():
        if base_path:
            prompt_paths.add(os.path.abspath(base_path))
        if custom_path:
            prompt_paths.add(os.path.abspath(custom_path))

    # docs配下のmdファイルをすべて追加してアップロード対象にする
    docs_path = Path(docs_dir)
    if docs_path.exists():
        for md_file in docs_path.glob('*.md'):
            prompt_paths.add(str(md_file.resolve()))

    uploaded_prompt_ids = upload_prompt_files(prompt_paths)
    prompt_parts_cache = {}

    if not model_name:
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    model = genai.GenerativeModel(model_name)

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(file_list_path):
        print(f"Error: File list not found: {file_list_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_list_path, 'r', encoding='utf-8') as f:
        files = [line.strip() for line in f if line.strip()]

    print(f"Processing {len(files)} files...", file=sys.stderr)
    review_count = 0
    had_failure = False

    default_prompt_paths = [
        os.path.abspath(p)
        for p in (default_prompt_path, default_custom_prompt_path)
        if p and os.path.abspath(p) in uploaded_prompt_ids
    ]

    def resolve_prompt_paths_for_file(file_path):
        """ファイルの拡張子に基づいて使用するプロンプトファイルパスのリストを返す"""
        path_obj = Path(file_path)
        suffixes = [s.lower() for s in path_obj.suffixes]
        candidates = []
        if suffixes:
            combined = ''.join(suffixes)
            candidates.append(combined)
            for suf in reversed(suffixes):
                candidates.append(suf)
        
        # 拡張子に対応するプロンプトを検索
        for ext in candidates:
            if ext in prompt_map:
                base_path, custom_path = prompt_map[ext]
                paths = []
                # 拡張子専用のプロンプトを優先的に追加
                for candidate_path in (base_path, custom_path):
                    abs_candidate = os.path.abspath(candidate_path) if candidate_path else None
                    if abs_candidate and abs_candidate in uploaded_prompt_ids:
                        paths.append(abs_candidate)
                print(f"Info: Using extension-specific prompts for {file_path} ({ext}): {[os.path.basename(p) for p in paths]}", file=sys.stderr)
                return paths
        
        # fallback: デフォルトプロンプトを使用
        print(f"Info: No extension mapping for {file_path}, using default prompts", file=sys.stderr)
        return list(default_prompt_paths)

    for file_path in files:
        if not file_path:
            continue

        filename = os.path.basename(file_path)
        review_filename = os.path.splitext(filename)[0] + '.md'
        review_file_path = os.path.join(output_dir, review_filename)

        print(f"✅ レビュー対象: {file_path} -> {review_file_path}", file=sys.stderr)

        try:
            if not os.path.exists(file_path):
                print(f"Error: File does not exist: {file_path}", file=sys.stderr)
                with open(review_file_path, 'w', encoding='utf-8') as out:
                    out.write("自動レビューに失敗しました。ファイルが見つかりません。")
                had_failure = True
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

            full_prompt = f"File: {file_path}\n\n```\n{file_content}\n```"
            prompt_paths_for_file = resolve_prompt_paths_for_file(file_path)
            prompt_parts = get_prompt_parts_for_paths(prompt_paths_for_file, uploaded_prompt_ids, prompt_parts_cache)

            contents = [full_prompt]
            contents.extend(prompt_parts)
            # Print model info and the contents passed to the Gemini SDK so we can
            # verify exactly what is being sent.
            print(f"Model name variable: {model_name}", file=sys.stderr)
            print(f"Model object repr: {repr(model)}", file=sys.stderr)
            print("Contents passed to model.generate_content:", contents, file=sys.stderr)
            response = model.generate_content(contents)

            with open(review_file_path, 'w', encoding='utf-8') as out:
                out.write(response.text)

            review_count += 1

        except Exception as e:
            # 例外の詳細をstderrに出力し、レビュー結果ファイルにエラー内容を記録する
            tb = traceback.format_exc()
            print(f"🚨 レビュー失敗: {file_path}: {e}", file=sys.stderr)
            print(tb, file=sys.stderr)
            with open(review_file_path, 'w', encoding='utf-8') as out:
                out.write("自動レビューに失敗しました。担当者に確認してください。\n\n")
                out.write("エラー内容: ")
                out.write(f"{e}\n\n")
                out.write("トレースバック:\n")
                out.write(tb)
            had_failure = True

    print(f"完了: {review_count}/{len(files)} ファイルをレビューしました", file=sys.stderr)
    # いずれかのレビューに失敗していたら非ゼロ終了させることでGitHub Actionsを失敗させる
    if had_failure:
        print("Error: One or more reviews failed; failing process to surface as GitHub Actions failure.", file=sys.stderr)
        sys.exit(1)

    return review_count

def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  gemini ask <prompt> [--file-path <path>] [--prompt-file-id <id>]", file=sys.stderr)
        print("  gemini upload-prompt <prompt-file-path>", file=sys.stderr)
        print("  gemini batch-review <file-list-path> <output-dir> [--default-prompt <path>] [--default-custom <path>] [--prompt-map <csv-path>] [--model <model-name>]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]

    if command == "batch-review":
        # バッチレビューコマンド
        if len(sys.argv) < 4:
            print("Usage: gemini batch-review <file-list-path> <output-dir> [--default-prompt <path>] [--default-custom <path>] [--prompt-map <csv-path>] [--model <model-name>]", file=sys.stderr)
            sys.exit(1)

        file_list_path = sys.argv[2]
        output_dir = sys.argv[3]
        default_prompt_path = None
        default_custom_prompt_path = None
        prompt_map_path = None
        model_name = None

        args = sys.argv[4:]
        idx = 0
        while idx < len(args):
            arg = args[idx]
            if arg == '--default-prompt' and idx + 1 < len(args):
                default_prompt_path = args[idx + 1]
                idx += 2
                continue
            if arg == '--default-custom' and idx + 1 < len(args):
                default_custom_prompt_path = args[idx + 1]
                idx += 2
                continue
            if arg == '--prompt-map' and idx + 1 < len(args):
                prompt_map_path = args[idx + 1]
                idx += 2
                continue
            if arg == '--model' and idx + 1 < len(args):
                model_name = args[idx + 1]
                idx += 2
                continue
            print(f"Warning: Unrecognized argument {arg}", file=sys.stderr)
            idx += 1

        batch_review_files(
            file_list_path,
            output_dir,
            default_prompt_path,
            default_custom_prompt_path,
            prompt_map_path,
            model_name,
        )
        return

    # 既存のコマンド処理
    setup_genai()

    if command == "upload-prompt":
        if len(sys.argv) < 3:
            print("Usage: gemini upload-prompt <prompt-file-path>", file=sys.stderr)
            sys.exit(1)
        prompt_file_path = sys.argv[2]
        upload_prompt_file_cli(prompt_file_path)
        return

    if command != "ask":
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

    prompt = sys.argv[2] if len(sys.argv) > 2 else ""
    file_path = None
    prompt_file_ids = []
    model_name = os.getenv('GEMINI_MODEL')

    if '--file-path' in sys.argv:
        file_idx = sys.argv.index('--file-path')
        if file_idx + 1 < len(sys.argv):
            file_path = sys.argv[file_idx + 1]
    if '--prompt-file-id' in sys.argv:
        id_idx = sys.argv.index('--prompt-file-id')
        if id_idx + 1 < len(sys.argv):
            prompt_file_ids.append(sys.argv[id_idx + 1])
    if '--custom-prompt-file-id' in sys.argv:
        custom_id_idx = sys.argv.index('--custom-prompt-file-id')
        if custom_id_idx + 1 < len(sys.argv):
            prompt_file_ids.append(sys.argv[custom_id_idx + 1])

    run_review(prompt, file_path, model_name, prompt_file_ids if prompt_file_ids else None)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 予期しない例外はstderrに出力して非ゼロ終了
        print(f"Unhandled error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()