"""
設定ファイル管理ユーティリティ
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


class ConfigManager:
    """設定ファイルの読み込みと管理を行うクラス"""
    
    def __init__(self, config_path: str = None):
        """
        ConfigManagerの初期化
        
        Args:
            config_path: 設定ファイルのパス
        """
        if config_path is None:
            # 現在のファイルの場所を基準にconfig.yamlのパスを決定
            current_dir = Path(__file__).parent.parent.parent
            config_path = current_dir / "config" / "config.yaml"
        
        self.config_path = config_path
        self.config = {}
        self._load_config()
    
    def _load_config(self):
        """設定ファイルを読み込む"""
        # 環境変数を読み込み
        load_dotenv()
        
        # 設定ファイルを読み込み
        config_file = Path(self.config_path)
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # 環境変数を置換
            self._replace_env_vars(self.config)
        else:
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
    
    def _replace_env_vars(self, obj: Any):
        """設定内の環境変数を実際の値に置換"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    obj[key] = os.getenv(env_var, "")
                elif isinstance(value, (dict, list)):
                    self._replace_env_vars(value)
        elif isinstance(obj, list):
            for item in obj:
                self._replace_env_vars(item)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値を取得
        
        Args:
            key: 設定キー（ドット区切りでネストしたキーも指定可能）
            default: デフォルト値
            
        Returns:
            設定値
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_path(self, key: str) -> Path:
        """
        パス設定を取得
        
        Args:
            key: パス設定キー
            
        Returns:
            Pathオブジェクト
        """
        path_str = self.get(key)
        if path_str:
            return Path(path_str)
        return None
    
    def validate_required_configs(self):
        """必須設定の検証"""
        required_configs = [
            "openai.api_key",
            "youtube.client_id",
            "youtube.client_secret"
        ]
        
        missing_configs = []
        for config_key in required_configs:
            if not self.get(config_key):
                missing_configs.append(config_key)
        
        if missing_configs:
            raise ValueError(f"必須設定が不足しています: {', '.join(missing_configs)}")


# グローバル設定インスタンス
config = ConfigManager() 