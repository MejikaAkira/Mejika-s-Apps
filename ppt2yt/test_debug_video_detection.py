#!/usr/bin/env python3
"""
動画検出機能のデバッグテスト
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.utils.media_detector import MediaDetector
from src.image_processor.image_processor import ImageProcessor

def test_video_detection():
    """動画検出機能のテスト"""
    print("=== 動画検出機能デバッグテスト ===")
    
    # MediaDetectorを初期化
    detector = MediaDetector()
    pptx_path = "samples/RMS and Overall Level.pptx"
    
    print(f"📄 テストファイル: {pptx_path}")
    
    # 各スライドで動画検出をテスト
    for slide_number in range(1, 11):
        print(f"\n--- スライド {slide_number} の動画検出 ---")
        
        try:
            videos = detector.detect_videos_in_slide(pptx_path, slide_number)
            print(f"検出された動画数: {len(videos)}")
            
            for i, video in enumerate(videos):
                print(f"  動画 {i+1}:")
                for key, value in video.items():
                    print(f"    {key}: {value}")
                    
        except Exception as e:
            print(f"❌ エラー: {e}")
    
    # ImageProcessorでの統合テスト
    print("\n=== ImageProcessor統合テスト ===")
    processor = ImageProcessor()
    
    try:
        results = processor.process_presentation(pptx_path)
        print(f"処理結果: {len(results)} スライド")
        
        for result in results:
            slide_num = result["slide_number"]
            file_type = result["type"]
            embedded_videos = result.get("embedded_videos", [])
            
            print(f"  スライド {slide_num}: {file_type}")
            if embedded_videos:
                print(f"    埋め込み動画: {len(embedded_videos)}個")
                for video in embedded_videos:
                    print(f"      - {video}")
                    
    except Exception as e:
        print(f"❌ ImageProcessorエラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_video_detection() 