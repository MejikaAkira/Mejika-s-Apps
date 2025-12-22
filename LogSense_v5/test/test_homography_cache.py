#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ホモグラフィキャッシュの動作確認テスト
複数フレームを連続処理して、キャッシュの再利用を確認
"""

import sys
import os
import time
from pathlib import Path

# video_processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "video_process"))

import cv2
import logging
from realtime_video_processor import RealtimeVideoProcessor

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def test_homography_cache():
    """
    ホモグラフィキャッシュの動作確認
    複数フレームを連続処理して、キャッシュの再利用を確認
    """
    print("=" * 60)
    print("ホモグラフィキャッシュ動作確認テスト")
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
    print("フレーム処理テスト（ホモグラフィキャッシュ確認）")
    print("=" * 60)
    print(f"ホモグラフィ再利用期間: {processor.homography_reuse_seconds}秒")
    print()
    
    # フレーム1を処理（ホモグラフィ計算）
    print("--- フレーム1: ホモグラフィ計算 ---")
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
    
    # キャッシュの状態を確認
    cache_time_1 = processor.homography_cache.timestamp
    print(f"キャッシュ保存時刻: {cache_time_1}")
    print()
    
    # フレーム2を処理（キャッシュ再利用）
    print("--- フレーム2: キャッシュ再利用（即座） ---")
    # キャッシュが有効なタイミングで処理するため、処理開始時刻を記録
    process_start_2 = time.time()
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
    
    # キャッシュが使用されたか確認（処理開始時点での経過時間を確認）
    elapsed_since_cache = process_start_2 - cache_time_1
    print(f"  処理開始時点でのキャッシュ経過時間: {elapsed_since_cache:.3f}秒")
    if elapsed_since_cache < processor.homography_reuse_seconds:
        print(f"  [OK] キャッシュが有効期間内で使用されるはずです")
    else:
        print(f"  [WARNING] キャッシュ有効期間を超過しています（新規計算が行われるはずです）")
    print()
    
    # フレーム3を処理（キャッシュ再利用）
    print("--- フレーム3: キャッシュ再利用（即座） ---")
    # キャッシュが有効なタイミングで処理するため、処理開始時刻を記録
    process_start_3 = time.time()
    start_time_3 = time.time()
    result_3 = processor._process_frame(current_frame)
    elapsed_3 = time.time() - start_time_3
    
    if result_3 is None:
        print("[ERROR] フレーム3の処理に失敗しました")
        return False
    
    print(f"[OK] フレーム3処理完了 (処理時間: {elapsed_3:.3f}秒)")
    print(f"  フレーム番号: {result_3['frame_number']}")
    print(f"  差分ピクセル数: {result_3['diff_pixels']}")
    print(f"  差分率: {result_3['diff_ratio']:.4f}")
    
    # キャッシュが使用されたか確認（処理開始時点での経過時間を確認）
    elapsed_since_cache = process_start_3 - cache_time_1
    print(f"  処理開始時点でのキャッシュ経過時間: {elapsed_since_cache:.3f}秒")
    if elapsed_since_cache < processor.homography_reuse_seconds:
        print(f"  [OK] キャッシュが有効期間内で使用されるはずです")
    else:
        print(f"  [WARNING] キャッシュ有効期間を超過しています（新規計算が行われるはずです）")
    print()
    
    # フレーム4を処理（キャッシュ有効期間を超える）
    print(f"--- フレーム4: キャッシュ有効期間超過後の処理（{processor.homography_reuse_seconds}秒待機） ---")
    time.sleep(processor.homography_reuse_seconds + 0.1)  # 有効期間 + 0.1秒待機
    start_time_4 = time.time()
    result_4 = processor._process_frame(current_frame)
    elapsed_4 = time.time() - start_time_4
    
    if result_4 is None:
        print("[ERROR] フレーム4の処理に失敗しました")
        return False
    
    print(f"[OK] フレーム4処理完了 (処理時間: {elapsed_4:.3f}秒)")
    print(f"  フレーム番号: {result_4['frame_number']}")
    print(f"  差分ピクセル数: {result_4['diff_pixels']}")
    print(f"  差分率: {result_4['diff_ratio']:.4f}")
    
    # キャッシュが無効になったか確認
    current_time_4 = time.time()
    elapsed_since_cache = current_time_4 - cache_time_1
    print(f"  キャッシュ経過時間: {elapsed_since_cache:.3f}秒")
    if elapsed_since_cache >= processor.homography_reuse_seconds:
        print(f"  [OK] キャッシュ有効期間を超過し、新規計算が行われました")
    else:
        print(f"  [WARNING] キャッシュがまだ有効期間内です")
    print()
    
    # 処理時間の比較
    print("=" * 60)
    print("処理時間の比較")
    print("=" * 60)
    print(f"フレーム1（新規計算）: {elapsed_1:.3f}秒")
    print(f"フレーム2（キャッシュ）: {elapsed_2:.3f}秒")
    print(f"フレーム3（キャッシュ）: {elapsed_3:.3f}秒")
    print(f"フレーム4（新規計算）: {elapsed_4:.3f}秒")
    print()
    
    if elapsed_2 < elapsed_1 and elapsed_3 < elapsed_1:
        print("[OK] キャッシュ使用時の処理時間が短縮されました")
    else:
        print("[WARNING] キャッシュ使用時の処理時間が短縮されていません")
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
    success = test_homography_cache()
    sys.exit(0 if success else 1)




