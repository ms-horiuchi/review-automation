#!/usr/bin/env python3
"""
target-extensions.csvから拡張子パターンを生成

Usage:
    python load_extensions.py [csv_path]

Output:
    **/*.ts
    **/*.js
    ...
"""
import csv
import sys


def load_extension_patterns(csv_path: str = "docs/target-extensions.csv"):
    """CSVから拡張子を読み込み、globパターンを生成"""
    patterns = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            # Try DictReader first (CSV with header: extension,base_prompt,custom_prompt)
            reader = csv.DictReader(f)
            if 'extension' in reader.fieldnames:
                for row in reader:
                    ext = row.get('extension', '').strip()
                    if ext:
                        patterns.append(f"**/*{ext}")
            else:
                # Fallback: no header, read first column from raw rows
                f.seek(0)
                for row in csv.reader(f):
                    if not row:
                        continue
                    ext = row[0].strip()
                    if ext:
                        patterns.append(f"**/*{ext}")
    except FileNotFoundError:
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not patterns:
        print("Warning: No extensions found in CSV", file=sys.stderr)
    
    return '\n'.join(patterns)


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "docs/target-extensions.csv"
    print(load_extension_patterns(csv_path))
