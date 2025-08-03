"""
BGM選択モジュール
動画の長さに合わせてサンプルBGMを準備する
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger


class BGMSelector:
    """BGM選択・処理クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        BGMSelectorの初期化
        
        Args:
            config: 設定辞書
        """
        self.config = config
        self.logger = logger.bind(name="bgm_selector")
        
        # BGM関連の設定を取得
        self.bgm_settings = config.get('bgm', {})
        self.output_dir = Path(config.get('paths', {}).get('output', {}).get('audio', 'output/audio'))
        
        # 出力ディレクトリを作成
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def select_and_prepare_bgm(self, video_duration: int, script_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        動画の長さに合わせてBGMを選択・準備する
        
        Args:
            video_duration: 動画の長さ（秒）
            script_data: 台本データ
            
        Returns:
            BGM情報辞書
        """
        self.logger.info(f"BGM選択・準備を開始（動画長: {video_duration}秒）")
        
        try:
            # audioディレクトリからBGMファイルを検索
            bgm_file = self._find_bgm_file()
            if not bgm_file:
                self.logger.warning("BGMファイルが見つかりません")
                return self._create_fallback_bgm_info(video_duration)
            
            self.logger.info(f"BGM準備完了: {bgm_file.name}")
            self.logger.info(f"動画長: {video_duration}秒 - BGMをループ再生します")
            
            # BGM情報を返す
            bgm_info = {
                'file_path': str(bgm_file),  # 元のファイルパス
                'duration': video_duration,
                'original_duration': 0,  # pydubを使わないため不明
                'volume': self.bgm_settings.get('volume', -20),  # dB
                'fade_in': self.bgm_settings.get('fade_in', 1000),  # ミリ秒
                'fade_out': self.bgm_settings.get('fade_out', 1000),  # ミリ秒
                'type': 'loop_bgm',
                'description': f'BGMループ再生（{bgm_file.name}）'
            }
            
            return bgm_info
            
        except Exception as e:
            self.logger.error(f"BGM準備でエラー: {e}")
            return self._create_fallback_bgm_info(video_duration)
    

    
    def _find_bgm_file(self) -> Optional[Path]:
        """
        audioディレクトリからBGMファイルを検索
        
        Returns:
            見つかったBGMファイルのパス（見つからない場合はNone）
        """
        if not self.output_dir.exists():
            self.logger.warning(f"audioディレクトリが存在しません: {self.output_dir}")
            return None
        
        # MP3ファイルのみ検索
        for mp3_file in self.output_dir.glob("*.mp3"):
            if mp3_file.is_file():
                self.logger.info(f"BGMファイルを発見: {mp3_file.name}")
                return mp3_file
        
        self.logger.warning(f"audioディレクトリにMP3ファイルが見つかりません: {self.output_dir}")
        return None
    
    def _create_fallback_bgm_info(self, video_duration: int) -> Dict[str, Any]:
        """
        フォールバック用のBGM情報を作成
        
        Args:
            video_duration: 動画の長さ（秒）
            
        Returns:
            フォールバックBGM情報
        """
        self.logger.warning("BGMファイルが見つからないため、無音で処理を続行")
        
        return {
            'file_path': None,
            'duration': video_duration,
            'original_duration': 0,
            'volume': -30,
            'fade_in': 500,
            'fade_out': 500,
            'type': 'no_bgm',
            'description': 'BGMなし（無音）'
        }
    
    def apply_volume_and_fade(self, bgm_info: Dict[str, Any]) -> Optional[str]:
        """
        BGMに音量調整とフェード効果を適用（簡素化版）
        
        Args:
            bgm_info: BGM情報
            
        Returns:
            処理済みBGMファイルパス（失敗時はNone）
        """
        if not bgm_info.get('file_path'):
            self.logger.warning("BGMファイルパスがありません")
            return None
        
        try:
            # pydubを使わないため、元のファイルをそのまま使用
            original_path = Path(bgm_info['file_path'])
            if not original_path.exists():
                self.logger.error(f"BGMファイルが存在しません: {original_path}")
                return None
            
            # 処理済みBGMとして元のファイルをコピー
            output_path = self.output_dir / f"bgm_processed_{bgm_info['duration']}s.mp3"
            shutil.copy2(original_path, output_path)
            
            self.logger.info(f"BGM処理完了: {output_path}")
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"BGM処理でエラー: {e}")
            return None 