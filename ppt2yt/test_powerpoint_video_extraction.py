#!/usr/bin/env python3
"""
PowerPoint COM動画抽出機能の詳細テスト
"""
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.extractors.powerpoint import PowerPointExtractor
from src.utils.config import config

def test_powerpoint_video_extraction():
    """PowerPoint COM動画抽出の詳細テスト"""
    print("=== PowerPoint COM動画抽出テスト ===")
    
    # 設定を読み込み
    output_dir = config.get_path("paths.output.images")
    config_dict = {
        "export_width": 1920,
        "export_height": 1080,
        "resolution": "1920x1080"
    }
    
    # PowerPointExtractorを初期化
    extractor = PowerPointExtractor(output_dir, config_dict)
    
    if not extractor.is_available():
        print("❌ PowerPoint COMが利用できません")
        return
    
    print("✅ PowerPoint COMが利用可能です")
    print(f"✅ 動画抽出サポート: {extractor.can_extract_video()}")
    
    pptx_path = "samples/RMS and Overall Level.pptx"
    slide_number = 5  # 動画が含まれているスライド
    
    print(f"\n📄 テストファイル: {pptx_path}")
    print(f"🎯 対象スライド: {slide_number}")
    
    try:
        print("\n--- 動画抽出テスト ---")
        video_path = extractor.extract_slide_as_video(pptx_path, slide_number, duration=5)
        
        if video_path and video_path.exists():
            size = video_path.stat().st_size
            print(f"✅ 動画抽出成功: {video_path}")
            print(f"📊 ファイルサイズ: {size:,} bytes ({size/1024:.1f}KB)")
        else:
            print("❌ 動画抽出に失敗")
            
    except Exception as e:
        print(f"❌ 動画抽出でエラー: {e}")
        import traceback
        traceback.print_exc()
    
    # 出力ディレクトリの内容を確認
    print(f"\n📁 出力ディレクトリ内容 ({output_dir}):")
    if output_dir.exists():
        for file_path in output_dir.glob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                print(f"  📄 {file_path.name} ({size:,} bytes)")

if __name__ == "__main__":
    test_powerpoint_video_extraction() 