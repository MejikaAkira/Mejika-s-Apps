#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分計算処理（GPU/CPUハイブリッド最適化版）
画像の位置補正と差分計算を実行し、結果をdiff_outputsフォルダ内に保存
"""

import os
import logging
import cv2
import numpy as np
import json
from datetime import datetime
import glob
from alignment_utils import resize_to_common_size, align_images
from gpu_utils import GpuPipe, smart_threshold_pixels, Timer
from config_loader import get_config

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def process_difference_calculation(output_dir, timestamp):
    """
    差分計算処理のメイン関数（GPU/CPUハイブリッド最適化版）
    """
    logging.info("=== 差分計算処理開始（GPU/CPUハイブリッド） ===")
    logging.info(f"出力ディレクトリ: {output_dir}")
    
    # 出力ディレクトリ作成
    os.makedirs(output_dir, exist_ok=True)
    
    # 位置補正処理（GPU/CPUハイブリッド最適化版）
    logging.info("=== 位置補正処理（GPU/CPUハイブリッド） ===")
    
    # 元の画像を読み込み（位置補正用）
    latest_timestamp = find_latest_timestamp_folder("image_inputs")
    if latest_timestamp is None:
        logging.error("エラー: image_inputs内にタイムスタンプ名のフォルダが見つかりません")
        return None
    
    # 画像名を動的に取得（_baseで終わる画像を基準に、それ以外の画像と全て比較）
    image_dir = f"image_inputs/{latest_timestamp}"
    
    # 画像ファイルを取得（archiveフォルダは除外、png/jpg/jpegに対応）
    image_files = []
    for f in os.listdir(image_dir):
        file_path = os.path.join(image_dir, f)
        # ファイルのみ（ディレクトリは除外）
        if os.path.isfile(file_path):
            # archiveフォルダは除外
            if 'archive' not in f.lower():
                # 画像ファイル形式をチェック
                if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                    image_files.append(f)
    
    # アルファベット順でソート
    image_files.sort()
    
    # _baseで終わる画像を探す（基準画像）
    base_file = None
    other_files = []
    
    for f in image_files:
        # 拡張子を除いたファイル名を取得
        name_without_ext = os.path.splitext(f)[0]
        if name_without_ext.endswith('_base'):
            base_file = f
        else:
            other_files.append(f)
    
    # 基準画像が見つからない場合
    if base_file is None:
        logging.error(f"エラー: '_base'で終わる画像ファイルが見つかりません（見つかったファイル: {image_files}）")
        return None
    
    # 比較対象の画像がない場合
    if len(other_files) == 0:
        logging.error(f"エラー: 比較対象の画像ファイルが見つかりません（基準画像: {base_file}）")
        return None
    
    logging.info(f"検出された画像ファイル: {image_files}")
    logging.info(f"基準画像: {base_file}")
    logging.info(f"比較対象画像: {other_files}")
    
    # 基準画像を読み込み
    base_path = os.path.join(image_dir, base_file)
    base_name = os.path.splitext(base_file)[0]
    
    if not os.path.exists(base_path):
        logging.error(f"エラー: 基準画像ファイルが見つかりません: {base_path}")
        return None
    
    with Timer("base image loading"):
        img_base = cv2.imread(base_path)
    
    if img_base is None:
        logging.error(f"エラー: 基準画像の読み込みに失敗: {base_path}")
        return None
    
    # 各比較対象画像に対して処理を実行
    results = []
    
    for other_file in other_files:
        other_path = os.path.join(image_dir, other_file)
        other_name = os.path.splitext(other_file)[0]
        
        logging.info(f"=== 差分計算対象: {base_name} vs {other_name} ===")
        
        if not os.path.exists(other_path):
            logging.warning(f"警告: 画像ファイルが見つかりません: {other_path}")
            continue
        
        # 比較対象画像を読み込み
        with Timer(f"image loading ({other_name})"):
            img_other = cv2.imread(other_path)
        
        if img_other is None:
            logging.warning(f"警告: 画像の読み込みに失敗: {other_path}")
            continue
        
        # 位置補正処理（GPU/CPUハイブリッド最適化版）
        with Timer(f"alignment processing ({other_name})"):
            img_base_resized, img_other_resized, target_h, target_w, mask_base, mask_other = resize_to_common_size(img_base, img_other)
            img_base_aligned, img_other_aligned, transform_matrix, mask_base_aligned, mask_other_aligned = align_images(img_base_resized, img_other_resized, mask_base, mask_other)
        
        if transform_matrix is None:
            logging.warning(f"警告: 位置補正に失敗: {base_name} vs {other_name}")
            continue
        
        logging.info(f"位置補正完了: サイズ統一({target_h}x{target_w})")
        
        # CV2のみで差分計算（GPU/CPUハイブリッド最適化版）
        config = get_config()
        absdiff_mode = config["image_processing"]["absdiff"]
        
        with Timer(f"difference calculation ({other_name})"):
            use_gpu_absdiff = (absdiff_mode == "GPU") or (absdiff_mode == "auto" and smart_threshold_pixels(img_base_aligned))
            
            if use_gpu_absdiff:
                logging.info("[diff] GPU absdiff path")
                pipe = GpuPipe().upload(img_base_aligned)
                diff_img = pipe.absdiff(img_other_aligned).download()
            else:
                logging.info("[diff] CPU absdiff path")
                diff_img = cv2.absdiff(img_base_aligned, img_other_aligned)
            
            # パディング部分を正確に除外（位置補正後のマスクを使用）
            if mask_base_aligned is not None and mask_other_aligned is not None:
                # 両方の画像で有効な部分（パディングを除いた部分）のみをマスク
                valid_mask = (mask_base_aligned > 127) & (mask_other_aligned > 127)
            else:
                # フォールバック: 両方の画像で黒（0）でない部分を有効と判定
                mask1 = np.any(img_base_aligned > 0, axis=2) if len(img_base_aligned.shape) == 3 else img_base_aligned > 0
                mask2 = np.any(img_other_aligned > 0, axis=2) if len(img_other_aligned.shape) == 3 else img_other_aligned > 0
                valid_mask = mask1 & mask2
            
            # マスクを適用（パディング部分を除外）
            if len(diff_img.shape) == 3:
                mask_3d = np.stack([valid_mask] * 3, axis=2)
                diff_img_masked = diff_img * mask_3d
            else:
                diff_img_masked = diff_img * valid_mask
            
            diff_pixels = np.sum(diff_img_masked > 0)
            logging.info(f"差分ピクセル数（パディング除外後）: {diff_pixels}")
            
            # マスク適用後の差分画像を使用
            diff_img = diff_img_masked
        
        # 結果を保存（画像名を含むファイル名で）
        result_prefix = f"{base_name}_vs_{other_name}"
        
        with Timer(f"result saving ({other_name})"):
            cv2.imwrite(os.path.join(output_dir, f"{result_prefix}_aligned_base.png"), img_base_aligned)
            cv2.imwrite(os.path.join(output_dir, f"{result_prefix}_aligned_other.png"), img_other_aligned)
            cv2.imwrite(os.path.join(output_dir, f"{result_prefix}_difference.png"), diff_img)
        
        # 輪郭座標データを抽出・保存
        contours_data = {
            "timestamp": timestamp,
            "base_image": base_name,
            "other_image": other_name,
            "image_shape": img_base_aligned.shape,
            "alignment_info": {
                "target_h": int(target_h),
                "target_w": int(target_w),
                "transform_matrix": transform_matrix.tolist() if transform_matrix is not None else None
            },
            "difference_pixels": int(diff_pixels),
            "contours": {
                "base_image": [],
                "other_image": []
            }
        }
        
        # 輪郭座標をJSONで保存
        contours_json_path = os.path.join(output_dir, f"{result_prefix}_contours.json")
        with open(contours_json_path, 'w', encoding='utf-8') as f:
            json.dump(contours_data, f, ensure_ascii=False, indent=2)
        
        results.append({
            "base_image": base_name,
            "other_image": other_name,
            "difference_pixels": int(diff_pixels),
            "difference_image": f"{result_prefix}_difference.png",
            "contours_json": contours_json_path
        })
        
        logging.info(f"=== 差分計算完了: {base_name} vs {other_name} ===")
        logging.info(f"差分画像: {os.path.join(output_dir, f'{result_prefix}_difference.png')}")
        logging.info(f"輪郭座標: {contours_json_path}")
    
    logging.info("=== 差分計算処理完了（GPU/CPUハイブリッド） ===")
    logging.info(f"結果保存先: {output_dir}")
    logging.info(f"処理した比較数: {len(results)}")
    
    return output_dir

def find_latest_timestamp_folder(base_dir):
    """
    指定ディレクトリ内の最も新しいタイムスタンプ名のフォルダを取得
    """
    if not os.path.exists(base_dir):
        return None
    
    timestamp_folders = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path) and len(item) == 15 and item[8] == '_':  # YYYYMMDD_HHMMSS形式
            timestamp_folders.append(item)
    
    if not timestamp_folders:
        return None
    
    # タイムスタンプでソート（新しい順）
    timestamp_folders.sort(reverse=True)
    return timestamp_folders[0]

def main():
    """
    メイン処理
    """
    # 最も新しいタイムスタンプ名のフォルダを取得
    latest_timestamp = find_latest_timestamp_folder("image_inputs")
    
    if latest_timestamp is None:
        print("エラー: image_inputs内にタイムスタンプ名のフォルダが見つかりません")
        return
    
    print(f"最新のタイムスタンプフォルダ: {latest_timestamp}")
    
    # 出力ディレクトリ設定
    output_dir = f"diff_outputs/{latest_timestamp}"
    
    # 差分計算処理実行
    result = process_difference_calculation(output_dir, latest_timestamp)
    
    if result:
        print(f"差分計算処理完了: {result}")
    else:
        print("差分計算処理に失敗しました")

if __name__ == "__main__":
    main()
