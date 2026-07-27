#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOLO 検出結果の JSONL 追記（座標は差分画像上）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class DetectionLogger:
    def __init__(self, log_path: Optional[Path], enabled: bool = True):
        self.enabled = enabled and log_path is not None
        self.log_path = Path(log_path) if log_path else None
        if self.enabled and self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        frame_index: int,
        detections: List[Dict[str, Any]],
        timestamp_iso: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled or not self.log_path:
            return
        ts = timestamp_iso or datetime.now(timezone.utc).isoformat()
        row = {
            "ts": ts,
            "frame_index": frame_index,
            "coordinate_space": "difference_bgr",
            "detections": detections,
        }
        if extra:
            row.update(extra)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
