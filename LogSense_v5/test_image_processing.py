#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画像処理の動作確認テスト"""

import sys
from pathlib import Path

# processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent / "process"))

try:
    from alignment_utils import resize_to_common_size, align_images
    from gpu_utils import GpuPipe, smart_threshold_pixels
    from config_loader import get_config
    import cv2
    import numpy as np
    
    print("✓ 既存のprocess/内の関数のインポート成功")
    
    # 設定読み込みテスト
    config = get_config()
    print("✓ config.jsonの読み込み成功")
    
    # 簡単な画像処理テスト（ダミー画像）
    img1 = np.zeros((100, 100, 3), dtype=np.uint8)
    img2 = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # resize_to_common_sizeのテスト
    base_resized, current_resized, target_h, target_w, mask_base, mask_current = resize_to_common_size(img1, img2)
    print(f"✓ resize_to_common_size成功: {base_resized.shape}, {current_resized.shape}")
    
    # align_imagesのテスト
    base_aligned, current_aligned, transform_matrix, mask_base_aligned, mask_current_aligned = align_images(
        base_resized, current_resized, mask_base, mask_current
    )
    print(f"✓ align_images成功: transform_matrix is not None = {transform_matrix is not None}")
    
    # 差分計算のテスト（cv2.absdiff）
    diff_img = cv2.absdiff(base_aligned, current_aligned)
    print(f"✓ cv2.absdiff成功: {diff_img.shape}")
    
    print("\n✓ 全ての画像処理関数が正常に動作しています")
    
except Exception as e:
    print(f"✗ エラー: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

