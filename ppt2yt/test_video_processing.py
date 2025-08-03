#!/usr/bin/env python3
"""
動画処理機能のテストスクリプト
新しい動画処理機能（スライド全体をMP4として保存、埋め込み動画の正しい抽出）をテスト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.image_processor import ImageProcessor
from src.utils.config import config
from src.utils.logger import get_logger

def test_video_processing():
    """動画処理機能のテスト"""
    logger = get_logger("VideoProcessingTest")
    
    # ImageProcessorの初期化
    image_processor = ImageProcessor()
    
    # テスト用のPPTXファイルを探す
    input_dir = Path("input")
    pptx_files = list(input_dir.glob("*.pptx"))
    
    if not pptx_files:
        logger.error("テスト用のPPTXファイルが見つかりません。input/フォルダにPPTXファイルを配置してください。")
        return False
    
    # 最初のPPTXファイルを使用
    pptx_path = str(pptx_files[0])
    logger.info(f"テスト対象ファイル: {pptx_path}")
    
    try:
        # 1. 統合処理方式での動画確認テスト
        logger.info("=== 統合処理方式での動画確認テスト ===")
        images_data = image_processor.extract_slides_with_video_check(pptx_path)
        
        logger.info(f"処理されたスライド数: {len(images_data)}")
        
        # 結果の詳細を表示
        for i, image_info in enumerate(images_data):
            slide_number = image_info.get('slide_number', i + 1)
            image_type = image_info.get('type', 'unknown')
            format_type = image_info.get('format', 'unknown')
            embedded_videos = image_info.get('embedded_videos', [])
            
            logger.info(f"スライド {slide_number}:")
            logger.info(f"  タイプ: {image_type}")
            logger.info(f"  形式: {format_type}")
            logger.info(f"  埋め込み動画数: {len(embedded_videos)}")
            
            if embedded_videos:
                for j, video in enumerate(embedded_videos):
                    logger.info(f"    動画 {j+1}: {video.get('description', 'unknown')}")
                    if video.get('extracted_path'):
                        logger.info(f"      抽出パス: {video['extracted_path']}")
        
        # 2. 動画ファイルの存在確認
        logger.info("=== 動画ファイルの存在確認 ===")
        output_dir = config.get_path("paths.output.images")
        video_files = list(output_dir.glob("*.mp4"))
        gif_files = list(output_dir.glob("*.gif"))
        
        logger.info(f"生成されたMP4ファイル数: {len(video_files)}")
        logger.info(f"生成されたGIFファイル数: {len(gif_files)}")
        
        for video_file in video_files:
            logger.info(f"  MP4: {video_file.name} ({video_file.stat().st_size / 1024:.1f}KB)")
        
        for gif_file in gif_files:
            logger.info(f"  GIF: {gif_file.name} ({gif_file.stat().st_size / 1024:.1f}KB)")
        
        # 3. 設定の確認
        logger.info("=== 設定確認 ===")
        logger.info(f"動画抽出有効: {image_processor.extract_embedded_videos}")
        logger.info(f"動画形式: {image_processor.video_format}")
        logger.info(f"スライドを動画として保存: {image_processor.save_slides_as_video}")
        logger.info(f"埋め込み動画を正しく抽出: {image_processor.extract_embedded_videos_properly}")
        logger.info(f"統合処理方式: {image_processor.use_unified_processing}")
        
        logger.info("=== テスト完了 ===")
        return True
        
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {e}")
        return False

def main():
    """メイン関数"""
    print("動画処理機能テストを開始します...")
    
    success = test_video_processing()
    
    if success:
        print("✅ テストが正常に完了しました")
    else:
        print("❌ テストでエラーが発生しました")
        sys.exit(1)

if __name__ == "__main__":
    main() 