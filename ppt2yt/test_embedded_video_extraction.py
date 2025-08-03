#!/usr/bin/env python3
"""
埋め込み動画の直接抽出テスト
"""
import sys
import zipfile
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.utils.media_detector import MediaDetector
from src.utils.config import config

def test_embedded_video_extraction():
    """埋め込み動画の直接抽出テスト"""
    print("=== 埋め込み動画直接抽出テスト ===")
    
    pptx_path = "samples/RMS and Overall Level.pptx"
    output_dir = config.get_path("paths.output.images")
    detector = MediaDetector()
    
    print(f"📄 テストファイル: {pptx_path}")
    print(f"📁 出力ディレクトリ: {output_dir}")
    
    # スライド5で動画を検出
    slide_number = 5
    videos = detector.detect_videos_in_slide(pptx_path, slide_number)
    
    print(f"\n🎯 スライド {slide_number} で検出された動画: {len(videos)}個")
    
    for i, video_info in enumerate(videos):
        print(f"\n--- 動画 {i+1} ---")
        for key, value in video_info.items():
            print(f"  {key}: {value}")
        
        # 埋め込み動画を抽出
        try:
            extracted_path = detector.extract_embedded_video(
                pptx_path, slide_number, video_info, output_dir
            )
            
            if extracted_path and extracted_path.exists():
                size = extracted_path.stat().st_size
                print(f"✅ 抽出成功: {extracted_path}")
                print(f"📊 ファイルサイズ: {size:,} bytes ({size/1024:.1f}KB)")
            else:
                print("❌ 抽出失敗")
                
        except Exception as e:
            print(f"❌ 抽出でエラー: {e}")
    
    # 出力ディレクトリの内容を確認
    print(f"\n📁 出力ディレクトリ内容:")
    if output_dir.exists():
        for file_path in output_dir.glob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                print(f"  📄 {file_path.name} ({size:,} bytes)")

def test_manual_extraction():
    """手動での動画抽出テスト"""
    print("\n=== 手動動画抽出テスト ===")
    
    pptx_path = "samples/RMS and Overall Level.pptx"
    output_dir = Path("output/images")
    
    try:
        with zipfile.ZipFile(pptx_path, 'r') as pptx_zip:
            # media1.mp4を直接抽出
            media_path = 'ppt/media/media1.mp4'
            
            if media_path in pptx_zip.namelist():
                print(f"✅ {media_path} が見つかりました")
                
                # 動画データを読み込み
                video_data = pptx_zip.read(media_path)
                print(f"📊 動画サイズ: {len(video_data):,} bytes ({len(video_data)/1024:.1f}KB)")
                
                # 出力ファイル
                output_path = output_dir / "extracted_media1.mp4"
                output_path.write_bytes(video_data)
                
                if output_path.exists():
                    size = output_path.stat().st_size
                    print(f"✅ 抽出成功: {output_path}")
                    print(f"📊 出力サイズ: {size:,} bytes")
                else:
                    print("❌ ファイル保存に失敗")
            else:
                print(f"❌ {media_path} が見つかりません")
                
    except Exception as e:
        print(f"❌ 手動抽出でエラー: {e}")

if __name__ == "__main__":
    test_embedded_video_extraction()
    test_manual_extraction() 