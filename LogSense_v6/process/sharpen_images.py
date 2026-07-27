#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画像シャープ化処理（GPU/CPUハイブリッド最適化版）
pre_image_inputsフォルダ内の画像をシャープ化し、image_inputsフォルダ内にタイムスタンプ名のフォルダを作成して保存
"""

import os
import logging
import cv2
import numpy as np
from datetime import datetime
import shutil
from gpu_utils import GpuPipe, smart_threshold_pixels, Timer
from config_loader import get_config

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

def preprocess_input_image(image):
    """
    画像の前処理（GPU/CPUハイブリッド最適化版）
    config.jsonから設定を読み込んで、CPU/GPUを選択
    """
    config = get_config()
    sharpen_mode = config["image_processing"]["sharpen"]
    
    # ガウシアンブラー処理の選択
    use_gpu = (sharpen_mode == "GPU") or (sharpen_mode == "auto" and smart_threshold_pixels(image))
    
    if use_gpu:
        logging.info("[sharpen] use GPU path")
        pipe = GpuPipe().upload(image)
        blurred = pipe.gaussian((3,3), 0).download()
    else:
        logging.info("[sharpen] use CPU path")
        blurred = cv2.GaussianBlur(image, (3,3), 0)
    
    # アンシャープマスク（CPUでOK：メモリ軽く、精度も同じ）
    with Timer("unsharp mask"):
        sharp = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    
    return sharp

def sharpen_images():
    """
    画像シャープ化処理のメイン関数（GPU/CPUハイブリッド最適化版）
    """
    logging.info("=== 画像シャープ化処理開始（GPU/CPUハイブリッド） ===")
    
    # タイムスタンプ生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"タイムスタンプ: {timestamp}")
    
    # 入力・出力ディレクトリ
    input_dir = "pre_image_inputs"
    output_dir = f"image_inputs/{timestamp}"
    
    # 出力ディレクトリ作成
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"出力ディレクトリ作成: {output_dir}")
    
    # 既存のimage_inputs内の画像をarchiveに移動
    if os.path.exists("image_inputs"):
        for item in os.listdir("image_inputs"):
            if item != "archive" and item != timestamp:
                item_path = os.path.join("image_inputs", item)
                if os.path.isfile(item_path):
                    archive_dir = "image_inputs/archive"
                    os.makedirs(archive_dir, exist_ok=True)
                    shutil.move(item_path, os.path.join(archive_dir, item))
                    logging.info(f"既存ファイルをarchiveに移動: {item}")
    
    # 入力ディレクトリの画像を処理
    if not os.path.exists(input_dir):
        logging.error(f"エラー: {input_dir}ディレクトリが存在しません")
        return None
    
    processed_count = 0
    total_time = 0
    
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            
            logging.info(f"処理中: {filename}")
            
            # 画像読み込み
            image = cv2.imread(input_path)
            if image is None:
                logging.warning(f"警告: {filename}の読み込みに失敗")
                continue
            
            # シャープ化処理（GPU/CPU自動切り替え）
            with Timer(f"sharpen_{filename}"):
                sharpened_image = preprocess_input_image(image)
            
            # 保存
            cv2.imwrite(output_path, sharpened_image)
            processed_count += 1
            logging.info(f"保存完了: {output_path}")
    
    logging.info(f"=== 処理完了: {processed_count}枚の画像を処理 ===")
    return timestamp

if __name__ == "__main__":
    timestamp = sharpen_images()
    if timestamp:
        print(f"タイムスタンプ: {timestamp}")
    else:
        print("処理に失敗しました")
