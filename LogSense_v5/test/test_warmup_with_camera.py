#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
カメラを使ったウォーミングアップ機能のテストスクリプト
"""

import sys
import os
from pathlib import Path
import time
import signal

# video_processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "video_process"))

import logging
from realtime_video_processor import RealtimeVideoProcessor

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def test_warmup_with_camera():
    """
    カメラを使ったウォーミングアップ機能のテスト
    """
    print("=" * 60)
    print("カメラを使ったウォーミングアップ機能テスト")
    print("=" * 60)
    print()
    print("注意: このテストはカメラが必要です")
    print("Ctrl+Cで停止できます")
    print()
    
    # RealtimeVideoProcessorを初期化
    processor = RealtimeVideoProcessor()
    
    print("=" * 60)
    print("処理開始（ウォーミングアップを含む）")
    print("=" * 60)
    
    try:
        # 処理を開始（ウォーミングアップが自動実行される）
        processor.start()
        
        if not processor.is_running:
            print("[ERROR] 処理の開始に失敗しました")
            return False
        
        print("[OK] 処理が開始されました")
        print()
        print("2秒間処理を実行します...")
        print("（この間にウォーミングアップが実行され、その後フレーム処理が開始されます）")
        print("FPS30の場合、約60フレーム処理される予定です")
        print()
        
        # 2秒間処理を実行
        for i in range(2):
            time.sleep(1)
            if processor.is_running:
                print(f"  処理中... ({i+1}/2秒) - フレーム数: {processor.frame_count}")
            else:
                print("[WARNING] 処理が停止しました")
                break
        
        print()
        print("=" * 60)
        print("処理停止")
        print("=" * 60)
        
        processor.stop()
        
        print("[OK] 処理が停止しました")
        print()
        
        # 出力ディレクトリを確認
        if processor.output_dir and os.path.exists(processor.output_dir):
            files = os.listdir(processor.output_dir)
            print(f"保存されたファイル数: {len(files)}")
            if len(files) > 0:
                print("保存されたファイル（最初の10個）:")
                for f in sorted(files)[:10]:
                    print(f"  - {f}")
        else:
            print("警告: 出力ディレクトリが見つかりません")
        
        print()
        print("=" * 60)
        print("テスト完了")
        print("=" * 60)
        
        return True
        
    except KeyboardInterrupt:
        print()
        print("[INFO] ユーザーによって中断されました")
        processor.stop()
        return True
    except Exception as e:
        print(f"[ERROR] エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        processor.stop()
        return False


if __name__ == "__main__":
    success = test_warmup_with_camera()
    sys.exit(0 if success else 1)

