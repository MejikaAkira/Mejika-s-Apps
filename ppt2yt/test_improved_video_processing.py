#!/usr/bin/env python3
"""
改善された動画処理機能のテスト
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.image_processor.image_processor import ImageProcessor
from src.utils.config import config
from src.utils.logger import get_logger

def test_improved_video_processing():
    """改善された動画処理機能のテスト"""
    logger = get_logger("ImprovedVideoProcessingTest")
    
    print("=== 改善された動画処理機能テスト ===")
    
    # ImageProcessorの初期化
    image_processor = ImageProcessor()
    
    # テスト用のPPTXファイル
    pptx_path = "samples/RMS and Overall Level.pptx"
    
    if not Path(pptx_path).exists():
        logger.error(f"テストファイルが見つかりません: {pptx_path}")
        return False
    
    logger.info(f"テスト対象ファイル: {pptx_path}")
    
    try:
        # 統合処理方式での動画確認テスト
        logger.info("=== 改善された統合処理方式でのテスト ===")
        results = image_processor.process_presentation(pptx_path)
        
        logger.info(f"処理されたスライド数: {len(results)}")
        
        # 結果の詳細を表示
        for i, result in enumerate(results):
            slide_number = result.get('slide_number', i + 1)
            file_type = result.get('type', 'unknown')
            format_type = result.get('format', 'unknown')
            embedded_videos = result.get('embedded_videos', [])
            has_video = result.get('has_video', False)
            note = result.get('note', '')
            extractor = result.get('extractor', '')
            
            logger.info(f"スライド {slide_number}:")
            logger.info(f"  タイプ: {file_type}")
            logger.info(f"  形式: {format_type}")
            logger.info(f"  動画フラグ: {has_video}")
            logger.info(f"  埋め込み動画数: {len(embedded_videos)}")
            if note:
                logger.info(f"  注意: {note}")
            if extractor:
                logger.info(f"  抽出器: {extractor}")
            
            if embedded_videos:
                for j, video in enumerate(embedded_videos):
                    logger.info(f"    動画 {j+1}: {video.get('description', 'unknown')}")
                    if video.get('extracted_path'):
                        logger.info(f"      抽出パス: {video['extracted_path']}")
        
        # 動画ファイルの存在確認
        logger.info("=== 動画ファイルの存在確認 ===")
        output_dir = config.get_path("paths.output.images")
        video_files = list(output_dir.glob("*.mp4"))
        gif_files = list(output_dir.glob("*.gif"))
        
        logger.info(f"生成されたMP4ファイル数: {len(video_files)}")
        logger.info(f"生成されたGIFファイル数: {len(gif_files)}")
        
        for video_file in video_files:
            size = video_file.stat().st_size
            logger.info(f"  MP4: {video_file.name} ({size:,} bytes, {size/1024:.1f}KB)")
        
        for gif_file in gif_files:
            size = gif_file.stat().st_size
            logger.info(f"  GIF: {gif_file.name} ({size:,} bytes, {size/1024:.1f}KB)")
        
        # 設定の確認
        logger.info("=== 設定確認 ===")
        logger.info(f"統合処理方式: {image_processor.config.get('use_unified_processing', True)}")
        logger.info(f"スライドを動画として保存: {image_processor.config.get('save_slides_as_video', True)}")
        logger.info(f"動画抽出有効: {image_processor.config.get('extract_embedded_videos', True)}")
        
        logger.info("=== テスト完了 ===")
        return True
        
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """メイン関数"""
    print("改善された動画処理機能テストを開始します...")
    
    success = test_improved_video_processing()
    
    if success:
        print("✅ テストが正常に完了しました")
    else:
        print("❌ テストでエラーが発生しました")
        sys.exit(1)

if __name__ == "__main__":
    main() 