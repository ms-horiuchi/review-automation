#!/usr/bin/env python3
"""
コードファイルとOCR結果のレビューを実行

Usage:
    python run_reviews.py

Environment Variables:
    GEMINI_API_KEY: Gemini APIキー（必須）
    GEMINI_MODEL: 使用するGeminiモデル（任意）
    REVIEW_BASE_DIR: レビュー結果の出力ベースディレクトリ（デフォルト: review）

Output:
    files_to_commit=review/yyyyMMdd_N
    review_count=5
"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime


def determine_review_dir(base_dir: str = "review") -> Path:
    """日付ベースのレビューディレクトリを決定"""
    date_dir = datetime.now().strftime("%Y%m%d")
    base_path = Path(base_dir) / date_dir
    output_dir = base_path
    index = 0
    while output_dir.exists():
        index += 1
        output_dir = Path(f"{base_path}_{index}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"レビュー結果ディレクトリ: {output_dir}", file=sys.stderr)
    return output_dir


def _has_review_targets(code_list: str = 'decoded_files.txt', ocr_list: str = 'ocr_files_list.txt') -> bool:
    """デコード済みファイルリストまたはOCRファイルリストに実際のレビュー対象が含まれているか判定する

    - 指定ファイルが存在し、かつ空行以外の行がある場合に True を返す
    - 存在しない / 空のみ の場合は False を返す
    """
    for p in (code_list, ocr_list):
        path = Path(p)
        if not path.exists():
            continue
        try:
            with path.open('r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        return True
        except Exception:
            # 何らかの理由で読めなければスキップ
            continue
    return False


def run_batch_review(file_list: str, output_dir: Path, use_prompt_map: bool = False) -> bool:
    """バッチレビューを実行"""
    if not Path(file_list).exists():
        return False
    
    try:
        cmd = [
            'python', 'scripts/gemini_cli_wrapper.py', 'batch-review',
            file_list,
            str(output_dir),
            '--default-prompt', 'docs/instruction-review.md',
            '--default-custom', 'docs/instruction-review-custom.md'
        ]
        if use_prompt_map:
            cmd.extend(['--prompt-map', 'docs/target-extensions.csv'])

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error during review: {result.stderr}", file=sys.stderr)
            return False
        
        # 標準出力をそのまま表示
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        
        return True
    except Exception as e:
        print(f"Error executing batch review: {e}", file=sys.stderr)
        return False


def count_reviews(output_dir: Path) -> int:
    """生成されたレビューファイル数をカウント"""
    return len(list(output_dir.glob('*.md')))


def main():
    # レビュー対象の有無を確認し、対象がある場合のみ GEMINI_API_KEY を必須にする
    if not _has_review_targets():
        # レビュー対象が無いので早期終了させる（GitHub Actions の後続処理に渡す出力は維持）
        print("No files to review: skip Gemini API calls", file=sys.stderr)
        print("files_to_commit=")
        print("review_count=0")
        sys.exit(0)

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY is not set", file=sys.stderr)
        sys.exit(1)
    
    # レビューディレクトリ決定
    review_base = os.getenv('REVIEW_BASE_DIR', 'review')
    output_dir = determine_review_dir(review_base)
    
    # コードファイルのレビュー
    code_files = 'decoded_files.txt'
    if Path(code_files).exists():
        print(f"コードファイルのレビューを開始: {code_files}", file=sys.stderr)
        success = run_batch_review(code_files, output_dir, use_prompt_map=True)
        if not success:
            print("Error: Batch review for code files failed.", file=sys.stderr)
            sys.exit(1)
    
    # OCR結果のレビュー
    ocr_files = 'ocr_files_list.txt'
    if Path(ocr_files).exists():
        print(f"OCR結果のレビューを開始: {ocr_files}", file=sys.stderr)
        success = run_batch_review(ocr_files, output_dir)
        if not success:
            print("Error: Batch review for OCR files failed.", file=sys.stderr)
            sys.exit(1)
    
    # 結果カウント
    review_count = count_reviews(output_dir)
    print(f"生成されたレビューファイル数: {review_count}", file=sys.stderr)
    
    # GitHub Actions出力
    if review_count > 0:
        print(f"files_to_commit={output_dir}")
        print(f"review_count={review_count}")
    else:
        print("files_to_commit=")
        print("review_count=0")


if __name__ == "__main__":
    main()
