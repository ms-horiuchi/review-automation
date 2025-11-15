#!/usr/bin/env python3
"""
画像ファイルをOCR処理し、テキストファイルとして出力する（pyocr版）

Usage:
    python process_ocr.py <image_files_csv> [output_dir]

Args:
    image_files_csv: カンマ区切りの画像ファイルパス
    output_dir: OCR結果の出力ベースディレクトリ（デフォルト: ocr_outputs）

Output:
    ocr_output_dir=<出力ディレクトリパス>

Requirements:
    pip install pyocr pillow
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageEnhance, ImageFilter
import pyocr
import pyocr.builders

# decode_file_paths.py から関数をインポート
from decode_file_paths import decode_file_path

# OCR画像前処理の定数
CONTRAST_ENHANCEMENT_FACTOR = 2.0


def preprocess_image(image):
    """
    OCR精度向上のための画像前処理
    
    Args:
        image: PIL.Image オブジェクト
    
    Returns:
        前処理済みのPIL.Image オブジェクト
    """
    # グレースケール化
    image = image.convert('L')
    
    # コントラスト強調
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(CONTRAST_ENHANCEMENT_FACTOR)
    
    # シャープネス強化
    image = image.filter(ImageFilter.SHARPEN)
    
    # 二値化（白黒はっきりさせる）
    threshold = 128
    image = image.point(lambda p: 255 if p > threshold else 0)
    
    return image


def process_images_to_ocr(image_files_csv: str, output_base_dir: str = "ocr_outputs"):
    """
    画像ファイルをOCR処理（pyocr使用）
    
    Args:
        image_files_csv: カンマ区切りの画像ファイルパス
        output_base_dir: OCR結果の出力ベースディレクトリ
    
    Returns:
        (出力ディレクトリパス, OCR結果ファイルリストパス)
    """
    # Tesseractの初期化
    tools = pyocr.get_available_tools()
    if len(tools) == 0:
        print("Error: No OCR tool found. Please install tesseract-ocr.", file=sys.stderr)
        return "", ""
    
    tool = tools[0]
    print(f"Using OCR tool: {tool.get_name()}", file=sys.stderr)
    
    # 日本語+英語でOCR
    langs = tool.get_available_languages()
    lang = 'jpn+eng' if 'jpn' in langs and 'eng' in langs else langs[0] if langs else 'eng'
    print(f"OCR language: {lang}", file=sys.stderr)
    
    # 出力ディレクトリの決定（yyyyMMdd形式、日本時間）
    date_dir = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    base_path = Path(output_base_dir) / date_dir
    output_dir = base_path
    index = 0
    while output_dir.exists():
        index += 1
        output_dir = Path(f"{base_path}_{index}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"OCR結果ディレクトリ: {output_dir}", file=sys.stderr)
    
    # 画像ファイルを処理（デコード処理を追加）
    raw_files = [f.strip() for f in image_files_csv.split(',') if f.strip()]
    image_files = [decode_file_path(f) for f in raw_files]
    
    if not image_files:
        print("Warning: No image files provided", file=sys.stderr)
        return "", ""
    
    print(f"Processing {len(image_files)} image file(s)...", file=sys.stderr)
    
    processed_count = 0
    
    for img_path in image_files:
        img_file = Path(img_path)
        if not img_file.exists():
            print(f"Warning: Image not found: {img_file}", file=sys.stderr)
            print(f"  Current working directory: {Path.cwd()}", file=sys.stderr)
            continue
        
        try:
            print(f"Processing: {img_file}", file=sys.stderr)
            
            # 画像を開く
            image = Image.open(img_file)
            
            # 画像前処理（精度向上）
            image = preprocess_image(image)
            
            # OCR実行
            text = tool.image_to_string(
                image,
                lang=lang,
                builder=pyocr.builders.TextBuilder()
            )
            
            # 結果を保存
            output_file = output_dir / f"{img_file.stem}.txt"
            output_file.write_text(text, encoding='utf-8')
            
            processed_count += 1
            print(f"OCR completed: {output_file.name} ({len(text)} chars)", file=sys.stderr)
            
        except Exception as e:
            print(f"Error processing {img_file}: {e}", file=sys.stderr)
    
    # 処理完了メッセージ
    print(f"Successfully processed {processed_count} of {len(image_files)} images", file=sys.stderr)
    
    # OCR結果ファイルリストを作成
    ocr_files = sorted(output_dir.glob('*.txt'))
    list_file = Path('ocr_files_list.txt')
    
    if ocr_files:
        with open(list_file, 'w', encoding='utf-8') as f:
            for txt_file in ocr_files:
                f.write(f"{txt_file}\n")
        print(f"OCR処理完了: {len(ocr_files)} ファイル生成", file=sys.stderr)
        return str(output_dir), str(list_file)
    else:
        print("Warning: OCR結果なし", file=sys.stderr)
        return "", ""


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_ocr.py <image_files_csv> [output_dir]", file=sys.stderr)
        sys.exit(1)
    
    image_files = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "ocr_outputs"
    
    ocr_dir, list_file = process_images_to_ocr(image_files, output_dir)
    
    # GitHub Actions出力用
    if ocr_dir:
        print(f"ocr_output_dir={ocr_dir}")
    else:
        print("ocr_output_dir=")


if __name__ == "__main__":
    main()
