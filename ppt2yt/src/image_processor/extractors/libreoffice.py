"""
LibreOfficeを使用したスライド抽出
"""
import platform
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseSlideExtractor


class LibreOfficeExtractor(BaseSlideExtractor):
    """LibreOfficeを使用したスライド抽出"""
    
    def is_available(self) -> bool:
        """LibreOfficeが利用可能かチェック"""
        try:
            # LibreOfficeのコマンドを確認
            result = subprocess.run(['soffice', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def can_extract_video(self) -> bool:
        """動画抽出はサポートしていない"""
        return False
    
    def extract_single_slide(self, pptx_path: str, slide_number: int) -> Optional[Dict[str, Any]]:
        """単一スライドを画像として抽出"""
        try:
            # LibreOfficeでPDFに変換
            pdf_path = self._convert_to_pdf(pptx_path)
            if not pdf_path:
                return None
            
            # PDFから画像を抽出
            images = self._extract_images_from_pdf(pdf_path, slide_number)
            if images:
                return images[0]  # 最初の画像を返す
            
            return None
        except Exception as e:
            self.logger.error(f"単一スライド抽出でエラー: {e}")
            return None
    
    def extract_slides(self, pptx_path: str) -> List[Dict[str, Any]]:
        """すべてのスライドを画像として抽出"""
        try:
            # LibreOfficeでPDFに変換
            pdf_path = self._convert_to_pdf(pptx_path)
            if not pdf_path:
                return []
            
            # PDFから画像を抽出
            return self._extract_images_from_pdf(pdf_path)
        except Exception as e:
            self.logger.error(f"スライド抽出でエラー: {e}")
            return []
    
    def extract_slide_as_video(self, pptx_path: str, slide_number: int, 
                              duration: int = 10) -> Optional[Path]:
        """スライドを動画として抽出（サポートしていない）"""
        self.logger.warning("LibreOffice抽出器は動画抽出をサポートしていません")
        return None
    
    def _convert_to_pdf(self, pptx_path: str) -> Optional[Path]:
        """PPTXをPDFに変換"""
        try:
            pdf_dir = self.output_dir / "temp_pdf"
            pdf_dir.mkdir(exist_ok=True)
            
            # LibreOfficeでPDFに変換
            cmd = [
                'soffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', str(pdf_dir),
                str(Path(pptx_path).resolve())
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # 生成されたPDFファイルを探す
                pptx_name = Path(pptx_path).stem
                pdf_path = pdf_dir / f"{pptx_name}.pdf"
                
                if pdf_path.exists():
                    return pdf_path
                else:
                    self.logger.error(f"PDFファイルが見つかりません: {pdf_path}")
                    return None
            else:
                self.logger.error(f"PDF変換に失敗: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"PDF変換でエラー: {e}")
            return None
    
    def _extract_images_from_pdf(self, pdf_path: Path, target_slide: Optional[int] = None) -> List[Dict[str, Any]]:
        """PDFから画像を抽出"""
        try:
            # pdf2imageを使用して画像に変換
            from pdf2image import convert_from_path
            
            # 特定のスライドのみ抽出する場合
            if target_slide is not None:
                pages = convert_from_path(
                    str(pdf_path),
                    first_page=target_slide,
                    last_page=target_slide,
                    dpi=200
                )
            else:
                pages = convert_from_path(str(pdf_path), dpi=200)
            
            images_info = []
            start_slide = target_slide if target_slide else 1
            
            for i, page in enumerate(pages):
                slide_number = start_slide + i
                filename = f"slide_{slide_number:02d}.png"
                output_path = self.output_dir / filename
                
                # 画像を保存
                page.save(output_path, "PNG")
                
                if output_path.exists():
                    images_info.append(self._create_slide_info(slide_number, output_path))
                else:
                    self.logger.warning(f"スライド {slide_number} の保存に失敗")
            
            return images_info
            
        except ImportError:
            self.logger.error("pdf2imageライブラリがインストールされていません")
            return []
        except Exception as e:
            self.logger.error(f"PDFから画像抽出でエラー: {e}")
            return [] 