#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data.yaml と images/labels の対応をざっくり検証する。
想定: images/train, images/val と labels/train, labels/val が data.yaml の path 基準で存在。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _check_split(root: Path, img_sub: str, label_sub: str, name: str) -> int:
    img_dir = root / img_sub
    lbl_dir = root / label_sub
    if not img_dir.is_dir():
        print(f"[NG] {name}: 画像ディレクトリなし {img_dir}")
        return 0
    if not lbl_dir.is_dir():
        print(f"[NG] {name}: ラベルディレクトリなし {lbl_dir}")
        return 0
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in exts]
    missing = 0
    for im in imgs:
        lf = lbl_dir / f"{im.stem}.txt"
        if not lf.is_file():
            print(f"[warn] {name}: ラベルなし {lf.name} (画像 {im.name})")
            missing += 1
    print(f"[{name}] 画像 {len(imgs)} 枚, ラベル欠け {missing}")
    return len(imgs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, required=True, help="data.yaml のパス")
    args = ap.parse_args()

    if yaml is None:
        print("PyYAML が必要です: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    data_yaml = Path(args.data).resolve()
    if not data_yaml.is_file():
        print(f"見つかりません: {data_yaml}", file=sys.stderr)
        sys.exit(1)

    root = data_yaml.parent
    with open(data_yaml, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    train_rel = (cfg.get("train") or "images/train").replace("\\", "/")
    val_rel = (cfg.get("val") or "images/val").replace("\\", "/")
    # labels は images/train -> labels/train のように対応させる
    def to_labels(img_rel: str) -> str:
        if img_rel.startswith("images/"):
            return "labels/" + img_rel.split("/", 1)[1]
        return "labels/" + img_rel

    n1 = _check_split(root, train_rel, to_labels(train_rel), "train")
    n2 = _check_split(root, val_rel, to_labels(val_rel), "val")
    if n1 + n2 == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
