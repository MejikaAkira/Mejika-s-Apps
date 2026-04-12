#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分フレーム（BGR 1枚）に対する YOLO 推論。既存コードは変更しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

try:
    from ultralytics import YOLO  # type: ignore
except ImportError as e:
    YOLO = None  # type: ignore
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


@dataclass
class Detection:
    xyxy: Sequence[float]
    conf: float
    cls_id: int
    name: str


def load_yolo(weights_path: Union[str, Path], device: Optional[str] = None):
    if YOLO is None:
        raise ImportError(
            "ultralytics がインストールされていません。pip install -r requirements-yolo.txt を実行してください。"
        ) from _IMPORT_ERROR
    path = Path(weights_path)
    if not path.is_file():
        raise FileNotFoundError(f"YOLO ウェイトが見つかりません: {path.resolve()}")
    model = YOLO(str(path))
    if device:
        model.to(device)
    return model


def predict_frame(
    model: Any,
    bgr: np.ndarray,
    *,
    conf: float = 0.25,
) -> List[Detection]:
    """
    差分可視化 BGR 1枚に対して 1 回 predict し、検出リストを返す。
    """
    if bgr is None or bgr.size == 0:
        return []
    results = model.predict(bgr, conf=conf, verbose=False)
    if not results:
        return []
    r0 = results[0]
    names = getattr(r0, "names", None) or {}
    out: List[Detection] = []
    boxes = getattr(r0, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return out
    for b in boxes:
        xyxy = b.xyxy.cpu().numpy().flatten().tolist()
        cid = int(b.cls.cpu().numpy().flatten()[0])
        cf = float(b.conf.cpu().numpy().flatten()[0])
        label = names.get(cid, str(cid)) if isinstance(names, dict) else str(cid)
        out.append(Detection(xyxy=xyxy, conf=cf, cls_id=cid, name=label))
    return out


def detections_to_dicts(dets: List[Detection]) -> List[Dict[str, Any]]:
    return [
        {
            "xyxy": [float(x) for x in d.xyxy],
            "conf": d.conf,
            "cls_id": d.cls_id,
            "name": d.name,
        }
        for d in dets
    ]
