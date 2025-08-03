"""
動画合成モジュール
画像、音声、BGMを組み合わせて動画を生成する機能
"""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
import ffmpeg


class VideoSynthesizer:
    """動画合成クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        VideoSynthesizerの初期化
        
        Args:
            config: 設定辞書
        """
        self.config = config
        self.logger = logger.bind(name="video_synthesizer")
        
        # 動画関連の設定を取得
        self.video_settings = config.get('video', {})
        self.audio_settings = config.get('audio', {})
        
        # 出力ディレクトリ
        self.output_dir = Path(config.get('paths', {}).get('output', {}).get('videos', 'output/videos'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 一時ディレクトリ
        self.temp_dir = self.output_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def create_slide_synchronized_video(self, image_files: List[str], slide_audio_files: Dict[int, str], 
                                       bgm_data: Dict[str, Any], output_path: str, script_data: Dict[str, Any]):
        """
        スライド同期動画作成（修正版）
        各スライドの音声と画像を単純に結合（動画ファイル対応）
        """
        try:
            # 動画設定
            resolution = self.video_settings.get('resolution', '1920x1080')
            fps = self.video_settings.get('fps', 30)
            natural_pause = self.video_settings.get('natural_pause', 0.3)
            
            self.logger.info("スライド同期動画作成開始（修正版）")
            self.logger.info(f"画像ファイル数: {len(image_files)}")
            self.logger.info(f"音声ファイル数: {len(slide_audio_files)}")
            
            # 一時ファイルリスト
            temp_files = []
            
            # 1. 各スライドの動画を作成
            for i, image_file in enumerate(image_files, 1):
                slide_num = i
                slide_audio_path = slide_audio_files.get(slide_num)
                
                # ファイルタイプとパスを確認
                image_path = Path(image_file)
                is_video = image_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.wmv']
                
                # 合成済み動画かどうか確認（_all.mp4）
                is_combined = '_all.mp4' in image_path.name
                
                # 出力ファイル名
                temp_video = self.output_dir / f"temp_slide_{slide_num:02d}.mp4"
                temp_files.append(str(temp_video))
                
                if is_combined:
                    # 合成済み動画の場合（静止画3秒＋埋め込み動画）
                    self.logger.info(f"スライド{slide_num}は合成済み動画です: {image_path}")
                    
                    if slide_audio_path and Path(slide_audio_path).exists():
                        # 音声の長さを取得
                        audio_duration = self._get_audio_duration(str(slide_audio_path))
                        video_duration = self._get_video_duration(str(image_file))
                        
                        self.logger.info(f"スライド{slide_num} - 音声: {audio_duration:.2f}秒, 動画: {video_duration:.2f}秒")
                        
                        # 音声と動画の長さを合わせる
                        cmd = [
                            'ffmpeg', '-y',
                            '-i', str(image_file),  # 合成済み動画
                            '-i', str(slide_audio_path),  # 音声
                            '-c:v', 'libx264',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-pix_fmt', 'yuv420p',
                            '-s', resolution,
                            '-r', str(fps),
                            '-t', str(max(audio_duration, video_duration)),  # 長い方に合わせる
                            str(temp_video)
                        ]
                    else:
                        # 音声なしの場合はそのままコピー
                        shutil.copy2(str(image_file), str(temp_video))
                        
                elif is_video:
                    # 通常の動画ファイルの場合
                    self.logger.info(f"スライド{slide_num}は動画ファイルです: {image_path}")
                    
                    if slide_audio_path and Path(slide_audio_path).exists():
                        # 音声ありの場合
                        cmd = [
                            'ffmpeg', '-y',
                            '-i', str(image_file),  # 動画入力（-loopなし）
                            '-i', str(slide_audio_path),  # 音声入力
                            '-c:v', 'libx264',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-pix_fmt', 'yuv420p',
                            '-s', resolution,
                            '-r', str(fps),
                            '-shortest',  # 音声の長さに合わせる
                            str(temp_video)
                        ]
                    else:
                        # 音声なしの場合
                        cmd = [
                            'ffmpeg', '-y',
                            '-i', str(image_file),  # 動画入力（-loopなし）
                            '-t', '5',  # 5秒に制限
                            '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p',
                            '-s', resolution,
                            '-r', str(fps),
                            str(temp_video)
                        ]
                else:
                    # 静止画の場合
                    if slide_audio_path and Path(slide_audio_path).exists():
                        # 音声ありの場合
                        cmd = [
                            'ffmpeg', '-y',
                            '-loop', '1', '-i', str(image_file),  # 画像入力（-loopあり）
                            '-i', str(slide_audio_path),  # 音声入力
                            '-c:v', 'libx264',
                            '-c:a', 'aac',
                            '-b:a', '128k',
                            '-pix_fmt', 'yuv420p',
                            '-s', resolution,
                            '-r', str(fps),
                            '-shortest',  # 音声の長さに合わせる
                            str(temp_video)
                        ]
                    else:
                        # 音声なしの場合（5秒の動画）
                        cmd = [
                            'ffmpeg', '-y',
                            '-loop', '1', '-t', '5', '-i', str(image_file),
                            '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p',
                            '-s', resolution,
                            '-r', str(fps),
                            str(temp_video)
                        ]
                
                # FFmpegを実行（エンコーディング指定を追加）
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if result.returncode != 0:
                    self.logger.error(f"スライド{slide_num}の動画作成エラー: {result.stderr}")
                    # エラーでも続行（フォールバック）
                    if is_video:
                        self._copy_video_with_duration(image_path, temp_video, 5)
                    else:
                        self._create_fallback_slide_video(image_path, temp_video, 5)
                else:
                    self.logger.info(f"スライド{slide_num}の動画作成完了")
            
            # 2. すべての動画を結合
            concat_list_path = self.output_dir / "concat_list.txt"
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for temp_file in temp_files:
                    if Path(temp_file).exists():
                        f.write(f"file '{Path(temp_file).resolve()}'\n")
            
            # 結合コマンド
            concat_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list_path),
                '-c', 'copy',
                str(output_path)
            ]
            
            result = subprocess.run(
                concat_cmd, 
                capture_output=True, 
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                self.logger.error(f"動画結合エラー: {result.stderr}")
            else:
                self.logger.info(f"動画結合完了: {output_path}")
            
            # 3. BGMを追加（必要な場合）
            if bgm_data.get('file_path') and Path(bgm_data['file_path']).exists():
                final_output = self.output_dir / "final_with_bgm.mp4"
                bgm_cmd = [
                    'ffmpeg', '-y',
                    '-i', str(output_path),
                    '-i', str(bgm_data['file_path']),
                    '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3',
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-shortest',
                    str(final_output)
                ]
                
                result = subprocess.run(
                    bgm_cmd, 
                    capture_output=True, 
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if result.returncode == 0:
                    # BGM追加成功したら、ファイルを置き換え
                    shutil.move(str(final_output), str(output_path))
                    self.logger.info("BGM追加完了")
            
            # 4. 一時ファイルを削除
            for temp_file in temp_files:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
            if concat_list_path.exists():
                concat_list_path.unlink()
            
        except Exception as e:
            self.logger.error(f"動画作成でエラー: {e}")
            raise
    
    def create_combined_video(self, slide_path: str, embedded_path: str, slide_number: int) -> Optional[Path]:
        """
        スライド動画と埋め込み動画を合成（修正版）
        静止画3秒 + 埋め込み動画の順序で正確な長さを保つ
        
        Args:
            slide_path: スライド画像のパス
            embedded_path: 埋め込み動画のパス
            slide_number: スライド番号
            
        Returns:
            合成された動画のパス
        """
        try:
            # 出力ファイル名
            output_path = self.output_dir / f"slide_{slide_number:02d}_all.mp4"
            
            # 埋め込み動画の長さを取得
            embedded_duration = self._get_video_duration(embedded_path)
            if embedded_duration <= 0:
                self.logger.error(f"埋め込み動画の長さを取得できません: {embedded_path}")
                return None
            
            self.logger.info(f"スライド{slide_number}の埋め込み動画長さ: {embedded_duration:.2f}秒")
            
            # 静止画表示時間（秒）
            image_duration = 3.0
            
            # 一時ファイル
            temp_image_video = self.temp_dir / f"temp_image_{slide_number}.mp4"
            temp_embedded_video = self.temp_dir / f"temp_embedded_{slide_number}.mp4"
            
            try:
                # 1. 静止画を3秒の動画に変換
                image_cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', str(slide_path),
                    '-t', str(image_duration),  # 正確に3秒
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-pix_fmt', 'yuv420p',
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                    '-r', '30',
                    str(temp_image_video)
                ]
                
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
                
                # 静止画動画の実際の長さを確認
                actual_image_duration = self._get_video_duration(str(temp_image_video))
                self.logger.info(f"静止画動画の実際の長さ: {actual_image_duration:.2f}秒")
                
                # 2. 埋め込み動画を正しい長さで処理（ループを防ぐ）
                embedded_cmd = [
                    'ffmpeg', '-y',
                    '-i', str(embedded_path),
                    '-t', str(embedded_duration),  # 元の長さを維持
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-pix_fmt', 'yuv420p',
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                    '-r', '30',
                    '-an',  # 音声を除去（後で追加するため）
                    str(temp_embedded_video)
                ]
                
                result = subprocess.run(
                    embedded_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if result.returncode != 0:
                    self.logger.error(f"埋め込み動画処理エラー: {result.stderr}")
                    # エラーの場合は元の動画をそのまま使用
                    temp_embedded_video = Path(embedded_path)
                
                # 3. 2つの動画を結合（concatプロトコルを使用）
                concat_list = self.temp_dir / f"concat_slide_{slide_number}.txt"
                with open(concat_list, 'w', encoding='utf-8') as f:
                    f.write(f"file '{temp_image_video.resolve()}'\n")
                    f.write(f"file '{temp_embedded_video.resolve()}'\n")
                
                # 結合コマンド
                concat_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_list),
                    '-c:v', 'libx264',  # 再エンコード（統一性のため）
                    '-preset', 'fast',
                    '-pix_fmt', 'yuv420p',
                    '-r', '30',
                    str(output_path)
                ]
                
                result = subprocess.run(
                    concat_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if result.returncode == 0:
                    # 合成された動画の実際の長さを確認
                    actual_duration = self._get_video_duration(str(output_path))
                    expected_duration = image_duration + embedded_duration
                    
                    self.logger.info(f"スライド{slide_number}の動画合成完了:")
                    self.logger.info(f"  期待される長さ: {expected_duration:.2f}秒 (静止画: {image_duration}秒 + 動画: {embedded_duration:.2f}秒)")
                    self.logger.info(f"  実際の長さ: {actual_duration:.2f}秒")
                    
                    # 長さの差が大きい場合は警告
                    if abs(actual_duration - expected_duration) > 1.0:
                        self.logger.warning(f"動画の長さに誤差があります: 期待値との差 {abs(actual_duration - expected_duration):.2f}秒")
                    
                    return output_path
                else:
                    self.logger.error(f"動画結合エラー: {result.stderr}")
                    return None
                    
            finally:
                # 一時ファイルをクリーンアップ
                for temp_file in [temp_image_video, concat_list]:
                    if temp_file.exists():
                        temp_file.unlink()
                # temp_embedded_videoが一時ファイルの場合のみ削除
                if temp_embedded_video != Path(embedded_path) and temp_embedded_video.exists():
                    temp_embedded_video.unlink()
                    
        except Exception as e:
            self.logger.error(f"動画合成でエラー: {e}")
            return None

    def _get_audio_duration(self, audio_path: str) -> float:
        """
        音声ファイルの長さを取得
        
        Args:
            audio_path: 音声ファイルパス
            
        Returns:
            音声の長さ（秒）
        """
        try:
            probe = ffmpeg.probe(audio_path)
            
            # formatから長さを取得（より正確）
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
                if duration > 0:
                    return duration
            
            # ストリームから長さを取得（フォールバック）
            if 'streams' in probe:
                for stream in probe['streams']:
                    if stream.get('codec_type') == 'audio' and 'duration' in stream:
                        duration = float(stream['duration'])
                        if duration > 0:
                            return duration
            
            # 長さが取得できない場合はffprobeコマンドを直接実行
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(audio_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                return duration
                
            return 0.0
            
        except Exception as e:
            self.logger.warning(f"音声長さ取得でエラー: {e}")
            return 0.0

    def _get_video_duration(self, video_path: str) -> float:
        """
        動画ファイルの長さを取得（改善版）
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            動画の長さ（秒）
        """
        try:
            probe = ffmpeg.probe(video_path)
            
            # formatから長さを取得（より正確）
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
                if duration > 0:
                    return duration
            
            # ストリームから長さを取得（フォールバック）
            if 'streams' in probe:
                for stream in probe['streams']:
                    if stream.get('codec_type') == 'video' and 'duration' in stream:
                        duration = float(stream['duration'])
                        if duration > 0:
                            return duration
            
            # 長さが取得できない場合はffprobeコマンドを直接実行
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                return duration
                
            return 0.0
            
        except Exception as e:
            self.logger.warning(f"動画長さ取得でエラー: {e}")
            return 0.0

    def _copy_video_with_duration(self, source_path: Path, output_path: Path, duration: float):
        """
        動画ファイルを指定された長さでコピー（フォールバック用）
        """
        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', str(source_path),
                '-t', str(duration),
                '-c', 'copy',  # 再エンコードなしでコピー
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                self.logger.info(f"動画をコピーしました: {output_path}")
            else:
                self.logger.error(f"動画コピーエラー: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"動画コピーでエラー: {e}")

    def _create_fallback_slide_video(self, image_path: Path, output_path: Path, duration: float):
        """
        フォールバック用のスライド動画作成
        """
        try:
            # シンプルなコマンドで再試行
            cmd = [
                'ffmpeg', '-y',
                '-framerate', '1',
                '-i', str(image_path),
                '-t', str(duration),
                '-vf', f'scale=1920:1080',
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                self.logger.info(f"フォールバック方法で動画を作成: {output_path}")
            else:
                self.logger.error(f"フォールバック作成エラー: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"フォールバック作成でエラー: {e}") 