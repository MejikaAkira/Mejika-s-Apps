"""
動画合成モジュール（メインコーディネーター）
画像、音声、BGMを組み合わせて動画を生成する
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from .audio_generator import AudioGenerator
from .video_synthesizer import VideoSynthesizer
from .media_processor import MediaProcessor


class VideoComposer:
    """動画合成クラス（メインコーディネーター）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        VideoComposerの初期化
        
        Args:
            config: 設定辞書
        """
        self.config = config
        self.logger = logger.bind(name="video_composer")
        
        # 動画関連の設定を取得
        self.video_settings = config.get('video', {})
        self.audio_settings = config.get('audio', {})
        
        # 出力ディレクトリ
        self.output_dir = Path(config.get('paths', {}).get('output', {}).get('videos', 'output/videos'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 一時ディレクトリ
        self.temp_dir = self.output_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # コンポーネントを初期化
        self.audio_generator = AudioGenerator(config)
        self.video_synthesizer = VideoSynthesizer(config)
        self.media_processor = MediaProcessor(config)
    
    def compose_video(self, script_data: Dict[str, Any], images_data: Any, 
                      bgm_info: Dict[str, Any]) -> str:
        """
        動画を合成
        
        Args:
            script_data: 台本データ
            images_data: 画像データ（リストまたは辞書）
            bgm_info: BGM情報
            
        Returns:
        生成された動画ファイルのパス
        """
        try:
            self.logger.info("動画合成を開始")
            
            # images_dataの形式を確認して正規化
            if isinstance(images_data, dict):
                # 辞書形式の場合、imagesキーから取得
                images_list = images_data.get("images", [])
            elif isinstance(images_data, list):
                # リスト形式の場合はそのまま使用
                images_list = images_data
            else:
                # その他の形式の場合はエラー
                raise ValueError(f"不正な画像データ形式: {type(images_data)}")
            
            # 画像・動画ファイルのリストを取得
            image_files = self._get_image_files(images_list)
            
            if not image_files:
                raise ValueError("処理可能な画像・動画ファイルが見つかりません")
            
            # 音声ファイルを生成（埋め込み動画対応）
            slide_audio_files = self.audio_generator.generate_slide_audio(script_data, images_list)
            
            # 入力ファイルの検証
            self.media_processor.validate_input_files(image_files, slide_audio_files, bgm_info)
            
            # 出力ファイルパスを設定
            output_name = script_data.get('title', 'output_video')
            output_path = self.config.get_path("paths.output.videos") / f"{output_name}.mp4"
            
            # 動画合成を実行
            self.video_synthesizer.create_slide_synchronized_video(
                image_files, slide_audio_files, bgm_info, str(output_path), script_data
            )
            
            # 出力ファイルの検証
            if not self.media_processor.validate_output_file(str(output_path)):
                raise RuntimeError("動画ファイルの生成に失敗しました")
            
            # 一時ファイルのクリーンアップ
            self._cleanup_slide_audio_files(slide_audio_files)
            
            # 結果情報を返す
            video_info = {
                'file_path': str(output_path),
                'title': script_data.get('title', 'output_video'),
                'duration': script_data.get('total_duration', 0),
                'resolution': self.video_settings.get('resolution', '1920x1080'),
                'fps': self.video_settings.get('fps', 30),
                'size_mb': output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
            }
            
            self.logger.info(f"動画合成完了: {output_path}")
            return video_info
            
        except Exception as e:
            self.logger.error(f"動画合成でエラー: {e}")
            raise
    
    def _get_image_files(self, images_data: List[Dict[str, Any]]) -> List[str]:
        """
        画像・動画ファイルのリストを取得（埋め込み動画対応版）
        
        Args:
            images_data: 画像・動画データのリスト
            
        Returns:
            画像・動画ファイルパスのリスト
        """
        image_files = []
        
        for i, image_info in enumerate(images_data):
            slide_number = image_info.get('slide_number', i + 1)
            slide_path = self._get_slide_path(image_info)
            
            if not slide_path:
                self.logger.warning(f"スライド{slide_number}のファイルが見つかりません")
                continue
            
            # 既に合成済みの動画がある場合はそれを使用
            if slide_path.name.endswith('_combined.mp4'):
                image_files.append(str(slide_path))
                self.logger.info(f"スライド{slide_number}の合成済み動画を追加: {slide_path}")
                continue
            
            # 埋め込み動画がある場合は合成を試行
            embedded_path = self._get_embedded_video_path(image_info.get('embedded_videos', []))
            if embedded_path:
                combined_path = self.video_synthesizer.create_combined_video(slide_path, embedded_path, slide_number)
                if combined_path and combined_path.exists():
                    image_files.append(str(combined_path))
                    self.logger.info(f"スライド{slide_number}の合成動画を追加: {combined_path}")
                    continue
            
            # 合成できない場合は元のファイルを使用
            image_files.append(str(slide_path))
            self.logger.info(f"スライド{slide_number}のファイルを追加: {slide_path}")
        
        self.logger.info(f"画像・動画ファイル数: {len(image_files)}")
        return image_files

    def _get_slide_path(self, image_info: Dict[str, Any]) -> Optional[Path]:
        """スライドのファイルパスを取得"""
        slide_path = image_info.get('file_path') or image_info.get('image_path')
        return Path(slide_path) if slide_path and Path(slide_path).exists() else None

    def _get_embedded_video_path(self, embedded_videos: List[Dict[str, Any]]) -> Optional[str]:
        """埋め込み動画のパスを取得"""
        for video_info in embedded_videos:
            for key in ['extracted_path', 'gif_path']:
                path = video_info.get(key)
                if path and Path(path).exists():
                    return path
        return None
    
    def _cleanup_slide_audio_files(self, slide_audio_files: Dict[int, str]):
        """スライド音声ファイルを削除"""
        for slide_num, audio_file in slide_audio_files.items():
            try:
                if Path(audio_file).exists():
                    Path(audio_file).unlink()
                    self.logger.info(f"スライド{slide_num}音声ファイル削除: {audio_file}")
            except Exception as e:
                self.logger.warning(f"スライド{slide_num}音声ファイル削除でエラー: {e}") 