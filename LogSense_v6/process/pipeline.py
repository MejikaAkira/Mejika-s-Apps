#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一連の処理パイプライン
画像シャープ化 → 位置補正 → SAM2処理 → 差分計算の全工程を実行
"""

import os
import sys
from datetime import datetime

# 現在のディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sharpen_images import sharpen_images
from calculate_difference import process_difference_calculation, find_latest_timestamp_folder as find_diff_timestamp

def run_pipeline():
    """
    一連の処理パイプラインを実行
    """
    print("=" * 60)
    print("=== SAM2差分検出パイプライン開始 ===")
    print("=" * 60)
    
    # タイムスタンプを記録（全工程で同じタイムスタンプを使用）
    start_time = datetime.now()
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    
    print(f"処理開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"タイムスタンプ: {timestamp}")
    print()
    
    # ステップ1: 画像シャープ化処理
    print("=" * 40)
    print("ステップ1: 画像シャープ化処理")
    print("=" * 40)
    
    try:
        sharpen_timestamp = sharpen_images()
        if sharpen_timestamp is None:
            print("エラー: 画像シャープ化処理に失敗")
            return False
        
        print(f"画像シャープ化処理完了: {sharpen_timestamp}")
        print()
    except Exception as e:
        print(f"エラー: 画像シャープ化処理で例外が発生: {e}")
        return False
    
    # ステップ2: 差分計算処理
    print("=" * 40)
    print("ステップ2: 差分計算処理")
    print("=" * 40)
    
    try:
        # 最新のタイムスタンプフォルダを取得
        latest_timestamp = find_diff_timestamp("image_inputs")
        if latest_timestamp is None:
            print("エラー: image_inputs内にタイムスタンプ名のフォルダが見つかりません")
            return False
        
        # 差分計算処理（SAM2処理なし）
        output_dir = f"diff_outputs/{latest_timestamp}"
        
        diff_result = process_difference_calculation(output_dir, latest_timestamp)
        if diff_result is None:
            print("エラー: 差分計算処理に失敗")
            return False
        
        print(f"差分計算処理完了: {diff_result}")
        print()
    except Exception as e:
        print(f"エラー: 差分計算処理で例外が発生: {e}")
        return False
    
    # 処理完了
    end_time = datetime.now()
    processing_time = end_time - start_time
    
    print("=" * 60)
    print("=== パイプライン処理完了 ===")
    print("=" * 60)
    print(f"処理開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"処理終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"処理時間: {processing_time}")
    print(f"タイムスタンプ: {timestamp}")
    print()
    print("処理結果:")
    print(f"  シャープ化画像: image_inputs/{timestamp}")
    print(f"  位置補正画像: aligned_image_inputs/{timestamp}")
    print(f"  SAM2結果: sam2_outputs/{timestamp}")
    print(f"  差分結果: diff_outputs/{timestamp}")
    print()
    print("主要な出力ファイル:")
    print(f"  差分画像: diff_outputs/{timestamp}/difference.png")
    print(f"  輪郭座標: diff_outputs/{timestamp}/contours.json")
    print(f"  ホモグラフィー行列: aligned_image_inputs/{timestamp}/homography_matrices.json")
    print(f"  SAM2結果: sam2_outputs/{timestamp}/sam2_results.json")
    
    return True

def main():
    """
    メイン処理
    """
    success = run_pipeline()
    
    if success:
        print("\n[SUCCESS] パイプライン処理が正常に完了しました")
        return 0
    else:
        print("\n[ERROR] パイプライン処理に失敗しました")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
