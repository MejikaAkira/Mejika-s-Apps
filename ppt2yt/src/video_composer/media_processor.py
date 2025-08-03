"""
メディア処理モジュール
動画・音声ファイルの長さ取得、ファイル検証などの機能
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
import ffmpeg


class MediaProcessor:
    """メディア処理クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        MediaProcessorの初期化
        
        Args:
            config: 設定辞書
        """
        self.config = config
        self.logger = logger.bind(name="media_processor")
    
    def get_video_duration(self, video_path: str) -> float:
        """
        動画ファイルの長さを取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            動画の長さ（秒）
        """
        try:
            probe = ffmpeg.probe(video_path)
            if probe and 'streams' in probe and len(probe['streams']) > 0:
                # 最初のストリームの長さを取得
                duration = float(probe['streams'][0].get('duration', 0))
                return duration
            else:
                return 0.0
        except Exception as e:
            self.logger.warning(f"動画長さ取得でエラー: {e}")
            return 0.0

    def get_audio_duration(self, audio_path: str) -> float:
        """
        音声ファイルの長さを取得
        
        Args:
            audio_path: 音声ファイルパス
            
        Returns:
            音声の長さ（秒）
        """
        try:
            probe = ffmpeg.probe(audio_path)
            if probe and 'streams' in probe and len(probe['streams']) > 0:
                # 最初のストリームの長さを取得
                duration = float(probe['streams'][0].get('duration', 0))
                return duration
            else:
                return 0.0
        except Exception as e:
            self.logger.warning(f"音声長さ取得でエラー: {e}")
            return 0.0

    def validate_input_files(self, image_files: List[str], slide_audio_files: Dict[int, str], bgm_data: Dict[str, Any]):
        """
        入力ファイルの存在確認
        
        Args:
            image_files: 画像ファイルのリスト
            slide_audio_files: スライド番号 -> 音声ファイルパスの辞書
            bgm_data: BGMデータ
        """
        # 画像ファイルの確認
        for i, image_file in enumerate(image_files, 1):
            if not Path(image_file).exists():
                raise FileNotFoundError(f"画像ファイルが見つかりません: {image_file}")
            self.logger.debug(f"画像ファイル確認: {image_file}")
        
        # 音声ファイルの確認
        for slide_num, audio_file in slide_audio_files.items():
            if not Path(audio_file).exists():
                raise FileNotFoundError(f"スライド{slide_num}の音声ファイルが見つかりません: {audio_file}")
            self.logger.debug(f"音声ファイル確認: スライド{slide_num} - {audio_file}")
        
        # BGMファイルの確認（オプション）
        if bgm_data.get('file_path') and not Path(bgm_data['file_path']).exists():
            self.logger.warning(f"BGMファイルが見つかりません: {bgm_data['file_path']}")
        
        self.logger.info("入力ファイルの検証完了")

    def validate_output_file(self, output_path: str) -> bool:
        """
        出力ファイルの検証
        
        Args:
            output_path: 出力ファイルパス
            
        Returns:
            検証結果
        """
        output_file = Path(output_path)
        
        if not output_file.exists():
            raise FileNotFoundError(f"出力ファイルが作成されませんでした: {output_path}")
        
        if output_file.stat().st_size == 0:
            raise ValueError(f"出力ファイルが空です: {output_path}")
        
        # ファイルサイズの確認（最小1MB）
        min_size = 1024 * 1024  # 1MB
        if output_file.stat().st_size < min_size:
            raise ValueError(f"出力ファイルが小さすぎます: {output_file.stat().st_size} bytes")
        
        self.logger.info(f"出力ファイル検証完了: {output_path} ({output_file.stat().st_size / (1024*1024):.1f}MB)")
        return True

    def verify_video_file(self, video_path: Path) -> bool:
        """
        動画ファイルの検証
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            検証結果
        """
        try:
            if not video_path.exists():
                return False
            
            # FFmpegで動画ファイルを検証
            cmd = [
                'ffmpeg', '-v', 'error',
                '-i', str(video_path),
                '-f', 'null', '-'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.logger.info(f"動画ファイル検証成功: {video_path}")
                return True
            else:
                self.logger.warning(f"動画ファイル検証失敗: {video_path} - {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"動画ファイル検証でエラー: {e}")
            return False

    def kill_ffmpeg_processes(self):
        """FFmpegプロセスを強制終了"""
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and 'ffmpeg' in proc.info['name'].lower():
                    self.logger.info(f"FFmpegプロセスを終了: PID {proc.info['pid']}")
                    proc.terminate()
                    proc.wait(timeout=5)
        except Exception as e:
            self.logger.warning(f"FFmpegプロセス終了でエラー: {e}")

    def cleanup_temp_files(self, temp_files: List[str]):
        """
        一時ファイルの削除
        
        Args:
            temp_files: 削除する一時ファイルのリスト
        """
        for temp_file in temp_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
                    self.logger.info(f"一時ファイル削除: {temp_file}")
            except Exception as e:
                self.logger.warning(f"一時ファイル削除でエラー: {e}")

    def cleanup_on_error(self, output_path: str, temp_files: List[str]):
        """
        エラー時のクリーンアップ
        
        Args:
            output_path: 出力ファイルパス
            temp_files: 一時ファイルのリスト
        """
        try:
            # 不完全な出力ファイルを削除
            if Path(output_path).exists():
                Path(output_path).unlink()
                self.logger.info(f"不完全な出力ファイルを削除: {output_path}")
            
            # 一時ファイルを削除
            self.cleanup_temp_files(temp_files)
            
            # FFmpegプロセスを終了
            self.kill_ffmpeg_processes()
            
        except Exception as e:
            self.logger.warning(f"エラー時クリーンアップでエラー: {e}") 