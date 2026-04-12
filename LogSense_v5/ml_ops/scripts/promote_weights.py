#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学習済み best.pt を本番用にコピーし registry/manifest.json を更新する。app.py とは無関係。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ML_OPS = Path(__file__).resolve().parent.parent
REPO_ROOT = ML_OPS.parent


def main() -> None:
    ap = argparse.ArgumentParser(description="本番重みへ昇格")
    ap.add_argument("--src", type=str, required=True, help="昇格する best.pt のパス")
    ap.add_argument(
        "--copy-to-models",
        action="store_true",
        help="リポジトリ直下 models/yolov8_custom.pt にもコピー（推論で使いやすい固定名）",
    )
    ap.add_argument(
        "--dataset-id",
        type=str,
        default="",
        help="任意。どのデータセットで学習したかメモ",
    )
    args = ap.parse_args()

    src = Path(args.src).resolve()
    if not src.is_file():
        print(f"ファイルがありません: {src}", file=sys.stderr)
        sys.exit(1)

    production_dir = ML_OPS / "registry" / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    dst = production_dir / "best.pt"
    shutil.copy2(src, dst)

    manifest_path = ML_OPS / "registry" / "manifest.json"
    payload = {
        "production_weights": str(dst.relative_to(ML_OPS)).as_posix(),
        "absolute_path": str(dst),
        "source_train_run": str(src),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": args.dataset_id,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"registry/production/best.pt にコピーしました。\nmanifest: {manifest_path}")

    if args.copy_to_models:
        models_dir = REPO_ROOT / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        custom = models_dir / "yolov8_custom.pt"
        shutil.copy2(src, custom)
        print(f"models/yolov8_custom.pt にもコピーしました。")
        print('yolo_stream_config.json の "model.weights" を "models/yolov8_custom.pt" に合わせてください。')


if __name__ == "__main__":
    main()
