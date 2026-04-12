#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
デモ用: ②の検出矩形（差分座標＝カメラと同解像度）を結合し 1.5 倍に拡大して curr から切り出し YOLO。
app.py では使用しない。
"""

from __future__ import annotations

import os
import time
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from yolo_infer import Detection, predict_frame


def _try_jp_font(size: int = 15) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if os.name == "nt":
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "meiryo.ttc"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msgothic.ttc"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "YuGothM.ttc"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"),
        ]
    else:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        ]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_lines(text: str, max_chars: int = 14) -> List[str]:
    lines: List[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > max_chars:
            lines.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        lines.append(paragraph)
    return lines if lines else [""]


def union_xyxy(detections: List[Detection]) -> Optional[Tuple[float, float, float, float]]:
    if not detections:
        return None
    x1 = min(d.xyxy[0] for d in detections)
    y1 = min(d.xyxy[1] for d in detections)
    x2 = max(d.xyxy[2] for d in detections)
    y2 = max(d.xyxy[3] for d in detections)
    return (x1, y1, x2, y2)


def expand_xyxy(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    scale: float,
    img_w: int,
    img_h: int,
) -> Tuple[int, int, int, int]:
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    bw = (x2 - x1) * scale
    bh = (y2 - y1) * scale
    nx1 = int(round(cx - bw / 2.0))
    ny1 = int(round(cy - bh / 2.0))
    nx2 = int(round(cx + bw / 2.0))
    ny2 = int(round(cy + bh / 2.0))
    nx1 = max(0, min(img_w - 1, nx1))
    ny1 = max(0, min(img_h - 1, ny1))
    nx2 = max(0, min(img_w, nx2))
    ny2 = max(0, min(img_h, ny2))
    if nx2 <= nx1:
        nx2 = min(img_w, nx1 + 1)
    if ny2 <= ny1:
        ny2 = min(img_h, ny1 + 1)
    return nx1, ny1, nx2, ny2


def draw_detections_on_bgr_local(bgr: np.ndarray, detections: List[Detection]) -> np.ndarray:
    out = bgr.copy()
    for d in detections:
        x1, y1, x2, y2 = [int(round(x)) for x in d.xyxy]
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 200, 0), 2)
        label = f"{d.name} {d.conf:.2f}"
        cv2.putText(
            out,
            label,
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 200, 0),
            1,
            cv2.LINE_AA,
        )
    return out


def infer_camera_roi_from_diff_detections(
    model: Any,
    curr_bgr: np.ndarray,
    diff_detections: List[Detection],
    *,
    conf: float,
    expand_scale: float = 1.5,
) -> Tuple[np.ndarray, float]:
    """
    ②の検出に基づき curr から ROI を切り出して YOLO。戻り値: (オーバーレイBGR, infer_ms)
    """
    h, w = curr_bgr.shape[:2]
    u = union_xyxy(diff_detections)
    if u is None:
        return make_roi_idle_image("②で検出なし"), 0.0
    x1, y1, x2, y2 = u
    nx1, ny1, nx2, ny2 = expand_xyxy(x1, y1, x2, y2, expand_scale, w, h)
    crop = curr_bgr[ny1:ny2, nx1:nx2].copy()
    if crop.size == 0:
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(blank, "empty crop", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1, cv2.LINE_AA)
        return blank, 0.0
    t0 = time.perf_counter()
    dets = predict_frame(model, crop, conf=conf)
    infer_ms = (time.perf_counter() - t0) * 1000.0
    overlay = draw_detections_on_bgr_local(crop, dets)
    return overlay, infer_ms


def make_roi_idle_image(message: str = "② 未検出（同周期待機）") -> np.ndarray:
    """日本語表示用。OpenCV putText は非対応のため PIL で描画する。"""
    w, h = 320, 240
    img = Image.new("RGB", (w, h), (24, 24, 28))
    draw = ImageDraw.Draw(img)
    font = _try_jp_font(15)
    lines = _wrap_lines(message, max_chars=16)
    y = 36
    for line in lines:
        draw.text((12, y), line, fill=(190, 190, 195), font=font)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + 6
        if y > h - 20:
            break
    arr = np.array(img, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
