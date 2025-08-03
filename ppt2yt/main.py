"""
PPTX to YouTube 動画自動生成システム - メイン実行ファイル
"""
import sys
import argparse
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.utils.config import config
from src.utils.logger import get_logger
from src.script_generator.script_generator import ScriptGenerator
from src.image_processor.image_processor import ImageProcessor
from src.bgm_selector import BGMSelector
from src.video_composer import VideoComposer


class PPT2YTProcessor:
    """PPTX to YouTube 動画生成のメイン処理クラス"""
    
    def __init__(self):
        """PPT2YTProcessorの初期化"""
        self.logger = get_logger("PPT2YTProcessor")
        self.script_generator = ScriptGenerator()
        self.image_processor = ImageProcessor()
        self.bgm_selector = BGMSelector(config)
        self.video_composer = VideoComposer(config)
        
        # 出力ディレクトリを作成
        self._create_output_directories()
    
    def _create_output_directories(self):
        """出力ディレクトリを作成"""
        output_paths = [
            config.get_path("paths.output.scripts"),
            config.get_path("paths.output.images"),
            config.get_path("paths.output.audio"),
            config.get_path("paths.output.videos"),
            config.get_path("paths.output.thumbnails"),
            config.get_path("paths.logs")
        ]
        
        for path in output_paths:
            if path:
                path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"ディレクトリ作成: {path}")
    
    def _archive_existing_files(self):
        """
        既存の生成ファイルをアーカイブフォルダに移動
        """
        try:
            from datetime import datetime
            import shutil
            
            # アーカイブフォルダの作成
            archive_dir = Path("output/archive")
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # タイムスタンプ付きのアーカイブフォルダ名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_subdir = archive_dir / f"archive_{timestamp}"
            archive_subdir.mkdir(exist_ok=True)
            
            # 移動対象のフォルダとファイル
            output_dirs = [
                "output/scripts",
                "output/images", 
                "output/audio",
                "output/videos",
                "output/thumbnails"
            ]
            
            moved_count = 0
            for output_dir in output_dirs:
                output_path = Path(output_dir)
                if output_path.exists() and any(output_path.iterdir()):
                    # フォルダ内のファイルをアーカイブフォルダに移動
                    for item in output_path.iterdir():
                        if item.is_file():
                            dest_path = archive_subdir / item.name
                            shutil.move(str(item), str(dest_path))
                            moved_count += 1
                            self.logger.debug(f"アーカイブ: {item} → {dest_path}")
            
            if moved_count > 0:
                self.logger.info(f"既存ファイルをアーカイブしました: {archive_subdir} ({moved_count}ファイル)")
            else:
                self.logger.info("アーカイブ対象のファイルはありませんでした")
                
        except Exception as e:
            self.logger.warning(f"アーカイブ処理でエラーが発生しました: {e}")
    
    def process_pptx(self, pptx_path: str, output_name: Optional[str] = None, progress_callback=None) -> bool:
        """
        PPTXファイルの処理を実行
        
        Args:
            pptx_path: PPTXファイルのパス
            output_name: 出力ファイル名（指定しない場合はPPTXファイル名を使用）
            
        Returns:
            処理成功フラグ
        """
        try:
            self.logger.info("PPTX to YouTube 動画生成処理を開始")
            
            # 既存ファイルのアーカイブ
            self._archive_existing_files()
            
            # 入力ファイルの検証
            pptx_file = Path(pptx_path)
            if not pptx_file.exists():
                raise FileNotFoundError(f"PPTXファイルが見つかりません: {pptx_path}")
            
            # 出力名の決定
            if output_name is None:
                output_name = pptx_file.stem
            
            # 進捗バー用のステップ定義
            steps = [
                "台本生成",
                "画像処理", 
                "BGM選定",
                "動画合成"
            ]
            
            # 進捗バーで全体の進行状況を表示
            with tqdm(total=len(steps), desc="全体進捗", unit="ステップ") as pbar:
                
                # 1. 台本生成
                self.logger.info("=== ステップ1: 台本生成 ===")
                if progress_callback:
                    progress_callback(25, "台本を生成しています...")
                script_output_path = config.get_path("paths.output.scripts") / f"{output_name}_script.json"
                
                # 動画情報を事前に取得（台本調整用）
                videos_info = []
                if self.image_processor.config.get("extract_embedded_videos", True) and self.image_processor.config.get("use_unified_processing", True):
                    self.logger.info("統合処理方式で動画情報を事前取得中...")
                    temp_images = self.image_processor.process_presentation(pptx_path)
                    for image_info in temp_images:
                        embedded_videos = image_info.get('embedded_videos', [])
                        videos_info.extend(embedded_videos)
                
                script_data = self.script_generator.generate_script(str(pptx_file), str(script_output_path), videos_info)
                
                self.logger.info(f"台本生成完了: {script_data['title']}")
                self.logger.info(f"総再生時間: {script_data['total_duration']}秒")
                self.logger.info(f"対話数: {len(script_data['dialogue'])}")
                pbar.update(1)
                
                # 2. 画像処理（動画も含む）
                self.logger.info("=== ステップ2: 画像・動画処理 ===")
                if progress_callback:
                    progress_callback(50, "スライド画像と動画を処理しています...")
                
                # 統合処理方式を使用
                if self.image_processor.config.get("use_unified_processing", True):
                    images_data = self.image_processor.process_presentation(pptx_path)
                    # 動画確認済みの情報を渡す
                    images_data = self.image_processor.process_images_for_script(pptx_path, script_data, images_data)
                else:
                    images_data = self.image_processor.process_presentation(pptx_path)
                    # 通常の画像処理
                    images_data = self.image_processor.process_images_for_script(pptx_path, script_data)
                pbar.update(1)
                
                # 3. BGM選定
                self.logger.info("=== ステップ3: BGM選定 ===")
                if progress_callback:
                    progress_callback(75, "BGMを選択しています...")
                bgm_data = self.bgm_selector.select_and_prepare_bgm(script_data['total_duration'], script_data)
                pbar.update(1)
                
                # 4. 動画合成
                self.logger.info("=== ステップ4: 動画合成 ===")
                if progress_callback:
                    progress_callback(90, "動画を合成しています...")
                video_data = self.video_composer.compose_video(script_data, images_data, bgm_data)
                pbar.update(1)
            
            # 5. サムネイル生成
            # self.logger.info("=== ステップ5: サムネイル生成 ===")
            # thumbnail_data = self.thumbnail_creator.create_thumbnail(script_data, video_data)
            
            # 6. YouTube投稿
            # self.logger.info("=== ステップ6: YouTube投稿 ===")
            # upload_result = self.youtube_uploader.upload_to_youtube(video_data, thumbnail_data, script_data)
            
            self.logger.info("処理完了（動画合成まで）")
            self.logger.info(f"動画ファイル: {video_data['file_path']}")
            self.logger.info(f"動画サイズ: {video_data['size_mb']:.1f}MB")
            return True
            
        except Exception as e:
            self.logger.error(f"処理中にエラーが発生しました: {e}")
            return False
    
    def validate_config(self) -> bool:
        """
        設定の検証
        
        Returns:
            設定が有効かどうか
        """
        try:
            config.validate_required_configs()
            self.logger.info("設定検証完了")
            return True
        except ValueError as e:
            self.logger.error(f"設定エラー: {e}")
            return False


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="PPTX to YouTube 動画自動生成システム")
    parser.add_argument("pptx_path", nargs='?', help="PPTXファイルのパス")
    parser.add_argument("-o", "--output", help="出力ファイル名（拡張子なし）")
    parser.add_argument("--validate-only", action="store_true", help="設定の検証のみ実行")
    
    args = parser.parse_args()
    
    # ロガーの初期化
    logger = get_logger("main")
    logger.info("PPTX to YouTube 動画自動生成システムを開始")
    
    try:
        # プロセッサーの初期化
        processor = PPT2YTProcessor()
        
        # 設定の検証
        if not processor.validate_config():
            logger.error("設定が無効です。.envファイルを確認してください。")
            return 1
        
        if args.validate_only:
            logger.info("設定検証のみ実行しました")
            return 0
        
        # PPTXファイルのパスを決定
        pptx_path = args.pptx_path
        if pptx_path is None:
            # inputフォルダ内のPPTXファイルを自動検索
            input_dir = Path("input")
            pptx_files = list(input_dir.glob("*.pptx"))
            if not pptx_files:
                logger.error("inputフォルダにPPTXファイルが見つかりません")
                return 1
            pptx_path = str(pptx_files[0])
            logger.info(f"自動検出されたPPTXファイル: {pptx_path}")
        else:
            # 引数で指定されたパスをワイルドカード対応で処理
            pptx_path = Path(pptx_path)
            if pptx_path.is_file():
                # 単一ファイルの場合
                pptx_path = str(pptx_path)
            elif pptx_path.is_dir():
                # ディレクトリの場合、その中のPPTXファイルを検索
                pptx_files = list(pptx_path.glob("*.pptx"))
                if not pptx_files:
                    logger.error(f"指定されたディレクトリにPPTXファイルが見つかりません: {pptx_path}")
                    return 1
                pptx_path = str(pptx_files[0])
                logger.info(f"ディレクトリから検出されたPPTXファイル: {pptx_path}")
            else:
                # ワイルドカードパターンの場合
                import glob
                matching_files = glob.glob(str(pptx_path))
                if not matching_files:
                    logger.error(f"指定されたパターンにマッチするPPTXファイルが見つかりません: {pptx_path}")
                    return 1
                pptx_path = matching_files[0]
                logger.info(f"パターンマッチで検出されたPPTXファイル: {pptx_path}")
        
        # PPTXファイルの処理
        success = processor.process_pptx(pptx_path, args.output)
        
        if success:
            logger.info("処理が正常に完了しました")
            return 0
        else:
            logger.error("処理が失敗しました")
            return 1
            
    except KeyboardInterrupt:
        logger.info("ユーザーによって処理が中断されました")
        return 1
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 