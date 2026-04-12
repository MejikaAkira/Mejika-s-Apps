#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分ストリーム（1フレーム＝差分可視化 BGR）→ YOLO → オーバーレイ・ログ。
ライブの1ティックごとに差分1枚へ推論（間引きは min_interval_ms）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from diff_mask import compute_difference_visual
from gsplat_placeholder import refine_detections_3dgs
from roi_gaussian_blur import apply_roi_gaussian_blur
from yolo_infer import Detection, detections_to_dicts, load_yolo, predict_frame

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return (_PROJECT_ROOT / path).resolve()


def load_yolo_stream_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else _PROJECT_ROOT / "yolo_stream_config.json"
    if not path.is_file():
        raise FileNotFoundError(f"設定が見つかりません: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def draw_detections_on_bgr(bgr: np.ndarray, detections: List[Detection]) -> np.ndarray:
    out = bgr.copy()
    for d in detections:
        x1, y1, x2, y2 = [int(round(x)) for x in d.xyxy]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{d.name} {d.conf:.2f}"
        cv2.putText(
            out,
            label,
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return out


class StreamingYoloPipeline:
    """
    各ティックで差分可視化 1 枚を作り、それを YOLO に入力する（保存 PNG の一括処理はしない）。
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        m = config.get("model", {})
        weights = _resolve_path(m.get("weights", "models/yolov8n.pt"))
        device = m.get("device")
        self._conf = float(m.get("conf", 0.25))
        self.model = load_yolo(weights, device=device)

        dcfg = config.get("difference", {})
        self._use_alignment = bool(dcfg.get("use_alignment", False))
        self._absdiff_threshold = int(dcfg.get("absdiff_threshold", 25))
        self._morph_kernel = int(dcfg.get("morph_kernel", 5))

        ycfg = config.get("yolo", {})
        self._min_interval_ms = float(ycfg.get("min_interval_ms", 0))

        log_cfg = config.get("logging", {})
        self._log_enabled = bool(log_cfg.get("enable", True))
        log_path = log_cfg.get("path")
        self._log_path: Optional[Path] = _resolve_path(log_path) if log_path else None

        self._last_infer_time: float = 0.0
        self._last_detections: List[Detection] = []

        from detection_logger import DetectionLogger

        self._logger = DetectionLogger(
            self._log_path if self._log_enabled else None,
            enabled=self._log_enabled,
        )

        gui_cfg = config.get("gui", {})
        self.roi_gaussian_enabled = False
        self._roi_gaussian_kernel = int(gui_cfg.get("roi_gaussian_kernel", 15))

    def process(
        self,
        prev_bgr: np.ndarray,
        curr_bgr: np.ndarray,
        frame_index: int,
    ) -> Dict[str, Any]:
        pack = compute_difference_visual(
            prev_bgr,
            curr_bgr,
            use_alignment=self._use_alignment,
            absdiff_threshold=self._absdiff_threshold,
            morph_kernel=self._morph_kernel,
        )
        diff_bgr = pack["diff_bgr"]

        now = time.perf_counter()
        elapsed_ms = (now - self._last_infer_time) * 1000.0
        run_infer = self._min_interval_ms <= 0 or elapsed_ms >= self._min_interval_ms

        infer_ms: Optional[float] = None
        if run_infer:
            self._last_infer_time = now
            t_inf0 = time.perf_counter()
            dets = predict_frame(self.model, diff_bgr, conf=self._conf)
            infer_ms = (time.perf_counter() - t_inf0) * 1000.0
            dicts = detections_to_dicts(dets)
            dicts = refine_detections_3dgs(diff_bgr, dicts)
            dets2: List[Detection] = []
            for x in dicts:
                dets2.append(
                    Detection(
                        xyxy=x["xyxy"],
                        conf=float(x["conf"]),
                        cls_id=int(x.get("cls_id", 0)),
                        name=str(x.get("name", "")),
                    )
                )
            self._last_detections = dets2

            self._logger.append(
                frame_index=frame_index,
                detections=detections_to_dicts(self._last_detections),
                extra={"homography_ok": pack["meta"].get("homography_ok")},
            )
        base_for_overlay = diff_bgr
        if self.roi_gaussian_enabled and self._last_detections:
            base_for_overlay = apply_roi_gaussian_blur(
                diff_bgr,
                self._last_detections,
                kernel_size=self._roi_gaussian_kernel,
            )
        overlay = draw_detections_on_bgr(base_for_overlay, self._last_detections)

        return {
            "diff_bgr": diff_bgr,
            "diff_gray": pack["diff_gray"],
            "mask": pack["mask"],
            "overlay_bgr": overlay,
            "detections": list(self._last_detections),
            "meta": pack["meta"],
            "inference_ran": run_infer,
            "infer_ms": infer_ms,
        }
