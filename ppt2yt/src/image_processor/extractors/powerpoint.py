"""
PowerPoint COMを使用したスライド抽出（修正版）
"""
import platform
import time
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseSlideExtractor


class PowerPointExtractor(BaseSlideExtractor):
    """PowerPoint COMを使用したスライド抽出"""
    
    def is_available(self) -> bool:
        """PowerPoint COMが利用可能かチェック"""
        if platform.system() != 'Windows':
            return False
            
        try:
            import win32com.client
            return True
        except ImportError:
            return False
    
    def can_extract_video(self) -> bool:
        """動画抽出をサポート"""
        return True
    
    def extract_slide_as_video(self, pptx_path: str, slide_number: int, 
                              duration: int = 10) -> Optional[Path]:
        """スライドを動画として抽出（修正版）"""
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        powerpoint = None
        presentation = None
        
        try:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            powerpoint.WindowState = 2  # ppWindowMinimized
            
            # プレゼンテーションを開く
            abs_path = str(Path(pptx_path).resolve())
            presentation = powerpoint.Presentations.Open(abs_path, WithWindow=False)
            
            if slide_number > presentation.Slides.Count:
                self.logger.error(f"スライド番号 {slide_number} は存在しません")
                return None
            
            # 方法1: 単一スライドのプレゼンテーションを作成してMP4保存
            try:
                self.logger.info("方法1: 単一スライドをMP4として保存を試行...")
                
                # 新しいプレゼンテーションを作成
                new_pres = powerpoint.Presentations.Add()
                
                # 対象スライドを新しいプレゼンテーションにコピー
                target_slide = presentation.Slides(slide_number)
                target_slide.Copy()
                new_pres.Slides.Paste()
                
                # コピーしたスライドの設定
                copied_slide = new_pres.Slides(1)
                
                # スライドのタイミング設定
                copied_slide.SlideShowTransition.AdvanceOnTime = True
                copied_slide.SlideShowTransition.AdvanceTime = duration
                
                # MP4として保存
                video_filename = f"slide_{slide_number:02d}.mp4"
                video_path = self.output_dir / video_filename
                
                # ppSaveAsMP4 = 39
                new_pres.SaveAs(str(video_path.resolve()), 39)
                
                # プレゼンテーションを閉じる
                new_pres.Close()
                
                # ファイル生成を待機
                for i in range(100):  # 最大10秒待機
                    if video_path.exists():
                        file_size = video_path.stat().st_size
                        if file_size > 10000:  # 10KB以上
                            self.logger.info(f"MP4ファイルを生成しました: {video_path} ({file_size} bytes)")
                            return video_path
                    time.sleep(0.1)
                
                self.logger.warning("MP4ファイルの生成がタイムアウトしました")
                
            except Exception as e:
                self.logger.warning(f"方法1でエラー: {e}")
            
            # 方法2: CreateVideoメソッドを使用（PowerPoint 2013以降）
            try:
                self.logger.info("方法2: CreateVideoメソッドを試行...")
                
                # 新しいプレゼンテーションを作成
                new_pres = powerpoint.Presentations.Add()
                
                # スライドをコピー
                presentation.Slides(slide_number).Copy()
                new_pres.Slides.Paste()
                
                # 動画ファイルパス
                video_filename = f"slide_{slide_number:02d}_create.mp4"
                video_path = self.output_dir / video_filename
                
                # CreateVideoメソッドを使用
                # UseTimingsAndNarrations: False = タイミングを使用しない
                # DefaultSlideDuration: 各スライドの表示時間（秒）
                # VertResolution: 720 = 720p
                new_pres.CreateVideo(
                    str(video_path.resolve()),
                    False,  # UseTimingsAndNarrations
                    duration,  # DefaultSlideDuration
                    720,  # VertResolution
                    30,  # FramesPerSecond
                    85  # Quality (0-100)
                )
                
                # 動画生成の完了を待機
                max_wait = 60  # 最大60秒
                for i in range(max_wait * 10):
                    try:
                        status = new_pres.CreateVideoStatus
                        if status == 2:  # ppMediaTaskStatusDone
                            new_pres.Close()
                            if video_path.exists():
                                self.logger.info(f"CreateVideoで動画を生成: {video_path}")
                                return video_path
                            break
                        elif status == 3:  # ppMediaTaskStatusFailed
                            self.logger.warning("CreateVideoが失敗しました")
                            break
                    except:
                        # ステータス取得エラーは無視
                        pass
                    time.sleep(0.1)
                
                new_pres.Close()
                
            except Exception as e:
                self.logger.warning(f"方法2でエラー: {e}")
            
            # 方法3: 画像として保存してFFmpegで変換
            try:
                self.logger.info("方法3: 画像エクスポート + FFmpeg変換を試行...")
                
                # 一時ディレクトリ
                temp_dir = Path(tempfile.gettempdir()) / "pptx_video_export"
                temp_dir.mkdir(exist_ok=True)
                
                # スライドを画像として保存
                temp_image_path = temp_dir / f"slide_{slide_number}.png"
                slide = presentation.Slides(slide_number)
                slide.Export(str(temp_image_path), "PNG", 1920, 1080)
                
                # 画像生成を待機
                for _ in range(50):
                    if temp_image_path.exists():
                        break
                    time.sleep(0.1)
                
                if temp_image_path.exists():
                    # FFmpegで動画に変換
                    video_path = self._convert_image_to_video(
                        temp_image_path, slide_number, duration
                    )
                    
                    # 一時ファイルを削除
                    try:
                        temp_image_path.unlink()
                    except:
                        pass
                    
                    if video_path:
                        return video_path
                else:
                    self.logger.error("画像エクスポートに失敗しました")
                    
            except Exception as e:
                self.logger.error(f"方法3でエラー: {e}")
            
            return None
            
        except Exception as e:
            self.logger.error(f"動画抽出で予期しないエラー: {e}")
            return None
        finally:
            # クリーンアップ
            try:
                if presentation:
                    presentation.Close()
            except:
                pass
            
            try:
                if powerpoint:
                    powerpoint.Quit()
            except:
                pass
                
            pythoncom.CoUninitialize()
    
    def _convert_image_to_video(self, image_path: Path, slide_number: int, 
                               duration: int) -> Optional[Path]:
        """画像を動画に変換（FFmpeg使用）"""
        try:
            import subprocess
            import shutil
            
            # FFmpegが利用可能か確認
            if not shutil.which('ffmpeg'):
                self.logger.error("FFmpegが見つかりません")
                return None
            
            video_filename = f"slide_{slide_number:02d}.mp4"
            video_path = self.output_dir / video_filename
            
            # FFmpegコマンド（シンプル版）
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', str(image_path),
                '-c:v', 'libx264',
                '-t', str(duration),
                '-pix_fmt', 'yuv420p',
                '-vf', 'scale=1920:1080',
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and video_path.exists():
                self.logger.info(f"FFmpegで動画を生成: {video_path}")
                return video_path
            else:
                self.logger.error(f"FFmpeg変換エラー: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            self.logger.error("FFmpeg変換がタイムアウトしました")
            return None
        except Exception as e:
            self.logger.error(f"画像→動画変換でエラー: {e}")
            return None

    def extract_single_slide(self, pptx_path: str, slide_number: int) -> Optional[Dict[str, Any]]:
        """単一スライドを画像として抽出"""
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        powerpoint = None
        presentation = None
        
        try:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            powerpoint.WindowState = 2  # ppWindowMinimized
            
            presentation = powerpoint.Presentations.Open(
                str(Path(pptx_path).resolve()), 
                WithWindow=False
            )
            
            if slide_number > presentation.Slides.Count:
                self.logger.error(f"スライド番号 {slide_number} は存在しません")
                return None
            
            filename = f"slide_{slide_number:02d}.png"
            output_path = self.output_dir / filename
            
            # スライドをエクスポート
            slide = presentation.Slides(slide_number)
            slide.Export(
                str(output_path.resolve()), 
                "PNG",
                self.config.get("export_width", 1920),
                self.config.get("export_height", 1080)
            )
            
            # ファイル生成を待機
            for _ in range(50):  # 最大5秒待機
                if output_path.exists():
                    break
                time.sleep(0.1)
            
            if output_path.exists():
                return self._create_slide_info(slide_number, output_path)
            else:
                self.logger.error(f"スライド {slide_number} のエクスポートに失敗")
                return None
                
        except Exception as e:
            self.logger.error(f"スライド抽出でエラー: {e}")
            return None
        finally:
            try:
                if presentation:
                    presentation.Close()
            except:
                pass
                
            try:
                if powerpoint:
                    powerpoint.Quit()
            except:
                pass
                
            pythoncom.CoUninitialize()
    
    def extract_slides(self, pptx_path: str) -> List[Dict[str, Any]]:
        """すべてのスライドを画像として抽出"""
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        powerpoint = None
        presentation = None
        
        try:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            powerpoint.WindowState = 2  # ppWindowMinimized
            
            presentation = powerpoint.Presentations.Open(
                str(Path(pptx_path).resolve()), 
                WithWindow=False
            )
            
            images_info = []
            total_slides = presentation.Slides.Count
            
            for i in range(1, total_slides + 1):
                try:
                    filename = f"slide_{i:02d}.png"
                    output_path = self.output_dir / filename
                    
                    # スライドをエクスポート
                    slide = presentation.Slides(i)
                    slide.Export(
                        str(output_path.resolve()), 
                        "PNG",
                        self.config.get("export_width", 1920),
                        self.config.get("export_height", 1080)
                    )
                    
                    # ファイル生成を待機
                    for _ in range(50):  # 最大5秒待機
                        if output_path.exists():
                            break
                        time.sleep(0.1)
                    
                    if output_path.exists():
                        images_info.append(self._create_slide_info(i, output_path))
                    else:
                        self.logger.warning(f"スライド {i} のエクスポートに失敗")
                        
                except Exception as e:
                    self.logger.error(f"スライド {i} の処理でエラー: {e}")
                    continue
                    
            return images_info
            
        except Exception as e:
            self.logger.error(f"スライド抽出でエラー: {e}")
            return []
        finally:
            try:
                if presentation:
                    presentation.Close()
            except:
                pass
                
            try:
                if powerpoint:
                    powerpoint.Quit()
            except:
                pass
                
            pythoncom.CoUninitialize() 