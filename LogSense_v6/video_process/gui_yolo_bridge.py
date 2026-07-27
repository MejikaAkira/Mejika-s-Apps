#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py からの YOLO 差分ストリーム統合用（設定読み込みのみ。既存処理は変更しない）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_NAME = "yolo_stream_config.json"


def yolo_config_path() -> Path:
    return _PROJECT_ROOT / _CONFIG_NAME


def load_yolo_json() -> Dict[str, Any]:
    p = yolo_config_path()
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gui_yolo_enabled() -> bool:
    return bool(load_yolo_json().get("gui", {}).get("enable", False))


def build_streaming_yolo_pipeline():
    """gui が有効なときだけ呼ぶ。失敗時は例外。"""
    from streaming_yolo_pipeline import StreamingYoloPipeline, load_yolo_stream_config

    cfg = load_yolo_stream_config(str(yolo_config_path()))
    return StreamingYoloPipeline(cfg)
