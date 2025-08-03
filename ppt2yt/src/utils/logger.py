"""
ログ管理ユーティリティ
"""
import sys
from pathlib import Path
from loguru import logger
from typing import Optional

from .config import config


class LoggerManager:
    """ログ管理クラス"""
    
    def __init__(self):
        """LoggerManagerの初期化"""
        self._setup_logger()
    
    def _setup_logger(self):
        """ログ設定をセットアップ"""
        # 既存のログハンドラーを削除
        logger.remove()
        
        # ログレベルを取得
        log_level = config.get("logging.level", "INFO")
        log_format = config.get("logging.format", 
                               "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}")
        
        # コンソール出力
        logger.add(
            sys.stdout,
            format=log_format,
            level=log_level,
            colorize=True
        )
        
        # ファイル出力
        log_path = config.get_path("paths.logs")
        if log_path:
            log_path.mkdir(parents=True, exist_ok=True)
            
            rotation = config.get("logging.rotation", "10 MB")
            retention = config.get("logging.retention", "30 days")
            
            logger.add(
                log_path / "app.log",
                format=log_format,
                level=log_level,
                rotation=rotation,
                retention=retention,
                encoding="utf-8"
            )
    
    def get_logger(self, name: str = None):
        """
        ロガーを取得
        
        Args:
            name: ロガー名
            
        Returns:
            loguru.logger
        """
        if name:
            return logger.bind(name=name)
        return logger


# グローバルロガーインスタンス
log_manager = LoggerManager()
app_logger = log_manager.get_logger("ppt2yt")


def get_logger(name: str = None):
    """
    ロガーを取得するヘルパー関数
    
    Args:
        name: ロガー名
        
    Returns:
        loguru.logger
    """
    return log_manager.get_logger(name) 