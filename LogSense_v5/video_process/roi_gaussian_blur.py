#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOLO 検出矩形内のみ 2D ガウシアンぼかし（空間フィルタ）。
"""

from __future__ import annotations

from typing import List

import cv2

from yolo_infer import Detection


def apply_roi_gaussian_blur(
    bgr: np.ndarray,
    detections: List[Detection],
    kernel_size: int = 15,
    sigma_x: float = 0.0,
) -> np.ndarray:
    """
    各検出ボックス内の画素にのみ GaussianBlur を適用した BGR を返す。
    kernel_size は奇数に丸める。
    """
    if not detections or bgr is None or bgr.size == 0:
        return bgr.copy() if bgr is not None else bgr

    h, w = bgr.shape[:2]
    k = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
    k = max(3, min(k, min(h, w) | 1))

    out = bgr.copy()
    for d in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in d.xyxy]
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2]
        out[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), sigmaX=sigma_x)
    return out
