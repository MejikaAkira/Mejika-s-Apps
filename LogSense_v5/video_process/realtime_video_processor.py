#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
リアルタイム動画差分検出処理モジュール
既存のprocess/内の関数のみを使用
"""

import os
import sys
import logging
import time
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import cv2
import numpy as np

# processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "process"))

from config_loader import get_config
from alignment_utils import resize_to_common_size, align_images
from gpu_utils import GpuPipe, smart_threshold_pixels

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


class HomographyCache:
    """ホモグラフィキャッシュ"""
    def __init__(self, reuse_seconds: float = 1.0):
        self.reuse_seconds = reuse_seconds
        self.matrix: Optional[np.ndarray] = None
        self.timestamp: Optional[float] = None
        self.lock = threading.Lock()
    
    def get(self, current_time: float) -> Optional[np.ndarray]:
        """キャッシュからホモグラフィ行列を取得（再利用期間内の場合のみ）"""
        with self.lock:
            if self.matrix is None or self.timestamp is None:
                return None
            elapsed = current_time - self.timestamp
            if elapsed < self.reuse_seconds:
                return self.matrix.copy()
            return None


class FrameBuffer:
    """フレームバッファ"""
    def __init__(self, maxsize: int = 10):
        self.queue = queue.Queue(maxsize=maxsize)
    
    def put(self, frame_data: Dict[str, Any]):
        try:
            self.queue.put_nowait(frame_data)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(frame_data)
            except queue.Empty:
                pass
    
    def get(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None


class RealtimeVideoProcessor:
    """リアルタイム動画差分検出処理クラス"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = get_config(config_path)
        rt_config = self.config.get("realtime_video", {})
        
        # 設定取得
        camera = rt_config.get("camera", {})
        diff = rt_config.get("difference", {})
        align = rt_config.get("alignment", {})
        save = rt_config.get("save", {})
        buffer = rt_config.get("buffer", {})
        img_proc = self.config.get("image_processing", {})
        
        self.camera_device_id = camera.get("device_id", 0)
        self.camera_fps = camera.get("fps", 30)
        self.threshold_pixels = diff.get("threshold_pixels", 5000)
        self.threshold_ratio = diff.get("threshold_ratio", 0.005)
        self.noise_threshold = diff.get("noise_threshold", 20)
        self.homography_reuse_seconds = align.get("homography_reuse_seconds", 0.1)
        self.archive_no_diff = save.get("archive_no_diff", True)
        self.archive_path = save.get("archive_path", "video_outputs/archive")
        self.frame_buffer_size = buffer.get("frame_buffer_size", 10)
        self.frame_queue_size = buffer.get("frame_queue_size", 5)
        self.absdiff_mode = img_proc.get("absdiff", "CPU")
        self.warp_mode = img_proc.get("warp_perspective", "CPU")
        
        # 初期化
        self.cap: Optional[cv2.VideoCapture] = None
        self.homography_cache = HomographyCache(self.homography_reuse_seconds)
        self.frame_buffer = FrameBuffer(maxsize=self.frame_buffer_size)
        self.is_running = False
        self.is_processing = False
        self.base_frame: Optional[np.ndarray] = None
        self.frame_count = 0
        self.capture_thread: Optional[threading.Thread] = None
        self.process_thread: Optional[threading.Thread] = None
        self.frame_queue: Optional[queue.Queue] = None
        self.output_dir: Optional[str] = None
        self.archive_dir: Optional[str] = None
        self.process_times = []  # 処理時間を記録（テスト用）
    
    def initialize_camera(self) -> bool:
        """カメラを初期化"""
        try:
            self.cap = cv2.VideoCapture(self.camera_device_id)
            if not self.cap.isOpened():
                logging.error(f"カメラを開けませんでした: device_id={self.camera_device_id}")
                return False
            self.cap.set(cv2.CAP_PROP_FPS, self.camera_fps)
            logging.info(f"カメラを初期化しました: device_id={self.camera_device_id}, FPS={self.cap.get(cv2.CAP_PROP_FPS)}")
            return True
        except Exception as e:
            logging.error(f"カメラ初期化中にエラー: {e}")
            return False
    
    def initialize_output_directories(self):
        """出力ディレクトリを初期化"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = f"video_outputs/{timestamp}"
        self.archive_dir = self.archive_path
        os.makedirs(self.output_dir, exist_ok=True)
        if self.archive_no_diff:
            os.makedirs(self.archive_dir, exist_ok=True)
        logging.info(f"出力ディレクトリ: {self.output_dir}")
    
    def start(self):
        """処理を開始"""
        if self.is_running:
            return
        
        if not self.initialize_camera():
            return
        
        self.initialize_output_directories()
        
        ret, frame = self.cap.read()
        if not ret or frame is None:
            logging.error("基準フレームの取得に失敗しました")
            return
        
        self.base_frame = frame.copy()
        
        # ウォーミングアップ処理を実行
        if not self._warmup():
            logging.error("ウォーミングアップ処理に失敗したため、処理を開始できません")
            return
        
        self.is_running = True
        self.is_processing = True
        
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.capture_thread.start()
        self.process_thread.start()
        
        logging.info("リアルタイム動画処理を開始しました")
    
    def stop(self):
        """処理を停止"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.is_processing = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
        if self.process_thread:
            self.process_thread.join(timeout=2.0)
        
        if self.cap:
            self.cap.release()
            self.cap = None
        
        logging.info("リアルタイム動画処理を停止しました")
    
    def _capture_loop(self):
        """カメラからフレームを取得するループ"""
        self.frame_queue = queue.Queue(maxsize=self.frame_queue_size)
        
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.1)
                continue
            
            try:
                self.frame_queue.put_nowait(frame.copy())
            except queue.Full:
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame.copy())
                except queue.Empty:
                    pass
        
        logging.info("カメラ取得ループを終了しました")
    
    def _warmup(self) -> bool:
        """
        ウォーミングアップ処理（OpenCVの初回実行オーバーヘッドを事前に処理）
        
        Returns:
            bool: 成功時True、失敗時False
        """
        if self.base_frame is None:
            logging.error("[warmup] base_frameが設定されていません")
            return False
        
        try:
            logging.info("[warmup] ウォーミングアップ処理を開始します...")
            
            # base_frameのコピーをダミー画像として使用（特徴点マッチングが成功するように）
            # 実際の画像を使用することで、OpenCVの初回実行オーバーヘッドを確実に処理できる
            dummy_frame = self.base_frame.copy()
            
            # フレームカウントを一時的に保存（ウォーミングアップでは増やさない）
            original_frame_count = self.frame_count
            
            # ウォーミングアップ処理を実行（結果は保存しない）
            result = self._process_frame(dummy_frame, skip_save=True)
            
            # フレームカウントを元に戻す
            self.frame_count = original_frame_count
            
            if result is None:
                logging.error("[warmup] ウォーミングアップ処理が失敗しました（_process_frameがNoneを返しました）")
                return False
            
            logging.info("[warmup] ウォーミングアップ処理が完了しました")
            return True
            
        except Exception as e:
            logging.error(f"[warmup] ウォーミングアップ処理中にエラーが発生しました: {e}", exc_info=True)
            return False
    
    def _process_loop(self):
        """フレームを処理するループ"""
        while self.is_running and self.is_processing:
            try:
                if self.frame_queue is None:
                    time.sleep(0.01)
                    continue
                
                current_frame = self.frame_queue.get(timeout=0.1)
                if current_frame is None:
                    continue
                
                self.frame_count += 1
                # 保存処理は別スレッドで実行するため、skip_save=Trueで処理
                result = self._process_frame(current_frame, skip_save=True)
                
                if result:
                    self.frame_buffer.put(result)
            
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"フレーム処理中にエラー: {e}")
        
        logging.info("処理ループを終了しました")
    
    def _process_frame(self, current_frame: np.ndarray, skip_save: bool = False) -> Optional[Dict[str, Any]]:
        """フレームを処理（既存のprocess/内の関数のみ使用）
        
        Args:
            current_frame: 処理するフレーム
            skip_save: Trueの場合、結果を保存しない（ウォーミングアップ用）
        """
        if self.base_frame is None:
            return None
        
        # 処理時間測定開始
        process_start_time = time.time()
        
        try:
            # サイズ統一（既存の関数を使用）
            base_resized, current_resized, _, _, mask_base, mask_current = resize_to_common_size(
                self.base_frame, current_frame
            )
            
            # 位置補正（ホモグラフィキャッシュを活用）
            current_time = time.time()
            cached_homography = self.homography_cache.get(current_time)
            
            if cached_homography is not None:
                # キャッシュが有効: 既存のホモグラフィ行列を使用して直接位置補正
                logging.debug(f"[cache] ホモグラフィキャッシュを使用（経過時間: {current_time - self.homography_cache.timestamp:.3f}秒）")
                h, w = base_resized.shape[:2]
                out_size = (w, h)
                
                # warpPerspective処理（GPU/CPU切り替え）
                use_gpu_warp = (self.warp_mode == "GPU") or (self.warp_mode == "auto" and smart_threshold_pixels(base_resized))
                
                if use_gpu_warp:
                    pipe = GpuPipe().upload(base_resized)
                    H32 = cached_homography.astype(np.float32)
                    g = pipe.g
                    g_out = cv2.cuda.warpPerspective(g, H32, out_size)
                    base_aligned = g_out.download()
                else:
                    base_aligned = cv2.warpPerspective(base_resized, cached_homography, out_size)
                
                current_aligned = current_resized
                transform_matrix = cached_homography
                
                # マスクも位置補正
                mask_base_aligned = None
                if mask_base is not None:
                    mask_base_aligned = cv2.warpPerspective(mask_base, cached_homography, out_size, flags=cv2.INTER_NEAREST)
                    _, mask_base_aligned = cv2.threshold(mask_base_aligned, 127, 255, cv2.THRESH_BINARY)
                mask_current_aligned = mask_current
                
            else:
                # キャッシュが無効: 新しくホモグラフィ計算
                if self.homography_cache.timestamp is not None:
                    elapsed = current_time - self.homography_cache.timestamp
                    logging.debug(f"[cache] ホモグラフィキャッシュが無効（経過時間: {elapsed:.3f}秒 >= {self.homography_reuse_seconds}秒）、新規計算を実行")
                else:
                    logging.debug("[cache] ホモグラフィキャッシュが存在しない、新規計算を実行")
                base_aligned, current_aligned, transform_matrix, mask_base_aligned, mask_current_aligned = align_images(
                    base_resized, current_resized, mask_base, mask_current
                )
                
                if transform_matrix is None:
                    return None
                
                # キャッシュに保存
                with self.homography_cache.lock:
                    self.homography_cache.matrix = transform_matrix
                    self.homography_cache.timestamp = current_time
            
            # 差分計算（動画対応版：既存のprocess/calculate_difference.pyのロジックを使用）
            diff_result = self._calculate_difference_for_video(base_aligned, current_aligned, mask_base_aligned, mask_current_aligned)
            
            result = {
                "frame_number": self.frame_count,
                "original_frame": current_frame,
                "base_aligned": base_aligned,
                "current_aligned": current_aligned,
                "difference": diff_result["diff_img"],
                "diff_pixels": diff_result["diff_pixels"],
                "diff_ratio": diff_result["diff_ratio"],
                "has_difference": diff_result["has_difference"],
                "timestamp": datetime.now()
            }
            
            # 処理時間測定終了（保存処理は含まない）
            process_time = (time.time() - process_start_time) * 1000  # ms
            self.process_times.append(process_time)
            
            # ウォーミングアップ時は保存をスキップ
            if not skip_save:
                self._save_frame(result)
            
            # 直前のフレームとの比較のため、base_frameを更新
            # current_frameは処理が完了するまで保持されるため、参照を保持するだけでOK
            self.base_frame = current_frame
            
            return result
            
        except Exception as e:
            logging.error(f"フレーム処理中にエラー: {e}")
            return None
    
    def _calculate_difference_for_video(self, base_aligned: np.ndarray, current_aligned: np.ndarray,
                                       mask_base: Optional[np.ndarray], mask_current: Optional[np.ndarray]) -> Dict[str, Any]:
        """
        差分を計算（動画対応版）
        既存のprocess/calculate_difference.pyのロジック（207-243行目）をそのまま使用
        """
        # 既存のprocess/calculate_difference.pyの差分計算ロジックをそのまま使用
        use_gpu_absdiff = (self.absdiff_mode == "GPU") or (self.absdiff_mode == "auto" and smart_threshold_pixels(base_aligned))
        
        if use_gpu_absdiff:
            pipe = GpuPipe().upload(base_aligned)
            diff_img = pipe.absdiff(current_aligned).download()
        else:
            diff_img = cv2.absdiff(base_aligned, current_aligned)
        
        # パディング部分を正確に除外（位置補正後のマスクを使用）
        if mask_base is not None and mask_current is not None:
            # 両方の画像で有効な部分（パディングを除いた部分）のみをマスク
            valid_mask = (mask_base > 127) & (mask_current > 127)
        else:
            # フォールバック: 両方の画像で黒（0）でない部分を有効と判定
            mask1 = np.any(base_aligned > 0, axis=2) if len(base_aligned.shape) == 3 else base_aligned > 0
            mask2 = np.any(current_aligned > 0, axis=2) if len(current_aligned.shape) == 3 else current_aligned > 0
            valid_mask = mask1 & mask2
        
        # マスクを適用（パディング部分を除外）
        if len(diff_img.shape) == 3:
            mask_3d = np.stack([valid_mask] * 3, axis=2)
            diff_img_masked = diff_img * mask_3d
        else:
            diff_img_masked = diff_img * valid_mask
        
        # ノイズ除去: 差分値がnoise_threshold未満のピクセルはノイズとして除外
        diff_pixels = int(np.sum(diff_img_masked >= self.noise_threshold))
        diff_ratio = diff_pixels / diff_img_masked.size if diff_img_masked.size > 0 else 0.0
        
        # 閾値判定（動画用）
        has_difference = (diff_pixels >= self.threshold_pixels) or (diff_ratio >= self.threshold_ratio)
        
        return {
            "diff_img": diff_img_masked,
            "diff_pixels": diff_pixels,
            "diff_ratio": diff_ratio,
            "has_difference": has_difference
        }
    
    def _save_frame(self, result: Dict[str, Any]):
        """フレームを保存"""
        frame_number = result["frame_number"]
        frame_filename = f"frame_{frame_number:06d}.png"
        diff_filename = f"frame_{frame_number:06d}_diff.png"
        
        if result["has_difference"]:
            frame_path = os.path.join(self.output_dir, frame_filename)
            diff_path = os.path.join(self.output_dir, diff_filename)
            cv2.imwrite(frame_path, result["original_frame"])
            cv2.imwrite(diff_path, result["difference"])
        elif self.archive_no_diff:
            frame_path = os.path.join(self.archive_dir, frame_filename)
            cv2.imwrite(frame_path, result["original_frame"])


def main():
    """メイン関数（テスト用）"""
    processor = RealtimeVideoProcessor()
    try:
        processor.start()
        time.sleep(10)
    except KeyboardInterrupt:
        logging.info("中断されました")
    finally:
        processor.stop()


if __name__ == "__main__":
    main()

