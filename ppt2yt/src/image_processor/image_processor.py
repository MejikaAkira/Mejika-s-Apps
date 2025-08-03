"""
画像処理モジュール（改善版）
"""
from pathlib import Path
from typing import Dict, List, Any, Optional

from .extractors import PowerPointExtractor, LibreOfficeExtractor, NativePptxExtractor
from .converters import VideoConverter, ImageConverter
from .utils import MediaDetector, FileHandler
from ..utils.config import config
from ..utils.logger import get_logger


class ImageProcessor:
    """PPTXファイルから画像を抽出・処理するクラス"""
    
    def __init__(self):
        self.logger = get_logger("ImageProcessor")
        self.config = self._load_config()
        self.output_dir = self._setup_output_dir()
        
        # コンポーネントを初期化
        self.media_detector = MediaDetector()
        self.video_converter = VideoConverter(self.config)
        self.image_converter = ImageConverter(self.config)
        self.file_handler = FileHandler(self.output_dir)
        
        # 抽出器を優先度順に初期化
        self.extractors = self._initialize_extractors()
    
    def _load_config(self) -> Dict[str, Any]:
        """設定を読み込み"""
        return {
            "resolution": config.get("video.resolution", "1920x1080"),
            "image_format": config.get("image.format", "png"),
            "image_quality": config.get("image.quality", 95),
            "export_width": config.get("image.export_width", 1920),
            "export_height": config.get("image.export_height", 1080),
            "extract_embedded_videos": config.get("video_processing.extract_embedded_videos", True),
            "use_unified_processing": config.get("video_processing.use_unified_processing", True),
            "save_slides_as_video": config.get("video_processing.save_slides_as_video", True),
        }
    
    def _setup_output_dir(self) -> Path:
        """出力ディレクトリをセットアップ"""
        output_dir = config.get_path("paths.output.images")
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def _initialize_extractors(self) -> List[Any]:
        """利用可能な抽出器を初期化"""
        extractors = []
        
        # 優先度順に抽出器を追加
        extractor_classes = [
            PowerPointExtractor,
            LibreOfficeExtractor,
            NativePptxExtractor
        ]
        
        for ExtractorClass in extractor_classes:
            try:
                extractor = ExtractorClass(self.output_dir, self.config)
                if extractor.is_available():
                    extractors.append(extractor)
                    self.logger.info(f"{ExtractorClass.__name__} が利用可能です")
            except Exception as e:
                self.logger.warning(f"{ExtractorClass.__name__} の初期化に失敗: {e}")
        
        if not extractors:
            self.logger.error("利用可能な抽出器がありません")
        
        return extractors
    
    def process_presentation(self, pptx_path: str) -> List[Dict[str, Any]]:
        """
        プレゼンテーション全体を処理
        
        Args:
            pptx_path: PPTXファイルのパス
            
        Returns:
            処理結果のリスト
        """
        self.logger.info(f"プレゼンテーションの処理を開始: {pptx_path}")
        
        if not self.extractors:
            self.logger.error("利用可能な抽出器がありません")
            return []
        
        if self.config.get("use_unified_processing"):
            return self._process_with_video_detection(pptx_path)
        else:
            return self._process_standard(pptx_path)
    
    def _process_with_video_detection(self, pptx_path: str) -> List[Dict[str, Any]]:
        """動画検出を含む処理"""
        results = []
        
        # スライド数を取得
        slide_count = self._get_slide_count(pptx_path)
        if slide_count == 0:
            self.logger.error("スライドが見つかりません")
            return []
        
        for slide_number in range(1, slide_count + 1):
            self.logger.info(f"=== スライド {slide_number}/{slide_count} の処理 ===")
            
            try:
                # 動画を検出
                videos = self.media_detector.detect_videos_in_slide(pptx_path, slide_number)
                
                if videos:
                    # 動画がある場合はMP4として保存
                    result = self._process_video_slide(pptx_path, slide_number, videos)
                else:
                    # 動画がない場合は画像として保存
                    result = self._process_image_slide(pptx_path, slide_number)
                
                if result:
                    results.append(result)
                else:
                    self.logger.warning(f"スライド {slide_number} の処理に失敗")
                    
            except Exception as e:
                self.logger.error(f"スライド {slide_number} の処理でエラー: {e}")
                continue
        
        return results
    
    def _process_video_slide(self, pptx_path: str, slide_number: int, 
                           videos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """動画を含むスライドを処理（改善版）"""
        
        # まず埋め込み動画を抽出
        embedded_videos = []
        for i, video_info in enumerate(videos):
            try:
                embedded_path = self.media_detector.extract_embedded_video(
                    pptx_path, slide_number, video_info, self.output_dir
                )
                if embedded_path:
                    video_info['extracted_path'] = str(embedded_path)
                    embedded_videos.append(video_info)
                    self.logger.info(f"埋め込み動画を抽出: {embedded_path}")
            except Exception as e:
                self.logger.error(f"埋め込み動画の抽出でエラー: {e}")
        
        # 設定を確認
        if not self.config.get("save_slides_as_video", True):
            # 動画として保存しない設定の場合は画像として処理
            result = self._process_image_slide(pptx_path, slide_number)
            if result and embedded_videos:
                result["embedded_videos"] = embedded_videos
                result["has_video"] = True
            return result
        
        # 埋め込み動画がある場合は、静止画+埋め込み動画の合成を行う
        if embedded_videos:
            self.logger.info(f"スライド{slide_number}に埋め込み動画があります。静止画+埋め込み動画の合成を行います。")
            
            # スライド全体のキャプチャ画像を保存（他のスライド同様）
            image_result = self._process_image_slide(pptx_path, slide_number)
            if not image_result:
                self.logger.error(f"スライド{slide_number}の画像保存に失敗")
                return None
            
            # 静止画+埋め込み動画の合成動画を作成
            combined_video_path = self._create_combined_slide_video(
                image_result["file_path"], 
                embedded_videos[0]["extracted_path"], 
                slide_number
            )
            
            if combined_video_path:
                return {
                    "slide_number": slide_number,
                    "file_path": str(combined_video_path),
                    "filename": combined_video_path.name,
                    "type": "video",
                    "format": "mp4",
                    "embedded_videos": embedded_videos,
                    "description": f"スライド {slide_number} （静止画+埋め込み動画合成）",
                    "extractor": "CombinedVideoExtractor"
                }
            else:
                # 合成に失敗した場合は静止画を使用
                self.logger.warning(f"スライド{slide_number}の合成に失敗。静止画を使用します。")
                image_result["embedded_videos"] = embedded_videos
                image_result["has_video"] = True
                image_result["note"] = "合成に失敗したため静止画を使用"
                return image_result
        
        # 埋め込み動画がない場合は通常の画像処理
        self.logger.info(f"スライド{slide_number}に埋め込み動画がありません。通常の画像処理を行います。")
        result = self._process_image_slide(pptx_path, slide_number)
        if result:
            result["embedded_videos"] = embedded_videos
            result["has_video"] = False
        return result
    
    def _create_combined_slide_video(self, image_path: str, embedded_video_path: str, slide_number: int) -> Optional[Path]:
        """
        静止画+埋め込み動画の合成動画を作成
        
        Args:
            image_path: 静止画のパス
            embedded_video_path: 埋め込み動画のパス
            slide_number: スライド番号
            
        Returns:
            合成された動画のパス
        """
        try:
            import subprocess
            from pathlib import Path
            
            # 出力ファイルパス
            output_path = self.output_dir / f"slide_{slide_number:02d}_combined.mp4"
            
            # 静止画表示時間（秒）
            image_duration = 3.0
            
            # 2段階の処理で合成
            # 1. 静止画を動画に変換
            temp_image_video = self.output_dir / f"temp_image_{slide_number}.mp4"
            
            # 静止画を動画に変換
            image_cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', str(image_path),
                '-t', str(image_duration),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-vf', 'scale=1920:1080',
                '-r', '30',  # フレームレートを明示的に設定
                '-shortest',  # 最短時間で終了
                str(temp_image_video)
            ]
            
            self.logger.info(f"スライド{slide_number}の静止画を動画に変換中...")
            result = subprocess.run(
                image_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                self.logger.error(f"静止画変換エラー: {result.stderr}")
                return None
            
            # 一時動画の長さを確認
            try:
                result = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(temp_image_video)],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    import json
                    info = json.loads(result.stdout)
                    duration = float(info['format']['duration'])
                    self.logger.info(f"一時動画の長さ: {duration:.2f}秒")
            except Exception as e:
                self.logger.warning(f"一時動画の長さ確認でエラー: {e}")
            
            # 2. 静止画動画と埋め込み動画を結合
            concat_list = self.output_dir / f"concat_slide_{slide_number}.txt"
            with open(concat_list, 'w', encoding='utf-8') as f:
                f.write(f"file '{temp_image_video.resolve()}'\n")
                f.write(f"file '{Path(embedded_video_path).resolve()}'\n")
            
            # FFmpegで動画を結合
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list),
                '-c', 'copy',  # 再エンコードなしで結合
                str(output_path)
            ]
            
            self.logger.info(f"スライド{slide_number}の合成動画作成開始:")
            self.logger.info(f"  静止画: {image_path} ({image_duration}秒)")
            self.logger.info(f"  埋め込み動画: {embedded_video_path}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # 一時ファイルを削除
            if temp_image_video.exists():
                temp_image_video.unlink()
            
            if result.returncode == 0:
                self.logger.info(f"スライド{slide_number}の合成動画作成完了: {output_path}")
                return output_path
            else:
                self.logger.error(f"スライド{slide_number}の合成動画作成エラー: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"スライド{slide_number}の合成動画作成でエラー: {e}")
            return None

    def _verify_video_file(self, video_path: Path) -> bool:
        """動画ファイルの検証"""
        try:
            # ファイルサイズチェック
            if not video_path.exists() or video_path.stat().st_size < 10000:
                return False
            
            # ファイル拡張子チェック
            if video_path.suffix.lower() not in ['.mp4', '.avi', '.mov', '.wmv']:
                return False
            
            # FFmpegで動画情報を確認（オプション）
            try:
                import subprocess
                result = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(video_path)],
                    capture_output=True, text=True
                )
                return result.returncode == 0
            except:
                # FFmpegが利用できない場合は基本的なチェックのみ
                return True
                
        except Exception as e:
            self.logger.error(f"動画ファイル検証でエラー: {e}")
            return False
    
    def _process_image_slide(self, pptx_path: str, slide_number: int) -> Optional[Dict[str, Any]]:
        """画像スライドを処理（単一スライド版）"""
        # 各抽出器で単一スライドの抽出を試行
        for extractor in self.extractors:
            try:
                # 単一スライド抽出メソッドがある場合は使用
                if hasattr(extractor, 'extract_single_slide'):
                    slide_info = extractor.extract_single_slide(pptx_path, slide_number)
                    if slide_info:
                        return self._format_slide_info(slide_info)
                else:
                    # フォールバック：全スライドを抽出して該当スライドを検索
                    slides = extractor.extract_slides(pptx_path)
                    for slide_info in slides:
                        if slide_info["slide_number"] == slide_number:
                            return self._format_slide_info(slide_info)
            except Exception as e:
                self.logger.error(f"{extractor.__class__.__name__} でのスライド抽出エラー: {e}")
                continue
        
        return None
    
    def _process_standard(self, pptx_path: str) -> List[Dict[str, Any]]:
        """標準的な処理（動画検出なし）"""
        for extractor in self.extractors:
            try:
                slides = extractor.extract_slides(pptx_path)
                if slides:
                    return [self._format_slide_info(slide) for slide in slides]
            except Exception as e:
                self.logger.error(f"{extractor.__class__.__name__} でエラー: {e}")
                continue
        
        self.logger.error("すべての抽出方法が失敗しました")
        return []
    
    def _format_slide_info(self, slide_info: Dict[str, Any]) -> Dict[str, Any]:
        """スライド情報を統一フォーマットに変換"""
        return {
            "slide_number": slide_info["slide_number"],
            "file_path": slide_info["image_path"],
            "filename": slide_info["filename"],
            "type": "image",
            "format": self.config["image_format"],
            "embedded_videos": [],
            "description": slide_info.get("description", f"スライド {slide_info['slide_number']}")
        }
    
    def _get_slide_count(self, pptx_path: str) -> int:
        """スライド数を取得"""
        try:
            from pptx import Presentation
            prs = Presentation(pptx_path)
            return len(prs.slides)
        except Exception as e:
            self.logger.error(f"スライド数の取得に失敗: {e}")
            return 0
    
    def save_metadata(self, results: List[Dict[str, Any]], output_path: Optional[str] = None):
        """処理結果のメタデータを保存"""
        if not output_path:
            output_path = self.output_dir / "slides_metadata.json"
        
        self.file_handler.save_json(results, output_path)
        self.logger.info(f"メタデータを保存: {output_path}")
    
    # 後方互換性のためのメソッド
    def extract_slides_as_images(self, pptx_path: str) -> List[Dict[str, Any]]:
        """後方互換性のためのメソッド"""
        return self._process_standard(pptx_path)
    
    def extract_slides_with_video_check(self, pptx_path: str) -> List[Dict[str, Any]]:
        """後方互換性のためのメソッド"""
        return self._process_with_video_detection(pptx_path)
    
    def process_images_for_script(self, pptx_path: str, script_data: Dict[str, Any], 
                                videos_info: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        台本に基づいて画像を処理（後方互換性のための修正版）
        
        Args:
            pptx_path: PPTXファイルのパス
            script_data: 台本データ
            videos_info: 既に抽出済みの動画情報（オプション）
            
        Returns:
        処理された画像情報（従来の形式）
        """
        self.logger.info("台本に基づいて画像を処理中...")
        
        # 既に動画確認済みの場合は、その情報を使用
        if videos_info:
            self.logger.info("既に動画確認済みの情報を使用します")
            images_info = videos_info
        else:
            # プレゼンテーションを処理
            images_info = self.process_presentation(pptx_path)
        
        # 台本の対話に基づいて画像のタイミングを設定
        processed_images = self._assign_timing_to_images(images_info, script_data)
        
        # メタデータを保存
        metadata_path = self.output_dir / "images_metadata.json"
        self.file_handler.save_json(processed_images, metadata_path)
        
        self.logger.info(f"画像処理完了: {len(processed_images)} 画像")
        
        # 従来の形式で返す（後方互換性のため）
        return processed_images

    def _assign_timing_to_images(self, images_info: List[Dict[str, Any]], 
                                script_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        画像にタイミング情報を割り当て
        
        Args:
            images_info: 画像情報のリスト
            script_data: 台本データ
            
        Returns:
            タイミング情報付きの画像リスト
        """
        processed_images = []
        
        # 台本の対話からスライドファイル名とタイミングを抽出
        slide_timings = {}
        
        for dialogue in script_data.get("dialogue", []):
            slide_file = dialogue.get("slide_file", "slide_01.png")
            timestamp = dialogue.get("timestamp", "00:00:00")
            
            # 拡張子を除いたファイル名で管理
            base_name = Path(slide_file).stem
            
            if base_name not in slide_timings:
                slide_timings[base_name] = {
                    "start_time": timestamp,
                    "end_time": timestamp
                }
            else:
                slide_timings[base_name]["end_time"] = timestamp
        
        # 画像情報にタイミングを追加し、従来の形式に変換
        for image_info in images_info:
            # ファイル名から拡張子を除いた名前を取得
            base_name = Path(image_info["filename"]).stem
            
            timing = slide_timings.get(base_name, {
                "start_time": "00:00:00",
                "end_time": "00:00:00"
            })
            
            # 従来の形式に変換（image_pathフィールドを確保）
            processed_image = {
                "slide_number": image_info["slide_number"],
                "image_path": image_info.get("file_path", image_info.get("image_path")),  # 互換性
                "filename": image_info["filename"],
                "description": image_info.get("description", f"スライド {image_info['slide_number']}"),
                "start_time": timing["start_time"],
                "end_time": timing["end_time"],
                "duration": self._calculate_duration(timing["start_time"], timing["end_time"]),
                "type": image_info.get("type", "image"),
                "format": image_info.get("format", "png"),
                "embedded_videos": image_info.get("embedded_videos", [])
            }
            
            # 動画の場合は追加情報を含める
            if image_info.get("type") == "video":
                processed_image["is_video"] = True
                processed_image["video_path"] = image_info.get("file_path")
            
            processed_images.append(processed_image)
        
        return processed_images

    def _calculate_duration(self, start_time: str, end_time: str) -> int:
        """
        時間の差を秒数で計算
        
        Args:
            start_time: 開始時間（HH:MM:SS形式）
            end_time: 終了時間（HH:MM:SS形式）
            
        Returns:
            秒数
        """
        def time_to_seconds(time_str: str) -> int:
            parts = time_str.split(':')
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        
        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time)
        
        return max(0, end_seconds - start_seconds) 