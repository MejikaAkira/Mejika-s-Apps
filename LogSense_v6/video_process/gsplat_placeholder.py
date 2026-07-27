#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将来: 3D Gaussian Splatting 連携用プレースホルダ（未実装）。
"""

from __future__ import annotations

from typing import Any, Dict, List


def refine_detections_3dgs(
    diff_bgr: Any,
    detections: List[Dict[str, Any]],
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    差分フレームと検出結果を入力に、3DGS による補強結果を返す予定。
    現状は未実装のため、そのまま detections を返す。
    """
    return detections
