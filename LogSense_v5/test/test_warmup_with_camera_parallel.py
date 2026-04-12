#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
カメラを使ったウォーミングアップ機能のテストスクリプト（保存処理を並列化）
"""

import sys
import os
from pathlib import Path
import time
import threading
from typing import Optional
import cv2

# video_processディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "video_process"))

import logging
from realtime_video_processor import RealtimeVideoProcessor

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


class ParallelSaveThread:
    """画像保存を並列実行するスレッド"""
    def __init__(self, processor: RealtimeVideoProcessor):
        self.processor = processor
        self.is_running = False
        self.save_thread: Optional[threading.Thread] = None
        self.saved_count = 0
        self.save_times = []  # 保存時間を記録
    
    def start(self):
        """保存スレッドを開始"""
        if self.is_running:
            return
        
        self.is_running = True
        self.save_thread = threading.Thread(target=self._save_loop, daemon=True)
        self.save_thread.start()
        logging.info("保存スレッドを開始しました")
    
    def stop(self):
        """保存スレッドを停止"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.save_thread:
            self.save_thread.join(timeout=2.0)
        logging.info(f"保存スレッドを停止しました（保存数: {self.saved_count}）")
    
    def _save_loop(self):
        """保存ループ"""
        while self.is_running or not self.processor.frame_buffer.queue.empty():
            try:
                result = self.processor.frame_buffer.get(timeout=0.1)
                if result is None:
                    continue
                
                # 保存処理（時間測定）
                save_start = time.time()
                self._save_frame(result)
                save_time = (time.time() - save_start) * 1000  # ms
                self.save_times.append(save_time)
                self.saved_count += 1
                
            except Exception as e:
                if self.is_running:
                    logging.error(f"保存処理中にエラー: {e}")
                continue
    
    def _save_frame(self, result):
        """フレームを保存（RealtimeVideoProcessorの_save_frameと同じロジック）"""
        frame_number = result["frame_number"]
        frame_filename = f"frame_{frame_number:06d}.png"
        diff_filename = f"frame_{frame_number:06d}_diff.png"
        
        if result["has_difference"]:
            frame_path = os.path.join(self.processor.output_dir, frame_filename)
            diff_path = os.path.join(self.processor.output_dir, diff_filename)
            cv2.imwrite(frame_path, result["original_frame"])
            cv2.imwrite(diff_path, result["difference"])
        elif self.processor.archive_no_diff:
            frame_path = os.path.join(self.processor.archive_dir, frame_filename)
            cv2.imwrite(frame_path, result["original_frame"])


def test_warmup_with_camera_parallel():
    """
    カメラを使ったウォーミングアップ機能のテスト（保存処理を並列化）
    """
    print("=" * 60)
    print("カメラを使ったウォーミングアップ機能テスト（並列保存）")
    print("=" * 60)
    print()
    print("注意: このテストはカメラが必要です")
    print("Ctrl+Cで停止できます")
    print()
    
    # RealtimeVideoProcessorを初期化
    processor = RealtimeVideoProcessor()
    
    # 並列保存スレッドを初期化
    save_thread = ParallelSaveThread(processor)
    
    print("=" * 60)
    print("処理開始（ウォーミングアップを含む）")
    print("=" * 60)
    
    try:
        # 処理を開始（ウォーミングアップが自動実行される）
        processor.start()
        
        if not processor.is_running:
            print("[ERROR] 処理の開始に失敗しました")
            return False
        
        # 保存スレッドを開始
        save_thread.start()
        
        print("[OK] 処理が開始されました（保存処理は並列実行）")
        print()
        print("2秒間処理を実行します...")
        print("（この間にウォーミングアップが実行され、その後フレーム処理が開始されます）")
        print("FPS30の場合、約60フレーム処理される予定です")
        print()
        
        # 2秒間処理を実行
        for i in range(2):
            time.sleep(1)
            if processor.is_running:
                print(f"  処理中... ({i+1}/2秒) - フレーム数: {processor.frame_count}, 保存数: {save_thread.saved_count}")
            else:
                print("[WARNING] 処理が停止しました")
                break
        
        print()
        print("=" * 60)
        print("処理停止")
        print("=" * 60)
        
        # 処理を停止
        processor.stop()
        
        # 残りのフレームを保存するために少し待機
        print("残りのフレームを保存中...")
        time.sleep(1.0)
        
        # 保存スレッドを停止
        save_thread.stop()
        
        print("[OK] 処理が停止しました")
        print()
        
        # 処理時間の統計を表示
        if processor.process_times:
            process_times = processor.process_times
            avg_process_time = sum(process_times) / len(process_times)
            max_process_time = max(process_times)
            min_process_time = min(process_times)
            target_time = (1.0 / processor.camera_fps) * 1000  # ms
            
            print()
            print("=" * 60)
            print("処理時間の統計")
            print("=" * 60)
            print(f"処理フレーム数: {len(process_times)}")
            print(f"平均処理時間: {avg_process_time:.2f}ms/フレーム")
            print(f"最大処理時間: {max_process_time:.2f}ms/フレーム")
            print(f"最小処理時間: {min_process_time:.2f}ms/フレーム")
            print(f"目標処理時間: {target_time:.2f}ms/フレーム (30FPS)")
            print(f"余裕: {target_time - avg_process_time:.2f}ms/フレーム")
        
        if save_thread.save_times:
            save_times = save_thread.save_times
            avg_save_time = sum(save_times) / len(save_times)
            max_save_time = max(save_times)
            min_save_time = min(save_times)
            
            print()
            print("=" * 60)
            print("保存時間の統計")
            print("=" * 60)
            print(f"保存フレーム数: {len(save_times)}")
            print(f"平均保存時間: {avg_save_time:.2f}ms/フレーム")
            print(f"最大保存時間: {max_save_time:.2f}ms/フレーム")
            print(f"最小保存時間: {min_save_time:.2f}ms/フレーム")
        
        # 出力ディレクトリを確認
        if processor.output_dir and os.path.exists(processor.output_dir):
            files = os.listdir(processor.output_dir)
            print()
            print("=" * 60)
            print("保存ファイル情報")
            print("=" * 60)
            print(f"保存されたファイル数: {len(files)}")
            print(f"処理フレーム数: {processor.frame_count}")
            print(f"保存スレッドで保存した数: {save_thread.saved_count}")
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
        save_thread.stop()
        return True
    except Exception as e:
        print(f"[ERROR] エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        processor.stop()
        save_thread.stop()
        return False


if __name__ == "__main__":
    success = test_warmup_with_camera_parallel()
    sys.exit(0 if success else 1)

