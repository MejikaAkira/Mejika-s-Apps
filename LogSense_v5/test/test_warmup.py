#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ウォーミングアップ機能のテストスクリプト
"""

import sys
import os
from pathlib import Path

# video_processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "video_process"))

import cv2
import logging
import time
from realtime_video_processor import RealtimeVideoProcessor

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def test_warmup():
    """
    ウォーミングアップ機能のテスト
    """
    print("=" * 60)
    print("ウォーミングアップ機能テスト")
    print("=" * 60)
    
    # テスト用画像を読み込む
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
    print()
    
    # 画像を読み込む
    base_frame = cv2.imread(base_image_path)
    current_frame = cv2.imread(current_image_path)
    
    if base_frame is None or current_frame is None:
        print("エラー: 画像の読み込みに失敗しました")
        return False
    
    # RealtimeVideoProcessorを初期化
    processor = RealtimeVideoProcessor()
    
    # 基準フレームを設定
    processor.base_frame = base_frame.copy()
    
    # 出力ディレクトリを初期化
    processor.initialize_output_directories()
    
    print("=" * 60)
    print("ウォーミングアップ処理テスト")
    print("=" * 60)
    
    # ウォーミングアップ処理を実行
    print("--- ウォーミングアップ処理開始 ---")
    start_time = time.time()
    warmup_success = processor._warmup()
    elapsed_time = time.time() - start_time
    
    if not warmup_success:
        print("[ERROR] ウォーミングアップ処理に失敗しました")
        return False
    
    print(f"[OK] ウォーミングアップ処理が完了しました (処理時間: {elapsed_time:.3f}秒)")
    print()
    
    # ウォーミングアップ後のフレーム処理をテスト
    print("--- ウォーミングアップ後のフレーム処理テスト ---")
    
    # フレーム1を処理（ウォーミングアップ後なので高速になるはず）
    print("フレーム1を処理...")
    start_time_1 = time.time()
    result_1 = processor._process_frame(current_frame)
    elapsed_1 = time.time() - start_time_1
    
    if result_1 is None:
        print("[ERROR] フレーム1の処理に失敗しました")
        return False
    
    print(f"[OK] フレーム1処理完了 (処理時間: {elapsed_1:.3f}秒)")
    print(f"  フレーム番号: {result_1['frame_number']}")
    print(f"  差分ピクセル数: {result_1['diff_pixels']}")
    print(f"  差分率: {result_1['diff_ratio']:.4f}")
    print()
    
    # フレーム2を処理（キャッシュ使用）
    print("フレーム2を処理（キャッシュ使用）...")
    start_time_2 = time.time()
    result_2 = processor._process_frame(current_frame)
    elapsed_2 = time.time() - start_time_2
    
    if result_2 is None:
        print("[ERROR] フレーム2の処理に失敗しました")
        return False
    
    print(f"[OK] フレーム2処理完了 (処理時間: {elapsed_2:.3f}秒)")
    print(f"  フレーム番号: {result_2['frame_number']}")
    print(f"  差分ピクセル数: {result_2['diff_pixels']}")
    print(f"  差分率: {result_2['diff_ratio']:.4f}")
    print()
    
    # 処理時間の比較
    print("=" * 60)
    print("処理時間の比較")
    print("=" * 60)
    print(f"ウォーミングアップ処理: {elapsed_time:.3f}秒")
    print(f"フレーム1（ウォーミングアップ後）: {elapsed_1:.3f}秒")
    print(f"フレーム2（キャッシュ使用）: {elapsed_2:.3f}秒")
    print()
    
    # ウォーミングアップ後の処理時間が短いことを確認
    if elapsed_1 < 0.5:  # ウォーミングアップ後は0.5秒以下になるはず
        print("[OK] ウォーミングアップ後の処理時間が短縮されました")
    else:
        print("[WARNING] ウォーミングアップ後の処理時間が期待より長いです")
    print()
    
    # 保存されたファイルを確認
    output_dir = processor.output_dir
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        print(f"保存されたファイル数: {len(files)}")
        for f in sorted(files):
            print(f"  - {f}")
    else:
        print(f"警告: 出力ディレクトリが見つかりません: {output_dir}")
    
    print()
    print("=" * 60)
    print("テスト完了")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_warmup()
    sys.exit(0 if success else 1)

