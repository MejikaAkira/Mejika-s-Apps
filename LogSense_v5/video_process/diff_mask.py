#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分フレーム（1枚）の生成。YOLO 入力は「差分を可視化した BGR 1枚」＝動画の1フレーム。
既存 process/ の align はオプションで import のみ使用（既存ファイルは変更しない）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _ensure_process_path() -> None:
    p = str(_PROJECT_ROOT / "process")
    if p not in sys.path:
        sys.path.insert(0, p)


def compute_difference_visual(
    prev_bgr: np.ndarray,
    curr_bgr: np.ndarray,
    *,
    use_alignment: bool = False,
    absdiff_threshold: int = 25,
    morph_kernel: int = 5,
) -> Dict[str, Any]:
    """
    連続2フレームから差分可視化 BGR（YOLO 用の「動画の1コマ」）を生成する。

    Returns:
        diff_bgr: 差分の疑似カラー BGR（Ultralytics 入力用）
        diff_gray: absdiff グレースケール
        mask: 二値マスク（変化領域）
        meta: 整列成否など
    """
    meta: Dict[str, Any] = {"aligned": False, "homography_ok": None}

    if prev_bgr.shape != curr_bgr.shape:
        curr_bgr = cv2.resize(curr_bgr, (prev_bgr.shape[1], prev_bgr.shape[0]))

    if use_alignment:
        _ensure_process_path()
        from alignment_utils import align_images, resize_to_common_size  # type: ignore

        img1, img2, _, _, mask1, mask2 = resize_to_common_size(prev_bgr, curr_bgr)
        align_out = align_images(img1, img2, mask1, mask2)
        if len(align_out) == 3:
            aligned_prev, aligned_curr, H = align_out
        else:
            aligned_prev, aligned_curr, H, _, _ = align_out
        meta["homography_ok"] = H is not None
        if H is not None:
            meta["aligned"] = True
        prev_use, curr_use = aligned_prev, aligned_curr
    else:
        prev_use, curr_use = prev_bgr, curr_bgr

    g1 = cv2.cvtColor(prev_use, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(curr_use, cv2.COLOR_BGR2GRAY)
    diff_gray = cv2.absdiff(g1, g2)

    _, mask = cv2.threshold(
        diff_gray, absdiff_threshold, 255, cv2.THRESH_BINARY
    )
    k = max(1, int(morph_kernel))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    diff_vis = cv2.applyColorMap(diff_gray, cv2.COLORMAP_JET)

    return {
        "diff_bgr": diff_vis,
        "diff_gray": diff_gray,
        "mask": mask,
        "meta": meta,
    }
