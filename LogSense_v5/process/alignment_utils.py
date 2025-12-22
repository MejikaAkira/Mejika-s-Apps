#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
位置補正処理ユーティリティ（GPU/CPUハイブリッド最適化版）
成功したtest_image_alignment.pyの実装を参考
config.jsonから設定を読み込んで、ORB/SIFT切り替えとCPU/GPU設定を反映
"""

import logging
import cv2
import numpy as np
from gpu_utils import GpuPipe, smart_threshold_pixels, Timer, USE_GPU
from config_loader import get_config

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# グローバル設定（初回読み込み時に設定）
_config = None

def _get_config():
    """設定を取得（初回のみ読み込み）"""
    global _config
    if _config is None:
        _config = get_config()
    return _config

def resize_to_common_size(img1, img2):
    """
    2つの画像を同じサイズに統一（アスペクト比保持版）
    アスペクト比を保持しながら、パディングでサイズを統一することで、
    位置補正の精度を向上させ、差分画像の境界線問題を解決
    """
    config = _get_config()
    resize_mode = config["image_processing"]["resize"]
    
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    
    # ターゲットサイズ（より大きいサイズに統一）
    target_h = max(h1, h2)
    target_w = max(w1, w2)
    
    def resize_with_aspect_ratio(img, target_h, target_w, use_gpu):
        """アスペクト比を保持しながらリサイズし、パディングでサイズを統一
        戻り値: (padded_image, valid_mask)
        - padded_image: パディング後の画像
        - valid_mask: 元の画像領域（パディングを除いた部分）を示すマスク
        """
        h, w = img.shape[:2]
        aspect_ratio = w / h
        
        # アスペクト比を保持しながらリサイズ
        if aspect_ratio > (target_w / target_h):
            # 幅基準でリサイズ
            new_w = target_w
            new_h = int(target_w / aspect_ratio)
        else:
            # 高さ基準でリサイズ
            new_h = target_h
            new_w = int(target_h * aspect_ratio)
        
        # リサイズ処理
        if use_gpu:
            logging.info(f"[resize] GPU path (aspect ratio preserved: {aspect_ratio:.2f})")
            resized = GpuPipe().upload(img).resize((new_w, new_h)).download()
        else:
            logging.info(f"[resize] CPU path (aspect ratio preserved: {aspect_ratio:.2f})")
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # パディングでサイズを統一（中央配置）
        pad_top = (target_h - new_h) // 2
        pad_bottom = target_h - new_h - pad_top
        pad_left = (target_w - new_w) // 2
        pad_right = target_w - new_w - pad_left
        
        if len(img.shape) == 3:
            # カラー画像
            padded = cv2.copyMakeBorder(resized, pad_top, pad_bottom, pad_left, pad_right,
                                       cv2.BORDER_CONSTANT, value=[0, 0, 0])
        else:
            # グレースケール画像
            padded = cv2.copyMakeBorder(resized, pad_top, pad_bottom, pad_left, pad_right,
                                       cv2.BORDER_CONSTANT, value=0)
        
        # 元の画像領域（パディングを除いた部分）を示すマスクを作成
        valid_mask = np.zeros((target_h, target_w), dtype=np.uint8)
        valid_mask[pad_top:pad_top+new_h, pad_left:pad_left+new_w] = 255
        
        return padded, valid_mask
    
    # リサイズ処理の選択
    use_gpu1 = (resize_mode == "GPU") or (resize_mode == "auto" and smart_threshold_pixels(img1))
    use_gpu2 = (resize_mode == "GPU") or (resize_mode == "auto" and smart_threshold_pixels(img2))
    
    # アスペクト比を保持しながらリサイズ（マスクも取得）
    img1_resized, mask1 = resize_with_aspect_ratio(img1, target_h, target_w, use_gpu1)
    img2_resized, mask2 = resize_with_aspect_ratio(img2, target_h, target_w, use_gpu2)
    
    return img1_resized, img2_resized, target_h, target_w, mask1, mask2

def _detect_features(gray1, gray2, config):
    """特徴点検出（SIFT/ORB切り替え対応）"""
    detector_type = config["feature_detector"]["type"]
    detector_device = config["feature_detector"]["device"]
    
    if detector_type == "SIFT":
        # SIFTはCPUのみ
        sift_config = config["sift"]
        sift = cv2.SIFT_create(
            nfeatures=sift_config["max_features"] if sift_config["max_features"] > 0 else 0,
            contrastThreshold=sift_config["contrast_threshold"],
            edgeThreshold=sift_config["edge_threshold"],
            sigma=sift_config["sigma"]
        )
        with Timer("SIFT features (CPU)"):
            kp1, des1 = sift.detectAndCompute(gray1, None)
            kp2, des2 = sift.detectAndCompute(gray2, None)
        return kp1, des1, kp2, des2, cv2.NORM_L2
    
    elif detector_type == "ORB":
        orb_config = config["orb"]
        
        if detector_device == "GPU" and USE_GPU:
            try:
                orb = cv2.cuda.ORB_create(
                    nfeatures=orb_config["nfeatures"],
                    scaleFactor=orb_config["scaleFactor"],
                    nlevels=orb_config["nlevels"]
                )
                # GPU ORB処理
                gpu_img1 = cv2.cuda_GpuMat()
                gpu_img2 = cv2.cuda_GpuMat()
                gpu_img1.upload(gray1)
                gpu_img2.upload(gray2)
                
                with Timer("ORB features (GPU)"):
                    kp1_gpu, des1_gpu = orb.detectAndCompute(gpu_img1, None)
                    kp2_gpu, des2_gpu = orb.detectAndCompute(gpu_img2, None)
                
                kp1 = orb.downloadKeypoints(kp1_gpu)
                kp2 = orb.downloadKeypoints(kp2_gpu)
                des1 = des1_gpu.download()
                des2 = des2_gpu.download()
                
                return kp1, des1, kp2, des2, cv2.NORM_HAMMING
                
            except Exception as e:
                logging.warning(f"GPU ORB failed, falling back to CPU: {e}")
                # CPUフォールバック
                orb = cv2.ORB_create(
                    nfeatures=orb_config["nfeatures"],
                    scaleFactor=orb_config["scaleFactor"],
                    nlevels=orb_config["nlevels"]
                )
                with Timer("ORB features (CPU)"):
                    kp1, des1 = orb.detectAndCompute(gray1, None)
                    kp2, des2 = orb.detectAndCompute(gray2, None)
                return kp1, des1, kp2, des2, cv2.NORM_HAMMING
        else:
            # CPU ORB
            orb = cv2.ORB_create(
                nfeatures=orb_config["nfeatures"],
                scaleFactor=orb_config["scaleFactor"],
                nlevels=orb_config["nlevels"]
            )
            with Timer("ORB features (CPU)"):
                kp1, des1 = orb.detectAndCompute(gray1, None)
                kp2, des2 = orb.detectAndCompute(gray2, None)
            return kp1, des1, kp2, des2, cv2.NORM_HAMMING
    
    else:
        raise ValueError(f"Unknown detector type: {detector_type}")

def _match_features(des1, des2, norm_type, config):
    """記述子マッチング（CPU/GPU切り替え対応）"""
    matching_device = config["descriptor_matching"]["device"]
    
    if matching_device == "GPU" and USE_GPU:
        try:
            if norm_type == cv2.NORM_L2:
                gpu_matcher = cv2.cuda.DescriptorMatcher_createBFMatcher(cv2.NORM_L2)
            else:
                gpu_matcher = cv2.cuda.DescriptorMatcher_createBFMatcher(cv2.NORM_HAMMING)
            
            gpu_des1 = cv2.cuda_GpuMat()
            gpu_des2 = cv2.cuda_GpuMat()
            gpu_des1.upload(des1)
            gpu_des2.upload(des2)
            
            with Timer("GPU descriptor matching"):
                matches = gpu_matcher.knnMatch(gpu_des1, gpu_des2, k=2)
            
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.7 * n.distance:
                        good_matches.append(m)
            
            logging.info(f"GPU found {len(good_matches)} good matches")
            return good_matches
            
        except Exception as e:
            logging.warning(f"GPU matching failed, falling back to CPU: {e}")
            # CPUフォールバック
            if norm_type == cv2.NORM_L2:
                bf = cv2.BFMatcher()
            else:
                bf = cv2.BFMatcher(cv2.NORM_HAMMING)
            
            with Timer("CPU descriptor matching"):
                matches = bf.knnMatch(des1, des2, k=2)
            
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.7 * n.distance:
                        good_matches.append(m)
            
            logging.info(f"CPU found {len(good_matches)} good matches")
            return good_matches
    else:
        # CPUマッチング
        if norm_type == cv2.NORM_L2:
            bf = cv2.BFMatcher()
        else:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        
        with Timer("CPU descriptor matching"):
            matches = bf.knnMatch(des1, des2, k=2)
        
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < 0.7 * n.distance:
                    good_matches.append(m)
        
        logging.info(f"CPU found {len(good_matches)} good matches")
        return good_matches

def calculate_alignment_coefficients(img1, img2):
    """位置補正係数を算出（画像は返さず、係数のみ）- GPU/CPUハイブリッド最適化版"""
    config = _get_config()
    blur_mode = config["image_processing"]["gaussian_blur"]
    
    # 前処理（ガウシアンブラー）
    use_gpu1 = (blur_mode == "GPU") or (blur_mode == "auto" and smart_threshold_pixels(img1))
    use_gpu2 = (blur_mode == "GPU") or (blur_mode == "auto" and smart_threshold_pixels(img2))
    
    if use_gpu1:
        logging.info("[align] GPU prefilter path for img1")
        img1_prep = GpuPipe().upload(img1).gaussian((3,3),0).download()
    else:
        img1_prep = cv2.GaussianBlur(img1, (3,3), 0)
    
    if use_gpu2:
        logging.info("[align] GPU prefilter path for img2")
        img2_prep = GpuPipe().upload(img2).gaussian((3,3),0).download()
    else:
        img2_prep = cv2.GaussianBlur(img2, (3,3), 0)
    
    # グレースケール変換
    gray1 = cv2.cvtColor(img1_prep, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_prep, cv2.COLOR_BGR2GRAY)
    
    # 特徴点検出（SIFT/ORB切り替え）
    kp1, des1, kp2, des2, norm_type = _detect_features(gray1, gray2, config)
    
    logging.info(f"画像1の特徴点: {len(kp1)}")
    logging.info(f"画像2の特徴点: {len(kp2)}")
    
    if des1 is None or des2 is None or len(des1) < 4 or len(des2) < 4:
        logging.warning("特徴点が不足しています。デフォルト係数を返します。")
        return img1.shape[0], img1.shape[1], None
    
    # 記述子マッチング（CPU/GPU切り替え）
    good_matches = _match_features(des1, des2, norm_type, config)
    
    if len(good_matches) < 4:
        logging.warning("十分なマッチがありません。デフォルト係数を返します。")
        return img1.shape[0], img1.shape[1], None
    
    # ホモグラフィー行列計算
    with Timer("Homography computation"):
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if H is None:
            logging.warning("ホモグラフィー行列の計算に失敗。デフォルト係数を返します。")
            return img1.shape[0], img1.shape[1], None
        
        inliers = np.sum(mask)
        logging.info(f"Homography computed with {inliers} inliers")
    
    # 係数のみを返す（画像は不要）
    return img1.shape[0], img1.shape[1], H

def align_images(img1, img2, mask1=None, mask2=None):
    """特徴点マッチングによる位置補正（GPU/CPUハイブリッド最適化版）
    mask1, mask2: 元の画像領域（パディングを除いた部分）を示すマスク（オプション）
    """
    config = _get_config()
    blur_mode = config["image_processing"]["gaussian_blur"]
    warp_mode = config["image_processing"]["warp_perspective"]
    
    # 前処理（ガウシアンブラー）
    use_gpu1 = (blur_mode == "GPU") or (blur_mode == "auto" and smart_threshold_pixels(img1))
    use_gpu2 = (blur_mode == "GPU") or (blur_mode == "auto" and smart_threshold_pixels(img2))
    
    if use_gpu1:
        logging.info("[align] GPU prefilter path for img1")
        img1_prep = GpuPipe().upload(img1).gaussian((3,3),0).download()
    else:
        img1_prep = cv2.GaussianBlur(img1, (3,3), 0)
    
    if use_gpu2:
        logging.info("[align] GPU prefilter path for img2")
        img2_prep = GpuPipe().upload(img2).gaussian((3,3),0).download()
    else:
        img2_prep = cv2.GaussianBlur(img2, (3,3), 0)
    
    # グレースケール変換
    gray1 = cv2.cvtColor(img1_prep, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_prep, cv2.COLOR_BGR2GRAY)
    
    # 特徴点検出（SIFT/ORB切り替え）
    kp1, des1, kp2, des2, norm_type = _detect_features(gray1, gray2, config)
    
    logging.info(f"画像1の特徴点: {len(kp1)}")
    logging.info(f"画像2の特徴点: {len(kp2)}")
    
    if des1 is None or des2 is None or len(des1) < 4 or len(des2) < 4:
        logging.warning("特徴点が不足しています。元画像を返します。")
        return img1, img2, None
    
    # 記述子マッチング（CPU/GPU切り替え）
    good_matches = _match_features(des1, des2, norm_type, config)
    
    if len(good_matches) < 4:
        logging.warning("十分なマッチがありません。元画像を返します。")
        return img1, img2, None
    
    # ホモグラフィー行列計算
    with Timer("Homography computation"):
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if H is None:
            logging.warning("ホモグラフィー行列の計算に失敗。元画像を返します。")
            return img1, img2, None
        
        inliers = np.sum(mask)
        logging.info(f"Homography computed with {inliers} inliers")
    
    # 画像変換（warpPerspective）
    h, w = img1.shape[:2]
    out_size = (w, h)
    
    use_gpu_warp = (warp_mode == "GPU") or (warp_mode == "auto" and smart_threshold_pixels(img1))
    
    if use_gpu_warp:
        logging.info("[align] GPU warpPerspective (cudawarping)")
        pipe = GpuPipe().upload(img1)
        H32 = H.astype(np.float32)
        g = pipe.g
        with Timer("CUDA warpPerspective"):
            g_out = cv2.cuda.warpPerspective(g, H32, out_size)
        img1_aligned = g_out.download()
    else:
        logging.info("[align] CPU warpPerspective")
        img1_aligned = cv2.warpPerspective(img1, H, out_size)
    
    # マスクも位置補正（パディング部分を正確に除外するため）
    mask1_aligned = None
    if mask1 is not None:
        mask1_aligned = cv2.warpPerspective(mask1, H, out_size, flags=cv2.INTER_NEAREST)
        # マスクはバイナリなので、閾値処理
        _, mask1_aligned = cv2.threshold(mask1_aligned, 127, 255, cv2.THRESH_BINARY)
    
    return img1_aligned, img2, H, mask1_aligned, mask2
