#!/usr/bin/env python3
import sys
import os
import time
import google.generativeai as genai

def setup_genai():
    # 環境変数からGEMINI_API_KEYを取得
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

def wait_for_file_active(file_name, timeout=120, interval=2):
    """Polls until an uploaded file becomes ACTIVE."""
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


def upload_prompt_file(prompt_file_path):
    # プロンプトファイルの設定
    if not os.path.exists(prompt_file_path):
        # プロンプトファイルがない場合終了
        print(f"Error: Prompt file does not exist: {prompt_file_path}", file=sys.stderr)
        sys.exit(1)
    file = genai.upload_file(prompt_file_path)
    # アップロード直後はPROCESSING状態のため、利用可能になるまで待機
    file = wait_for_file_active(file.name)
    # API応答によって file_id が存在しない場合があるため name をフォールバックに使う
    file_id = getattr(file, "file_id", None) or getattr(file, "name", None)
    if not file_id:
        print("Error: Unable to determine uploaded prompt file ID", file=sys.stderr)
        sys.exit(1)
    print(f"Uploaded prompt file. File ID: {file_id}", file=sys.stderr)
    # 標準出力にFile IDのみを出力（ワークフローで取得できるように）
    print(file_id)
    return file_id


def build_prompt_file_parts(prompt_file_ids):
    """Convert prompt file IDs into file_data parts consumable by Gemini."""
    if not prompt_file_ids:
        return []
    if isinstance(prompt_file_ids, str):
        prompt_file_ids = [prompt_file_ids]

    parts = []
    for file_id in prompt_file_ids:
        try:
            uploaded_file = wait_for_file_active(file_id)
        except Exception:
            print(f"Warning: Failed to load prompt file {file_id}, skipping", file=sys.stderr)
            continue
        file_uri = getattr(uploaded_file, "uri", None)
        mime_type = getattr(uploaded_file, "mime_type", "text/plain")
        if not file_uri:
            print(f"Warning: Prompt file {file_id} missing uri; skipping", file=sys.stderr)
            continue
        parts.append({
            "file_data": {
                "file_uri": file_uri,
                "mime_type": mime_type,
            }
        })
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
    response = model.generate_content(contents)
    print(response.text)

def batch_review_files(prompt_file_path, file_list_path, output_dir, custom_prompt_path=None, model_name=None):
    """
    複数ファイルを一括レビュー（genaiの初期化は1回のみ）
    
    Args:
        prompt_file_path: 共通プロンプトファイルのパス（instruction-review.md）
        file_list_path: レビュー対象ファイルのリストファイル（1行1ファイル）
        output_dir: レビュー結果の出力ディレクトリ
        custom_prompt_path: カスタムプロンプトファイルのパス（instruction-review-custom.md、オプション）
        model_name: 使用するモデル名（オプション）
    """
    # 1. genaiのセットアップ（1回のみ）
    setup_genai()
    print("✅ Gemini APIのセットアップ完了", file=sys.stderr)
    
    # 2. プロンプトファイルをアップロード（1回のみ）
    prompt_file_ids = []
    
    # 共通プロンプトをアップロード
    common_file_id = upload_prompt_file(prompt_file_path)
    prompt_file_ids.append(common_file_id)
    print(f"✅ 共通プロンプトファイルアップロード完了: File ID = {common_file_id}", file=sys.stderr)
    
    # カスタムプロンプトが指定されている場合はアップロード
    if custom_prompt_path and os.path.exists(custom_prompt_path):
        custom_file_id = upload_prompt_file(custom_prompt_path)
        prompt_file_ids.append(custom_file_id)
        print(f"✅ カスタムプロンプトファイルアップロード完了: File ID = {custom_file_id}", file=sys.stderr)
    else:
        print("ℹ️  カスタムプロンプトファイルは使用しません", file=sys.stderr)
    
    # 3. モデル名の決定
    if not model_name:
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    model = genai.GenerativeModel(model_name)
    
    # 4. 出力ディレクトリの作成
    os.makedirs(output_dir, exist_ok=True)
    
    # 5. ファイルリストを読み込み
    if not os.path.exists(file_list_path):
        print(f"Error: File list not found: {file_list_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(file_list_path, 'r', encoding='utf-8') as f:
        files = [line.strip() for line in f if line.strip()]
    
    print(f"Processing {len(files)} files...", file=sys.stderr)
    review_count = 0
    
    prompt_file_parts = build_prompt_file_parts(prompt_file_ids)

    # 6. 各ファイルをレビュー（同じgenai設定を再利用）
    for file_path in files:
        if not file_path:
            continue
        
        # レビュー結果のファイル名を決定
        filename = os.path.basename(file_path)
        review_filename = os.path.splitext(filename)[0] + ".md"
        review_file_path = os.path.join(output_dir, review_filename)
        
        print(f"✅ レビュー対象: {file_path} -> {review_file_path}", file=sys.stderr)
        
        try:
            # ファイルの内容を読み込み
            if not os.path.exists(file_path):
                print(f"Warning: File does not exist: {file_path}", file=sys.stderr)
                with open(review_file_path, 'w', encoding='utf-8') as out:
                    out.write("自動レビューに失敗しました。ファイルが見つかりません。")
                continue
            
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # プロンプトを構築
            full_prompt = f"File: {file_path}\n\n```\n{file_content}\n```"
            
            # Gemini APIを呼び出し（アップロード済みプロンプトをfilesとして添付）
            contents = [full_prompt]
            contents.extend(prompt_file_parts)
            response = model.generate_content(contents)
            
            # 結果を保存
            with open(review_file_path, 'w', encoding='utf-8') as out:
                out.write(response.text)
            
            review_count += 1
            
        except Exception as e:
            print(f"🚨 レビュー失敗: {file_path}: {e}", file=sys.stderr)
            with open(review_file_path, 'w', encoding='utf-8') as out:
                out.write("自動レビューに失敗しました。担当者に確認してください。")
    
    print(f"完了: {review_count}/{len(files)} ファイルをレビューしました", file=sys.stderr)
    return review_count

def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  gemini ask <prompt> [--file-path <path>] [--prompt-file-id <id>]", file=sys.stderr)
        print("  gemini upload-prompt <prompt-file-path>", file=sys.stderr)
        print("  gemini batch-review <prompt-file-path> <file-list-path> <output-dir> [--model <model-name>]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]

    if command == "batch-review":
        # バッチレビューコマンド
        if len(sys.argv) < 5:
            print("Usage: gemini batch-review <prompt-file-path> <file-list-path> <output-dir> [--custom-prompt <path>] [--model <model-name>]", file=sys.stderr)
            sys.exit(1)
        
        prompt_file_path = sys.argv[2]
        file_list_path = sys.argv[3]
        output_dir = sys.argv[4]
        custom_prompt_path = None
        model_name = None
        
        if '--custom-prompt' in sys.argv:
            custom_idx = sys.argv.index('--custom-prompt')
            if custom_idx + 1 < len(sys.argv):
                custom_prompt_path = sys.argv[custom_idx + 1]
        
        if '--model' in sys.argv:
            model_idx = sys.argv.index('--model')
            if model_idx + 1 < len(sys.argv):
                model_name = sys.argv[model_idx + 1]
        
        batch_review_files(prompt_file_path, file_list_path, output_dir, custom_prompt_path, model_name)
        return

    # 既存のコマンド処理
    setup_genai()

    if command == "upload-prompt":
        if len(sys.argv) < 3:
            print("Usage: gemini upload-prompt <prompt-file-path>", file=sys.stderr)
            sys.exit(1)
        prompt_file_path = sys.argv[2]
        upload_prompt_file(prompt_file_path)
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
    main()