#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_loader.pyのテストスクリプト
config.jsonの読み込みと検証が正しく動作するか確認
"""

import sys
import os
from pathlib import Path

# processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent / "process"))

from config_loader import get_config, load_config, validate_config

def test_config_loading():
    """config.jsonの読み込みテスト"""
    print("=" * 60)
    print("config.json読み込みテスト")
    print("=" * 60)
    
    try:
        config = get_config()
        print("✓ config.jsonの読み込みに成功しました")
        return config
    except Exception as e:
        print(f"✗ config.jsonの読み込みに失敗しました: {e}")
        return None

def test_realtime_video_config(config):
    """realtime_videoセクションの確認"""
    print("\n" + "=" * 60)
    print("realtime_videoセクションの確認")
    print("=" * 60)
    
    if config is None:
        print("✗ configがNoneのため、確認をスキップします")
        return
    
    if "realtime_video" not in config:
        print("✗ realtime_videoセクションが見つかりません")
        return
    
    rt_config = config["realtime_video"]
    print("✓ realtime_videoセクションが見つかりました")
    
    # 各設定項目の確認
    sections = {
        "camera": ["device_id", "fps"],
        "difference": ["threshold_pixels", "threshold_ratio"],
        "alignment": ["homography_reuse_seconds"],
        "save": ["archive_no_diff", "archive_path"],
        "display": ["enable", "show"],
        "streaming": ["enable", "protocol", "port", "address"]
    }
    
    for section_name, keys in sections.items():
        if section_name in rt_config:
            print(f"\n  [{section_name}]")
            section = rt_config[section_name]
            for key in keys:
                if key in section:
                    value = section[key]
                    print(f"    {key}: {value} ({type(value).__name__})")
                else:
                    print(f"    ✗ {key}: 見つかりません")
        else:
            print(f"\n  ✗ [{section_name}]: セクションが見つかりません")

def test_config_validation(config):
    """configの検証テスト"""
    print("\n" + "=" * 60)
    print("config検証テスト")
    print("=" * 60)
    
    if config is None:
        print("✗ configがNoneのため、検証をスキップします")
        return
    
    try:
        is_valid = validate_config(config)
        if is_valid:
            print("✓ configの検証に成功しました")
        else:
            print("✗ configの検証に失敗しました")
    except Exception as e:
        print(f"✗ configの検証中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

def main():
    """メイン関数"""
    print("config_loader.py テスト開始\n")
    
    # config読み込みテスト
    config = test_config_loading()
    
    # realtime_videoセクションの確認
    test_realtime_video_config(config)
    
    # config検証テスト
    test_config_validation(config)
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    main()

