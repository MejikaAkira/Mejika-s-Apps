"""
動画変換処理
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ...utils.logger import get_logger


class VideoConverter:
    """動画変換処理"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger("VideoConverter")

        # 動画処理設定
        self.max_video_duration = config.get("max_video_duration", 30)
        self.video_scale = config.get("video_scale", "640x360")
        self.gif_fps = config.get("gif_fps", 10)
        self.gif_quality = config.get("gif_quality", 85)

    def convert_video_to_gif(self, video_path: str, output_path: Path) -> Optional[Path]:
        """動画をGIFに変換"""
        try:
            # FFmpegでGIFに変換
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f'fps={self.gif_fps},scale={self.video_scale}',
                '-t', str(self.max_video_duration),
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.logger.error(f"GIF変換エラー: {result.stderr}")
                return None

            self.logger.info(f"動画をGIFに変換完了: {output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            self.logger.error("GIF変換がタイムアウトしました")
            return None
        except Exception as e:
            self.logger.error(f"GIF変換エラー: {e}")
            return None

    def get_video_info(self, video_path: str) -> Optional[Dict[str, Any]]:
        """動画ファイルの情報を取得"""
        try:
            import subprocess
            import json

            # FFprobeで動画情報を取得
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.error(f"FFprobeエラー: {result.stderr}")
                return None

            info = json.loads(result.stdout)

            # 動画ストリームを取得
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                self.logger.error("動画ストリームが見つかりません")
                return None

            # 動画情報を抽出
            duration = float(info.get('format', {}).get('duration', 0))
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))

            # 最大動画長をチェック
            if duration > self.max_video_duration:
                self.logger.warning(f"動画が長すぎます: {duration}秒 > {self.max_video_duration}秒")
                duration = self.max_video_duration

            return {
                "duration": duration,
                "width": width,
                "height": height,
                "format": info.get('format', {}).get('format_name', 'unknown')
            }

        except subprocess.TimeoutExpired:
            self.logger.error("動画情報取得がタイムアウトしました")
            return None
        except Exception as e:
            self.logger.error(f"動画情報取得エラー: {e}")
            return None

    def verify_video_file(self, video_path: Path) -> bool:
        """動画ファイルが実際に動画かどうかを検証"""
        try:
            import subprocess

            # ffprobeを使用して動画情報を取得
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(video_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                import json
                probe_data = json.loads(result.stdout)

                # 動画ストリームがあるかチェック
                streams = probe_data.get('streams', [])
                video_streams = [s for s in streams if s.get('codec_type') == 'video']

                if video_streams:
                    # 動画の長さをチェック
                    format_info = probe_data.get('format', {})
                    duration = float(format_info.get('duration', 0))

                    if duration > 1.0:  # 1秒以上の動画
                        self.logger.info(f"動画ファイルを検証しました: {video_path} (長さ: {duration:.2f}秒)")
                        return True
                    else:
                        self.logger.warning(f"動画が短すぎます: {duration:.2f}秒")
                        return False
                else:
                    self.logger.warning(f"動画ストリームが見つかりません: {video_path}")
                    return False
            else:
                self.logger.warning(f"動画ファイルの検証に失敗: {video_path}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("動画検証がタイムアウトしました")
            return False
        except Exception as e:
            self.logger.error(f"動画検証でエラー: {e}")
            return False 