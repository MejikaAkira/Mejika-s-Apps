"""
音声生成モジュール
台本から音声ファイルを生成する機能
"""

import os
import httpx
from openai import OpenAI
import re
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger


class AudioGenerator:
    """音声生成クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        AudioGeneratorの初期化
        
        Args:
            config: 設定辞書
        """
        self.config = config
        self.logger = logger.bind(name="audio_generator")
        
        # 出力ディレクトリ
        self.output_dir = Path(config.get('paths', {}).get('output', {}).get('audio', 'output/audio'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_slide_audio(self, script_data: Dict[str, Any], images_data: List[Dict[str, Any]] = None) -> Dict[int, str]:
        """
        台本から各スライドの音声ファイルを生成（対話形式対応・埋め込み動画対応）
        
        Args:
            script_data: 台本データ
            images_data: 画像・動画データ（埋め込み動画の長さ調整用）
            
        Returns:
            スライド番号 -> 音声ファイルパスの辞書
        """
        try:
            # OpenAI API設定
            api_key = self.config.get("openai.api_key")
            if not api_key:
                raise ValueError("OpenAI API key not found")
            
            # プロキシ設定
            proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            
            if proxy_url:
                http_client = httpx.Client(proxies={"http://": proxy_url, "https://": proxy_url})
                client = OpenAI(api_key=api_key, http_client=http_client)
            else:
                client = OpenAI(api_key=api_key)
            
            if not script_data.get('dialogue'):
                self.logger.warning("台本テキストが空です")
                return {}
            
            self.logger.info("TTS音声生成を開始（各セリフ別→スライド結合）")
            
            # 設定ファイルからTTSモデルを取得
            tts_model = self.config.get("openai.model.tts", "tts-1")
            
            # 1. 各セリフを個別に音声生成
            dialogue_audio_files = []
            for i, dialogue in enumerate(script_data.get('dialogue', [])):
                text = dialogue.get('text', '').strip()
                voice = dialogue.get('voice', 'onyx')
                
                if not text:
                    self.logger.warning(f"セリフ{i+1}のテキストが空です")
                    continue
                
                try:
                    self.logger.info(f"セリフ{i+1}音声生成中: {voice}")
                    
                    response = client.audio.speech.create(
                        model=tts_model,
                        voice=voice,
                        input=text
                    )
                    
                    # セリフ用音声ファイルを保存
                    audio_path = self.output_dir / f"dialogue_{i:03d}_audio.wav"
                    with open(audio_path, 'wb') as f:
                        f.write(response.content)
                    
                    dialogue_audio_files.append({
                        'index': i,
                        'file_path': str(audio_path),
                        'slide_file': dialogue.get('slide_file', ''),
                        'duration': dialogue.get('duration', 5)
                    })
                    
                    self.logger.info(f"セリフ{i+1}音声生成完了: {audio_path}")
                    
                except Exception as e:
                    self.logger.error(f"セリフ{i+1}の音声生成でエラー: {e}")
                    continue
            
            # 2. スライド別に音声ファイルを結合
            slide_audio_files = {}
            slide_dialogues = {}
            
            # スライド別にセリフをグループ化
            for dialogue_audio in dialogue_audio_files:
                slide_file = dialogue_audio['slide_file']
                match = re.search(r'slide_(\d+)\.png', slide_file)
                if match:
                    slide_num = int(match.group(1))
                else:
                    slide_num = 1
                
                if slide_num not in slide_dialogues:
                    slide_dialogues[slide_num] = []
                slide_dialogues[slide_num].append(dialogue_audio)
            
            # 各スライドの音声ファイルを結合
            for slide_num, dialogues in slide_dialogues.items():
                if not dialogues:
                    continue
                
                self.logger.info(f"スライド{slide_num}の音声結合中...")
                
                # スライド用音声ファイルの出力パス
                slide_audio_path = self.output_dir / f"slide_{slide_num:02d}_audio.wav"
                
                try:
                    # セリフ音声ファイルを結合
                    audio_files = [d['file_path'] for d in dialogues]
                    self._combine_audio_files_with_ffmpeg(audio_files, str(slide_audio_path))
                    
                    # 埋め込み動画がある場合は音声長さを調整
                    if images_data:
                        slide_info = next((img for img in images_data if img.get('slide_number') == slide_num), None)
                        if slide_info and slide_info.get('embedded_videos'):
                            # 合成動画の長さを取得
                            combined_video_path = self.output_dir / f"slide_{slide_num:02d}_all.mp4"
                            if combined_video_path.exists():
                                video_duration = self._get_video_duration(str(combined_video_path))
                                audio_duration = self._get_audio_duration(str(slide_audio_path))
                                
                                if video_duration > audio_duration:
                                    # 音声を動画の長さに合わせて延長
                                    self.logger.info(f"スライド{slide_num}の音声を動画長({video_duration:.2f}秒)に合わせて調整")
                                    extended_audio_path = self._extend_audio_to_duration(str(slide_audio_path), video_duration)
                                    if extended_audio_path:
                                        slide_audio_path = Path(extended_audio_path)
                            else:
                                self.logger.info(f"スライド{slide_num}の合成動画が存在しないため音声調整をスキップ")
                    
                    slide_audio_files[slide_num] = str(slide_audio_path)
                    self.logger.info(f"スライド{slide_num}音声結合完了: {slide_audio_path}")
                    
                except Exception as e:
                    self.logger.error(f"スライド{slide_num}の音声結合でエラー: {e}")
                    continue
            
            # スライド8-10の音声ファイルが存在しない場合の処理
            total_slides = max(slide_dialogues.keys()) if slide_dialogues else 0
            for slide_num in range(1, total_slides + 1):
                if slide_num not in slide_audio_files:
                    self.logger.warning(f"スライド{slide_num}の音声ファイルが生成されていません。無音ファイルを作成します。")
                    # 無音ファイルを作成
                    silent_audio_path = self.output_dir / f"slide_{slide_num:02d}_audio.wav"
                    self._create_silent_audio_file(str(silent_audio_path), 5)
                    slide_audio_files[slide_num] = str(silent_audio_path)
                    self.logger.info(f"スライド{slide_num}無音ファイル作成: {silent_audio_path}")
            
            # 一時ファイルを削除
            for dialogue_audio in dialogue_audio_files:
                if os.path.exists(dialogue_audio['file_path']):
                    os.remove(dialogue_audio['file_path'])
            
            self.logger.info(f"TTS音声生成完了: {len(slide_audio_files)}スライド")
            return slide_audio_files
            
        except Exception as e:
            self.logger.error(f"TTS音声生成でエラー: {e}")
            return {}
    
    def _combine_audio_files_with_ffmpeg(self, audio_files: List[str], output_path: str):
        """
        FFmpegを使用して音声ファイルを結合
        
        Args:
            audio_files: 結合する音声ファイルのリスト
            output_path: 出力音声ファイルのパス
        """
        import ffmpeg
        
        if not audio_files:
            self.logger.warning("結合する音声ファイルがありません")
            return
        
        try:
            self.logger.info(f"音声結合開始: {len(audio_files)}個のファイル")
            
            # concatファイルを作成
            concat_file = self.output_dir / "audio_concat.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    if Path(audio_file).exists():
                        abs_path = Path(audio_file).resolve()
                        f.write(f"file '{abs_path}'\n")
            
            # 音声ファイルを結合
            (
                ffmpeg
                .input(str(concat_file), f='concat', safe=0)
                .output(output_path, acodec='pcm_s16le', ar=44100, ac=2)
                .overwrite_output()
                .run(quiet=True)
            )
            
            # 一時ファイルを削除
            if concat_file.exists():
                concat_file.unlink()
            
            self.logger.info(f"音声結合完了: {output_path}")
            
        except Exception as e:
            self.logger.error(f"音声結合でエラー: {e}")
            # エラーの場合は最初の音声ファイルをコピー
            if audio_files and Path(audio_files[0]).exists():
                import shutil
                shutil.copy2(audio_files[0], output_path)
                self.logger.info(f"エラーのため最初の音声ファイルをコピー: {output_path}")
            else:
                # 無音ファイルを作成
                self._create_silent_audio_file(output_path, 5)
                self.logger.info(f"エラーのため無音ファイルを作成: {output_path}")
    
    def _create_silent_audio_file(self, file_path: str, duration: int):
        """
        無音の音声ファイルを作成（FFmpeg使用）
        
        Args:
            file_path: 出力ファイルパス
            duration: 音声の長さ（秒）
        """
        import ffmpeg
        
        try:
            (
                ffmpeg
                .input('anullsrc', f='lavfi', t=duration)
                .output(file_path, acodec='pcm_s16le', ar=44100, ac=2)
                .overwrite_output()
                .run(quiet=True)
            )
        except Exception as e:
            self.logger.error(f"無音ファイル生成でエラー: {e}")
            # フォールバック: 空のファイルを作成
            with open(file_path, 'w') as f:
                pass
    
    def _get_video_duration(self, video_path: str) -> float:
        """
        動画ファイルの長さを取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            動画の長さ（秒）
        """
        import ffmpeg
        
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

    def _get_audio_duration(self, audio_path: str) -> float:
        """
        音声ファイルの長さを取得
        
        Args:
            audio_path: 音声ファイルパス
            
        Returns:
            音声の長さ（秒）
        """
        import ffmpeg
        
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

    def _extend_audio_to_duration(self, audio_path: str, target_duration: float) -> str:
        """
        音声ファイルを指定された長さに延長（無音を追加）
        
        Args:
            audio_path: 音声ファイルパス
            target_duration: 目標の長さ（秒）
            
        Returns:
            延長された音声ファイルのパス
        """
        try:
            current_duration = self._get_audio_duration(audio_path)
            if current_duration >= target_duration:
                return audio_path  # 既に十分な長さ
            
            # 延長する長さを計算
            extension_duration = target_duration - current_duration
            
            # 出力ファイルパス
            output_path = audio_path.replace('.wav', '_extended.wav')
            
            # 無音セグメントを作成
            silence_path = self._create_silence_segment(extension_duration)
            
            # 音声と無音を結合
            cmd = [
                'ffmpeg', '-y',
                '-i', audio_path,
                '-i', silence_path,
                '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1',
                '-c:a', 'pcm_s16le',
                '-ar', '44100',
                '-ac', '2',
                output_path
            ]
            
            import subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                self.logger.info(f"音声を延長しました: {current_duration:.2f}秒 → {target_duration:.2f}秒")
                return output_path
            else:
                self.logger.error(f"音声延長エラー: {result.stderr}")
                return audio_path
                
        except Exception as e:
            self.logger.error(f"音声延長でエラー: {e}")
            return audio_path 

    def _create_silence_segment(self, duration: float) -> str:
        """
        指定した長さの無音セグメントを作成
        
        Args:
            duration: 無音の長さ（秒）
            
        Returns:
            無音ファイルのパス
        """
        import ffmpeg
        import uuid
        silence_path = self.output_dir / f"silence_{uuid.uuid4().hex[:8]}.wav"
        
        try:
            (
                ffmpeg
                .input('anullsrc', f='lavfi', t=duration)
                .output(str(silence_path), acodec='pcm_s16le', ar=44100, ac=2)
                .overwrite_output()
                .run(quiet=True)
            )
            return str(silence_path)
        except Exception as e:
            self.logger.error(f"無音セグメント作成エラー: {e}")
            # フォールバック
            with open(silence_path, 'wb') as f:
                f.write(b'\x00' * int(44100 * 2 * 2 * duration))  # 簡易的な無音データ
            return str(silence_path) 