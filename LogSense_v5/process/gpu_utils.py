# -*- coding: utf-8 -*-
"""
GPU/CPU切り替えユーティリティ
目的：GPU/CPUを安全に切替しつつ、転送回数を最小化して高速化するユーティリティ
ログは解析しやすいようINFO/ERRORを詳細に出力
"""

import os
import logging
import time
import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

def _cuda_available() -> bool:
    """CUDAが利用可能かチェック"""
    try:
        return hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0
    except Exception as e:
        logging.warning(f"[gpu_utils] cuda availability check failed: {e}")
        return False

# 環境変数とCUDA可用性をチェック
USE_GPU_ENV = os.getenv("USE_GPU", "true").lower() == "true"
CUDA_OK = _cuda_available()
USE_GPU = USE_GPU_ENV and CUDA_OK

if USE_GPU:
    logging.info("[gpu_utils] GPUモードで実行（USE_GPU=true かつ CUDA 有効）")
else:
    logging.info("[gpu_utils] CPUモードで実行（USE_GPU=false または CUDA 無効）")

class Timer:
    """処理時間測定用コンテキストマネージャー"""
    def __init__(self, tag=""):
        self.tag = tag
        self.t0 = None
    
    def __enter__(self):
        self.t0 = time.time()
        return self
    
    def __exit__(self, exc_type, exc, tb):
        dt = (time.time() - self.t0) * 1000
        logging.info(f"[timer] {self.tag}: {dt:.2f} ms")

class GpuPipe:
    """GPU前処理→（必要なら）CPU後段 までをまとめる簡易パイプ
    - upload() 後はなるべく GPU 内で連続処理
    - 最後だけ download() でCPUへ戻す
    """
    def __init__(self):
        self.stream = cv2.cuda_Stream() if USE_GPU else None
        self.g = None  # cv2.cuda_GpuMat
        self.cpu = None  # CPU画像のバックアップ
    
    def upload(self, img: np.ndarray):
        """画像をGPUにアップロード（変更前：都度 upload/download していた）"""
        # 変更後：最初に一度だけ upload → GPUに滞在
        if not USE_GPU:
            self.g = None
            self.cpu = img
            logging.info("[GpuPipe] CPU画像を保持（GPU無効）")
            return self
        
        self.g = cv2.cuda_GpuMat()
        self.g.upload(img, self.stream)
        logging.info(f"[GpuPipe] upload: shape={img.shape}, dtype={img.dtype}")
        return self
    
    def gaussian(self, ksize=(15,15), sigma=0):
        """ガウシアンフィルタ適用"""
        if not USE_GPU:
            # CPUフォールバック
            with Timer("CPU GaussianBlur"):
                self.cpu = cv2.GaussianBlur(self.cpu, ksize, sigma)
            return self
        
        with Timer("CUDA Gaussian (cudafilters)"):
            filt = cv2.cuda.createGaussianFilter(self.g.type(), self.g.type(), ksize, sigma)
            self.g = filt.apply(self.g, stream=self.stream)
        return self
    
    def resize(self, size):
        """画像リサイズ"""
        if not USE_GPU:
            with Timer("CPU resize"):
                self.cpu = cv2.resize(self.cpu, size)
            return self
        
        with Timer("CUDA resize (cudawarping)"):
            self.g = cv2.cuda.resize(self.g, size, stream=self.stream)
        return self
    
    def cvtcolor(self, code):
        """色空間変換"""
        if not USE_GPU:
            with Timer("CPU cvtColor"):
                self.cpu = cv2.cvtColor(self.cpu, code)
            return self
        
        with Timer("CUDA cvtColor"):
            self.g = cv2.cuda.cvtColor(self.g, code, stream=self.stream)
        return self
    
    def absdiff(self, other_img: np.ndarray):
        """絶対差分計算"""
        if not USE_GPU:
            with Timer("CPU absdiff"):
                self.cpu = cv2.absdiff(self.cpu, other_img)
            return self
        
        with Timer("CUDA absdiff"):
            other = cv2.cuda_GpuMat()
            other.upload(other_img, self.stream)
            self.g = cv2.cuda.absdiff(self.g, other, stream=self.stream)
        return self
    
    def download(self) -> np.ndarray:
        """GPUからCPUにダウンロード"""
        if not USE_GPU:
            return self.cpu
        
        out = self.g.download(self.stream)
        logging.info(f"[GpuPipe] download: shape={out.shape}, dtype={out.dtype}")
        return out

def smart_threshold_pixels(img: np.ndarray, threshold: int = 1280*720) -> bool:
    """画像が大きい時だけGPUを使う簡易ヒューリスティクス"""
    if not USE_GPU:
        return False
    
    H, W = img.shape[:2]
    use = (H * W) >= threshold
    logging.info(f"[gpu_utils] smart_threshold_pixels={use} for {W}x{H}")
    return use

def safe_read_buildinfo():
    """OpenCVビルド情報を安全に取得"""
    info = cv2.getBuildInformation()
    logging.info("[gpu_utils] CUDA enabled? -> %s", "NVIDIA CUDA: YES" in info)
    logging.info("[gpu_utils] cuDNN enabled? -> %s", "cuDNN: YES" in info)
    return info

def get_gpu_memory_info():
    """GPUメモリ情報を取得（利用可能な場合）"""
    if not USE_GPU:
        return "GPU not available"
    
    try:
        # OpenCV CUDAのメモリ情報（簡易版）
        device_count = cv2.cuda.getCudaEnabledDeviceCount()
        return f"CUDA devices: {device_count}"
    except Exception as e:
        return f"GPU memory info unavailable: {e}"
