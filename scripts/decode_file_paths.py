#!/usr/bin/env python3
import os
import sys

def decode_file_paths(raw_files_string, output_file='decoded_files.txt'):
    """
    エスケープされたファイルパス文字列をデコードしてファイルに出力
    
    Args:
        raw_files_string: カンマ区切りのファイルパス文字列
        output_file: 出力ファイル名（デフォルト: decoded_files.txt）
    """
    if not raw_files_string:
        print("No files to decode", file=sys.stderr)
        sys.exit(0)
    
    # カンマで区切ってファイルリストを作成
    # 各ファイル名のエスケープシーケンス（8進数）をデコードまたはバックスラッシュを除去
    files = []
    for f in raw_files_string.split(','):
        f = f.strip()
        if f:
            # バックスラッシュ+8進数エスケープをデコード
            try:
                # unicode_escapeでバックスラッシュシーケンスを解釈し、
                # latin1経由でバイト列として扱い、UTF-8としてデコード
                decoded = bytes(f, 'utf-8').decode('unicode_escape').encode('latin1').decode('utf-8')
                # デコード後もバックスラッシュが残っている場合は除去
                # （GitがUTF-8文字の前にエスケープバックスラッシュを付ける場合の対応）
                if '\\' in decoded:
                    decoded = decoded.replace('\\', '')
                files.append(decoded)
            except Exception as e:
                # デコードに失敗した場合は、バックスラッシュを除去して使用
                print(f"Info: Decode failed for '{f}': {e}", file=sys.stderr)
                cleaned = f.replace('\\', '')
                print(f"Info: Using cleaned path: '{cleaned}'", file=sys.stderr)
                files.append(cleaned)
    
    # デコードされたファイルリストを出力
    if files:
        with open(output_file, 'w', encoding='utf-8') as out:
            for f in files:
                out.write(f + '\n')
        print(f"Successfully decoded {len(files)} file(s)", file=sys.stderr)
        for f in files:
            print(f"  - {f}", file=sys.stderr)
    else:
        print("No files after decoding", file=sys.stderr)

def main():
    # 環境変数から変更されたファイルの一覧を取得
    raw = os.environ.get('CHANGED_FILES_RAW', '')
    decode_file_paths(raw)

if __name__ == "__main__":
    main()
