#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultralytics YOLO バッチ学習。app.py とは無関係。
出力: registry/candidates/<run_name>/weights/best.pt
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ML_OPS = Path(__file__).resolve().parent.parent
REPO_ROOT = ML_OPS.parent


def _load_yaml_config(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        return {}
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    ap = argparse.ArgumentParser(description="YOLO 学習（ml_ops）")
    ap.add_argument(
        "--data",
        type=str,
        required=True,
        help="data.yaml のパス（例: ml_ops/datasets/curated/myset/data.yaml）",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=None,
        help="ベース重み .pt（省略時は configs/train.default.yaml または models/yolov8n.pt）",
    )
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument(
        "--config",
        type=str,
        default=str(ML_OPS / "configs" / "train.default.yaml"),
        help="デフォルト値用 YAML",
    )
    ap.add_argument(
        "--project",
        type=str,
        default=str(ML_OPS / "registry" / "candidates"),
        help="学習出力の親ディレクトリ",
    )
    ap.add_argument(
        "--name",
        type=str,
        default=None,
        help="実行名（省略時は run_日時）",
    )
    args = ap.parse_args()

    cfg = _load_yaml_config(Path(args.config))
    model = args.model or cfg.get("model") or str(REPO_ROOT / "models" / "yolov8n.pt")
    epochs = args.epochs if args.epochs is not None else int(cfg.get("epochs", 50))
    imgsz = args.imgsz if args.imgsz is not None else int(cfg.get("imgsz", 640))
    batch = args.batch if args.batch is not None else int(cfg.get("batch", 16))

    data_yaml = Path(args.data).resolve()
    if not data_yaml.is_file():
        print(f"data.yaml が見つかりません: {data_yaml}", file=sys.stderr)
        sys.exit(1)

    model_path = Path(model)
    if not model_path.is_file():
        print(f"ベース重みが見つかりません: {model_path}", file=sys.stderr)
        sys.exit(1)

    project = Path(args.project).resolve()
    name = args.name or datetime.now().strftime("run_%Y%m%d_%H%M%S")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics をインストールしてください: pip install -r ml_ops/requirements-train.txt", file=sys.stderr)
        sys.exit(1)

    yolo = YOLO(str(model_path))
    yolo.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=str(project),
        name=name,
    )

    best = project / name / "weights" / "best.pt"
    print(f"完了。best.pt: {best}")
    if best.is_file():
        print(f"次の例: python ml_ops/scripts/promote_weights.py --src \"{best}\" --copy-to-models")


if __name__ == "__main__":
    main()
