#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出力ディレクトリとアーカイブディレクトリの内容を確認
"""

import os
from pathlib import Path

# 最新の出力ディレクトリを取得
output_base = Path("video_outputs")
if output_base.exists():
    output_dirs = [d for d in output_base.iterdir() if d.is_dir() and d.name != "archive"]
    if output_dirs:
        latest = max(output_dirs, key=lambda x: x.stat().st_mtime)
        print(f"最新の出力ディレクトリ: {latest}")
        files = list(latest.glob("*"))
        print(f"  ファイル数: {len(files)}")
        
        # 差分あり/なしの内訳
        diff_files = [f for f in files if "_diff.png" in f.name]
        frame_files = [f for f in files if "_diff.png" not in f.name]
        print(f"  フレーム画像: {len(frame_files)}")
        print(f"  差分画像: {len(diff_files)}")
        print(f"  差分検出フレーム数: {len(diff_files)}")
    else:
        print("出力ディレクトリが見つかりません")
else:
    print("video_outputsディレクトリが存在しません")

# アーカイブディレクトリを確認
archive_dir = Path("video_outputs/archive")
if archive_dir.exists():
    archive_files = list(archive_dir.glob("*.png"))
    print(f"\nアーカイブディレクトリ: {archive_dir}")
    print(f"  ファイル数: {len(archive_files)}")
    print(f"  （差分なしフレーム数: {len(archive_files)}）")
else:
    print("\nアーカイブディレクトリが存在しません")

