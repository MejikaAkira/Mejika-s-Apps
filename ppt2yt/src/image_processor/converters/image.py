"""
画像変換処理
"""
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from ...utils.logger import get_logger


class ImageConverter:
    """画像変換処理"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger("ImageConverter")

    def resize_image(self, image_path: str, output_path: Path, 
                    width: int = 1920, height: int = 1080) -> Optional[Path]:
        """画像をリサイズ"""
        try:
            with Image.open(image_path) as img:
                # アスペクト比を保持してリサイズ
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                
                # 背景を追加して指定サイズに
                new_image = Image.new('RGB', (width, height), 'white')
                
                # 画像を中央に配置
                x = (width - img.width) // 2
                y = (height - img.height) // 2
                new_image.paste(img, (x, y))
                
                # 保存
                new_image.save(output_path, "PNG", optimize=True)
                
                self.logger.info(f"画像をリサイズ完了: {output_path}")
                return output_path
                
        except Exception as e:
            self.logger.error(f"画像リサイズでエラー: {e}")
            return None

    def save_image(self, image: Image.Image, output_path: Path, 
                   format: str = "PNG", quality: int = 95) -> Optional[Path]:
        """画像を保存"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, format, optimize=True, quality=quality)
            
            self.logger.info(f"画像を保存完了: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"画像保存でエラー: {e}")
            return None

    def verify_image_file(self, image_path: Path) -> bool:
        """画像ファイルが実際に画像かどうかを検証"""
        try:
            with Image.open(image_path) as img:
                # 画像の基本情報を確認
                width, height = img.size
                if width > 0 and height > 0:
                    self.logger.info(f"画像ファイルを検証しました: {image_path} ({width}x{height})")
                    return True
                else:
                    self.logger.warning(f"無効な画像サイズ: {width}x{height}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"画像検証でエラー: {e}")
            return False 