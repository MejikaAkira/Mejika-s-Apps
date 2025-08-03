"""
ファイル操作ユーティリティ
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from ...utils.logger import get_logger


class FileHandler:
    """ファイル操作を管理"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.logger = get_logger("FileHandler")

    def save_json(self, data: Any, output_path: Path):
        """JSONファイルとして保存"""
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"JSONファイルを保存: {output_path}")
            
        except Exception as e:
            self.logger.error(f"JSON保存でエラー: {e}")

    def load_json(self, file_path: Path) -> Any:
        """JSONファイルを読み込み"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.logger.info(f"JSONファイルを読み込み: {file_path}")
            return data
            
        except FileNotFoundError:
            self.logger.error(f"ファイルが見つかりません: {file_path}")
            return None
        except Exception as e:
            self.logger.error(f"JSON読み込みでエラー: {e}")
            return None

    def ensure_directory(self, directory: Path):
        """ディレクトリを確実に作成"""
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.logger.info(f"ディレクトリを作成/確認: {directory}")
        except Exception as e:
            self.logger.error(f"ディレクトリ作成でエラー: {e}")

    def list_files(self, directory: Path, pattern: str = "*") -> List[Path]:
        """ディレクトリ内のファイルをリストアップ"""
        try:
            files = list(directory.glob(pattern))
            self.logger.info(f"ファイル一覧を取得: {directory} ({len(files)}件)")
            return files
        except Exception as e:
            self.logger.error(f"ファイル一覧取得でエラー: {e}")
            return []

    def file_exists(self, file_path: Path) -> bool:
        """ファイルの存在確認"""
        exists = file_path.exists()
        if exists:
            self.logger.debug(f"ファイルが存在します: {file_path}")
        else:
            self.logger.debug(f"ファイルが存在しません: {file_path}")
        return exists 