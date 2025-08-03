"""
スライド抽出の基底クラス
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional

from ...utils.logger import get_logger


class BaseSlideExtractor(ABC):
    """スライド抽出の基底クラス"""
    
    def __init__(self, output_dir: Path, config: Dict[str, Any]):
        self.output_dir = output_dir
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        
    @abstractmethod
    def is_available(self) -> bool:
        """この抽出方法が利用可能かチェック"""
        pass
        
    @abstractmethod
    def extract_slides(self, pptx_path: str) -> List[Dict[str, Any]]:
        """すべてのスライドを画像として抽出"""
        pass
    
    def extract_single_slide(self, pptx_path: str, slide_number: int) -> Optional[Dict[str, Any]]:
        """
        単一スライドを画像として抽出
        デフォルト実装：全スライドを抽出して該当スライドを返す
        """
        slides = self.extract_slides(pptx_path)
        for slide in slides:
            if slide["slide_number"] == slide_number:
                return slide
        return None
        
    @abstractmethod
    def extract_slide_as_video(self, pptx_path: str, slide_number: int, 
                              duration: int = 10) -> Optional[Path]:
        """スライドを動画として抽出"""
        pass
    
    def can_extract_video(self) -> bool:
        """動画抽出をサポートしているかどうか"""
        return False
    
    def _create_slide_info(self, slide_number: int, file_path: Path, 
                          file_type: str = "image") -> Dict[str, Any]:
        """スライド情報の共通フォーマットを作成"""
        return {
            "slide_number": slide_number,
            "image_path": str(file_path),  # 後方互換性のため
            "file_path": str(file_path),
            "filename": file_path.name,
            "description": f"スライド {slide_number}",
            "type": file_type
        } 