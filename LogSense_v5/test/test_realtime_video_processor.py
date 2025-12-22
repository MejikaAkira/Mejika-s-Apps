#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_video_processor.pyのテストスクリプト
既存の静止画像を使用して、動画処理の動作を確認
"""

import sys
import os
from pathlib import Path

# video_processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "video_process"))

import cv2
import logging
from realtime_video_processor import RealtimeVideoProcessor

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def test_with_static_images():
    """
    既存の静止画像を使用してrealtime_video_processorをテスト
    """
    print("=" * 60)
    print("realtime_video_processor.py テスト開始")
    print("=" * 60)
    
    # 既存の画像ファイルを読み込む
    base_image_path = "image_inputs/20251130_132156/bird2_base.png"
    current_image_path = "image_inputs/20251130_132156/bird2_b.png"
    
    if not os.path.exists(base_image_path):
        print(f"エラー: 基準画像が見つかりません: {base_image_path}")
        return False
    
    if not os.path.exists(current_image_path):
        print(f"エラー: 比較画像が見つかりません: {current_image_path}")
        return False
    
    print(f"基準画像: {base_image_path}")
    print(f"比較画像: {current_image_path}")
    
    # 画像を読み込む
    base_frame = cv2.imread(base_image_path)
    current_frame = cv2.imread(current_image_path)
    
    if base_frame is None:
        print(f"エラー: 基準画像の読み込みに失敗: {base_image_path}")
        return False
    
    if current_frame is None:
        print(f"エラー: 比較画像の読み込みに失敗: {current_image_path}")
        return False
    
    print(f"基準画像サイズ: {base_frame.shape}")
    print(f"比較画像サイズ: {current_frame.shape}")
    print()
    
    # RealtimeVideoProcessorを初期化
    processor = RealtimeVideoProcessor()
    
    # 基準フレームを設定
    processor.base_frame = base_frame.copy()
    
    # 出力ディレクトリを初期化
    processor.initialize_output_directories()
    
    print("=" * 60)
    print("フレーム処理テスト")
    print("=" * 60)
    
    # フレームを処理
    result = processor._process_frame(current_frame)
    
    if result is None:
        print("[ERROR] フレーム処理に失敗しました")
        return False
    
    print("[OK] フレーム処理が成功しました")
    print(f"  フレーム番号: {result['frame_number']}")
    print(f"  差分ピクセル数: {result['diff_pixels']}")
    print(f"  差分率: {result['diff_ratio']:.4f}")
    print(f"  差分検出: {'あり' if result['has_difference'] else 'なし'}")
    print()
    
    # 保存されたファイルを確認
    output_dir = processor.output_dir
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        print(f"保存されたファイル数: {len(files)}")
        for f in files:
            print(f"  - {f}")
    else:
        print(f"警告: 出力ディレクトリが見つかりません: {output_dir}")
    
    print()
    print("=" * 60)
    print("テスト完了")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_with_static_images()
    sys.exit(0 if success else 1)

