#!/usr/bin/env python3
"""
リファクタリングされたImageProcessorのテストスクリプト
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.image_processor import ImageProcessor

def main():
    print("=== ImageProcessor テスト開始 ===")
    
    # ImageProcessorを初期化
    processor = ImageProcessor()
    print("✓ ImageProcessor初期化完了")
    
    # テスト用PPTXファイル
    pptx_path = "samples/RMS and Overall Level.pptx"
    
    if not Path(pptx_path).exists():
        print(f"❌ テストファイルが見つかりません: {pptx_path}")
        return
    
    print(f"📄 処理対象ファイル: {pptx_path}")
    
    # プレゼンテーションを処理
    try:
        results = processor.process_presentation(pptx_path)
        print(f"✓ 処理完了: {len(results)} スライド")
        
        # 結果を表示
        for result in results:
            slide_num = result["slide_number"]
            file_type = result["type"]
            format_type = result["format"]
            file_path = result["file_path"]
            
            print(f"  📊 スライド {slide_num}: {file_type} ({format_type})")
            print(f"      📁 ファイル: {file_path}")
            
            if result.get("embedded_videos"):
                print(f"      🎥 埋め込み動画: {len(result['embedded_videos'])}個")
        
        # メタデータを保存
        processor.save_metadata(results)
        print("✓ メタデータ保存完了")
        
        # 出力ディレクトリの内容を確認
        output_dir = Path("output/images")
        if output_dir.exists():
            print(f"\n📁 出力ディレクトリ内容 ({output_dir}):")
            for file_path in output_dir.glob("*"):
                size = file_path.stat().st_size
                print(f"  📄 {file_path.name} ({size:,} bytes)")
        
    except Exception as e:
        print(f"❌ 処理中にエラーが発生: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 