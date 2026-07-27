#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
差分ストリーム → YOLO のデモ（カメラまたは動画ファイル）。
プロジェクトルートで:
  python video_process/run_stream_yolo_demo.py
  python video_process/run_stream_yolo_demo.py --source path/to/video.mp4
  python video_process/run_stream_yolo_demo.py --config yolo_stream_config.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

_VP = Path(__file__).resolve().parent
_ROOT = _VP.parent
if str(_VP) not in sys.path:
    sys.path.insert(0, str(_VP))

from streaming_yolo_pipeline import StreamingYoloPipeline, load_yolo_stream_config


def main() -> None:
    ap = argparse.ArgumentParser(description="差分ストリーム + YOLO デモ")
    ap.add_argument(
        "--source",
        default="0",
        help="カメラ番号 (0,1,...) または動画ファイルパス",
    )
    ap.add_argument(
        "--config",
        default=str(_ROOT / "yolo_stream_config.json"),
        help="yolo_stream_config.json のパス",
    )
    args = ap.parse_args()

    cfg = load_yolo_stream_config(args.config)
    pipeline = StreamingYoloPipeline(cfg)

    src = args.source
    if src.isdigit():
        cap = cv2.VideoCapture(int(src))
    else:
        cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"入力を開けませんでした: {src}")
        sys.exit(1)

    win = "LogSense diff stream + YOLO (q で終了)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    prev = None
    idx = 0
    t0 = time.perf_counter()
    fps_ema = 0.0

    while True:
        ok, curr = cap.read()
        if not ok:
            break
        if prev is None:
            prev = curr.copy()
            idx += 1
            continue

        out = pipeline.process(prev, curr, frame_index=idx)
        overlay = out["overlay_bgr"]

        idx += 1
        prev = curr.copy()

        dt = time.perf_counter() - t0
        t0 = time.perf_counter()
        inst_fps = 1.0 / dt if dt > 1e-6 else 0.0
        fps_ema = inst_fps if fps_ema <= 0 else fps_ema * 0.9 + inst_fps * 0.1

        inf = "Y" if out["inference_ran"] else "N"
        cv2.putText(
            overlay,
            f"FPS ~{fps_ema:.1f} infer={inf} frame={idx}",
            (8, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow(win, overlay)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
