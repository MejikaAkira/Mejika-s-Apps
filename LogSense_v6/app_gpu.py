#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LogSense v5 GUIアプリケーション
リアルタイム動画差分検出のGUIインターフェース
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QImage, QPixmap

# パスを追加
sys.path.insert(0, str(Path(__file__).parent / "video_process"))
sys.path.insert(0, str(Path(__file__).parent / "process"))

from video_process.realtime_video_processor import RealtimeVideoProcessor
from video_process.gui_yolo_bridge import gui_yolo_enabled
from video_process.yolo_infer import predict_frame
from video_process.streaming_yolo_pipeline import draw_detections_on_bgr
from process.config_loader import get_config
import queue


def build_streaming_yolo_pipeline_gpu():
    """Build a pipeline that runs YOLO on the GPU (cuda); app_gpu only.

    Difference processing stays on CPU (it is light, so CPU is faster).
    Falls back to CPU automatically when CUDA is unavailable.
    """
    import torch
    from streaming_yolo_pipeline import StreamingYoloPipeline, load_yolo_stream_config
    from video_process.gui_yolo_bridge import yolo_config_path

    cfg = load_yolo_stream_config(str(yolo_config_path()))
    cfg.setdefault("model", {})["device"] = "cuda" if torch.cuda.is_available() else None
    return StreamingYoloPipeline(cfg)


class VideoDisplayWidget(QWidget):
    """画像表示ウィジェット（元フレーム用）"""
    
    def __init__(self, label: str = "元フレーム", parent=None):
        super().__init__(parent)
        self.label = label
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # ラベル
        self.title_label = QLabel(self.label)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        # 画像表示エリア
        self.image_label = QLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setText("画像を待機中...")
        self.image_label.setScaledContents(False)  # アスペクト比を保持
        layout.addWidget(self.image_label)
        
        # タイムスタンプ表示（画像の下）
        self.timestamp_label = QLabel("--:--:--.---")
        self.timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timestamp_label.setStyleSheet("font-size: 12px; color: gray;")
        layout.addWidget(self.timestamp_label)
        
        # 現在のフレームを保持（リサイズ時に再描画用）
        self.current_frame = None
        self.current_timestamp = None
        
        self.setLayout(layout)
    
    def update_frame(self, frame: np.ndarray, timestamp: Optional[datetime] = None):
        """フレームを更新"""
        if frame is None:
            return
        
        # フレームとタイムスタンプを保持
        self.current_frame = frame
        self.current_timestamp = timestamp
        
        self._display_frame()
    
    def _display_frame(self):
        """フレームを表示（リサイズ時にも呼び出される）"""
        if self.current_frame is None:
            return
        
        # BGR→RGB変換
        rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        
        # QImageに変換
        q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # QPixmapに変換して表示
        pixmap = QPixmap.fromImage(q_image)
        # ラベルのサイズに合わせてスケール
        label_size = self.image_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        
        # タイムスタンプ更新
        if self.current_timestamp:
            timestamp_str = self.current_timestamp.strftime("%H:%M:%S.%f")[:-3]  # ミリ秒まで
            self.timestamp_label.setText(timestamp_str)
    
    def resizeEvent(self, event):
        """ウィジェットのリサイズ時に呼び出される"""
        super().resizeEvent(event)
        self._display_frame()


class DifferenceDisplayWidget(QWidget):
    """差分画像表示ウィジェット"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_realtime_mode = True
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # ラベル
        self.title_label = QLabel("差分画像")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        # 画像表示エリア
        self.image_label = QLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setText("画像を待機中...")
        self.image_label.setScaledContents(False)  # アスペクト比を保持
        layout.addWidget(self.image_label)
        
        # タイムスタンプ表示（画像の下）
        self.timestamp_label = QLabel("--:--:--.---")
        self.timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timestamp_label.setStyleSheet("font-size: 12px; color: gray;")
        layout.addWidget(self.timestamp_label)
        
        # エラーメッセージ表示（タイムスタンプの下）
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("font-size: 11px; color: red;")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
        
        # 再生スライダー（初期は非表示）
        self.playback_slider = QSlider(Qt.Orientation.Horizontal)
        self.playback_slider.setMinimum(0)
        self.playback_slider.setMaximum(0)
        self.playback_slider.setValue(0)
        self.playback_slider.setVisible(False)
        layout.addWidget(self.playback_slider)
        
        # 現在のフレームを保持（リサイズ時に再描画用）
        self.current_frame = None
        self.current_timestamp = None
        
        self.setLayout(layout)
    
    def update_frame(self, frame: Optional[np.ndarray] = None, 
                     timestamp: Optional[datetime] = None,
                     status: Optional[str] = None,
                     error_message: Optional[str] = None):
        """フレームを更新
        
        Args:
            frame: 表示するフレーム（Noneの場合は表示しない）
            timestamp: タイムスタンプ
            status: 処理状態（"success", "error", "no_difference"など）
            error_message: エラーメッセージ
        """
        # エラーメッセージの表示/非表示
        if error_message:
            self.error_label.setText(error_message)
            self.error_label.setVisible(True)
        elif status == "no_difference":
            self.error_label.setText("差分が検出されませんでした")
            self.error_label.setVisible(True)
        elif status == "processing":
            self.error_label.setText("処理中...")
            self.error_label.setVisible(True)
        elif status == "success" or (frame is not None):
            self.error_label.setVisible(False)
        else:
            self.error_label.setVisible(False)
        
        if frame is None:
            return
        
        # フレームとタイムスタンプを保持
        self.current_frame = frame
        self.current_timestamp = timestamp
        
        self._display_frame()
    
    def _display_frame(self):
        """フレームを表示（リサイズ時にも呼び出される）"""
        if self.current_frame is None:
            return
        
        # 差分画像はグレースケールの場合があるので、3チャンネルに変換
        frame = self.current_frame.copy()
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:
            # BGR→RGB変換
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        
        # QImageに変換
        q_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # QPixmapに変換して表示
        pixmap = QPixmap.fromImage(q_image)
        # ラベルのサイズに合わせてスケール
        label_size = self.image_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        
        # タイムスタンプ更新
        if self.current_timestamp:
            timestamp_str = self.current_timestamp.strftime("%H:%M:%S.%f")[:-3]  # ミリ秒まで
            self.timestamp_label.setText(timestamp_str)
    
    def resizeEvent(self, event):
        """ウィジェットのリサイズ時に呼び出される"""
        super().resizeEvent(event)
        self._display_frame()
    
    def set_realtime_mode(self, enabled: bool):
        """リアルタイムモードの切替"""
        self.is_realtime_mode = enabled
        self.playback_slider.setVisible(not enabled)


class LiveCameraWindow(QMainWindow):
    """リアルタイムカメラ映像表示ウィンドウ"""
    
    def __init__(self, processor: RealtimeVideoProcessor, parent=None):
        super().__init__(parent)
        self.processor: Optional[RealtimeVideoProcessor] = processor
        self.is_running = False
        self.current_frame: Optional[np.ndarray] = None
        self.subscriber_queue: Optional[queue.Queue] = None  # ブロードキャストから購読したキュー
        
        self.init_ui()
        self.init_timer()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("LogSense v5 - リアルタイムカメラ映像")
        self.setMinimumSize(640, 480)
        
        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # 画像表示エリア
        self.image_label = QLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setText("カメラを待機中...")
        self.image_label.setScaledContents(False)
        layout.addWidget(self.image_label)
        
        # タイムスタンプ表示
        self.timestamp_label = QLabel("--:--:--.---")
        self.timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timestamp_label.setStyleSheet("font-size: 12px; color: gray;")
        layout.addWidget(self.timestamp_label)
    
    def init_timer(self):
        """タイマーの初期化"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_frame)
        self.update_timer.setInterval(33)  # 約30FPS
    
    def start_camera(self):
        """カメラを開始（processorのframe_broadcasterから購読）"""
        if self.is_running:
            return True
        
        if self.processor is None:
            self.image_label.setText("プロセッサが設定されていません")
            return False
        
        if not self.processor.is_running:
            self.image_label.setText("メイン処理が動作していません。先に「開始」ボタンを押してください。")
            return False
        
        # フレームブロードキャストから購読
        self.subscriber_queue = self.processor.frame_broadcaster.subscribe(maxsize=2)
        
        self.is_running = True
        self.update_timer.start()
        return True
    
    def stop_camera(self):
        """カメラを停止"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.update_timer.stop()
        
        # ブロードキャストから購読解除
        if self.subscriber_queue is not None and self.processor is not None:
            self.processor.frame_broadcaster.unsubscribe(self.subscriber_queue)
            self.subscriber_queue = None
        
        self.image_label.setText("リアルタイム映像を停止しました")
    
    def update_frame(self):
        """フレームを更新（processorのframe_broadcasterから取得）"""
        if not self.is_running or self.processor is None:
            return
        
        if not self.processor.is_running:
            self.image_label.setText("メイン処理が停止しました")
            self.is_running = False
            self.update_timer.stop()
            return
        
        if self.subscriber_queue is None:
            return
        
        try:
            # 購読キューから最新のフレームを取得
            latest_frame = None
            while True:
                try:
                    latest_frame = self.subscriber_queue.get_nowait()
                except queue.Empty:
                    break
            
            if latest_frame is not None:
                self.current_frame = latest_frame
                self._display_frame()
        except Exception as e:
            # エラーは無視（次のフレームで再試行）
            pass
    
    def _display_frame(self):
        """フレームを表示"""
        if self.current_frame is None:
            return
        
        # BGR→RGB変換
        rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        
        # QImageに変換
        q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # QPixmapに変換して表示
        pixmap = QPixmap.fromImage(q_image)
        label_size = self.image_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        
        # タイムスタンプ更新
        current_time = datetime.now()
        timestamp_str = current_time.strftime("%H:%M:%S.%f")[:-3]
        self.timestamp_label.setText(timestamp_str)
    
    def resizeEvent(self, event):
        """ウィジェットのリサイズ時に呼び出される"""
        super().resizeEvent(event)
        self._display_frame()
    
    def closeEvent(self, event):
        """ウィンドウを閉じる時の処理"""
        self.stop_camera()
        event.accept()


class StatsWidget(QWidget):
    """統計情報表示ウィジェット"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout()
        
        # FPS
        self.fps_label = QLabel("FPS: --")
        layout.addWidget(self.fps_label)
        
        # 差分ピクセル数
        self.diff_pixels_label = QLabel("差分ピクセル: --")
        layout.addWidget(self.diff_pixels_label)
        
        # 差分率
        self.diff_ratio_label = QLabel("差分率: --%")
        layout.addWidget(self.diff_ratio_label)
        
        # 処理時間
        self.process_time_label = QLabel("処理時間: --ms")
        layout.addWidget(self.process_time_label)
        
        # フレーム番号
        self.frame_number_label = QLabel("フレーム: --")
        layout.addWidget(self.frame_number_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_stats(self, fps: Optional[float] = None,
                     diff_pixels: Optional[int] = None,
                     diff_ratio: Optional[float] = None,
                     process_time: Optional[float] = None,
                     frame_number: Optional[int] = None):
        """統計情報を更新"""
        if fps is not None:
            self.fps_label.setText(f"FPS: {fps:.1f}")
        if diff_pixels is not None:
            self.diff_pixels_label.setText(f"差分ピクセル: {diff_pixels}")
        if diff_ratio is not None:
            self.diff_ratio_label.setText(f"差分率: {diff_ratio*100:.2f}%")
        if process_time is not None:
            self.process_time_label.setText(f"処理時間: {process_time:.1f}ms")
        if frame_number is not None:
            self.frame_number_label.setText(f"フレーム: {frame_number}")


class MainWindow(QMainWindow):
    """メインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        self.processor: Optional[RealtimeVideoProcessor] = None
        self.config = get_config("config.json")
        self.last_frame_time = None
        self.frame_count = 0
        self.fps = 0.0
        self.live_camera_window: Optional[LiveCameraWindow] = None
        self.subscriber_queue: Optional[queue.Queue] = None  # ブロードキャストから購読したキュー
        self._yolo_gui_requested = gui_yolo_enabled()
        self._yolo_pipeline = None  # type: ignore
        self._prev_bgr_yolo: Optional[np.ndarray] = None
        self._yolo_frame_index = 0
        
        # 設定確認
        rt_config = self.config.get("realtime_video", {})
        display_config = rt_config.get("display", {})
        self.display_enable = display_config.get("enable", True)
        self.display_show = display_config.get("show", "both")
        
        if not self.display_enable:
            print("GUI表示が無効になっています。config.jsonのrealtime_video.display.enableをtrueに設定してください。")
            sys.exit(1)
        
        self.init_ui()
        self.init_processor()
        self.init_timer()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("LogSense v5 - リアルタイム動画差分検出 (GPU)")
        self.setMinimumSize(1280, 720)
        
        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # コントロールパネル
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # 画像表示エリア
        image_area = self.create_image_area()
        main_layout.addWidget(image_area)
        
        # 統計情報
        self.stats_widget = StatsWidget()
        main_layout.addWidget(self.stats_widget)
        
        # ステータスバー
        self.statusBar().showMessage("準備完了")
    
    def create_control_panel(self) -> QWidget:
        """コントロールパネルを作成"""
        panel = QWidget()
        layout = QHBoxLayout()
        
        # 開始ボタン
        self.start_button = QPushButton("開始")
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button)
        
        # 停止ボタン
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
        
        # リアルタイム映像ボタン
        self.live_camera_button = QPushButton("リアルタイム映像")
        self.live_camera_button.clicked.connect(self.on_live_camera_clicked)
        layout.addWidget(self.live_camera_button)
        
        self.roi_gaussian_check = QCheckBox("ROIガウシアン")
        self.roi_gaussian_check.setToolTip("YOLO検出矩形内のみ2Dガウシアンぼかし（差分+YOLO表示時）")
        self.roi_gaussian_check.setEnabled(False)
        self.roi_gaussian_check.toggled.connect(self._on_roi_gaussian_toggled)
        layout.addWidget(self.roi_gaussian_check)
        
        layout.addStretch()
        panel.setLayout(layout)
        return panel
    
    def create_image_area(self) -> QWidget:
        """画像表示エリアを作成"""
        area = QWidget()
        layout = QHBoxLayout()
        
        # 表示設定に基づいてウィジェットを作成
        if self.display_show in ["both", "original"]:
            self.original_widget = VideoDisplayWidget("元フレーム")
            layout.addWidget(self.original_widget)
        
        if self.display_show in ["both", "difference"]:
            self.difference_widget = DifferenceDisplayWidget()
            layout.addWidget(self.difference_widget)
        
        area.setLayout(layout)
        return area
    
    def init_processor(self):
        """プロセッサの初期化"""
        self.processor = RealtimeVideoProcessor()
    
    def init_timer(self):
        """タイマーの初期化（フレーム更新用）"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_frames)
        self.update_timer.setInterval(33)  # 約30FPS
    
    def on_start_clicked(self):
        """開始ボタンのクリック処理"""
        if self.processor is None:
            return
        
        try:
            self.processor.start()
            if self.subscriber_queue is None:
                self.subscriber_queue = self.processor.frame_broadcaster.subscribe(maxsize=2)
            if self._yolo_gui_requested and self._yolo_pipeline is None:
                try:
                    self._yolo_pipeline = build_streaming_yolo_pipeline_gpu()
                except Exception as e:
                    self._yolo_pipeline = None
                    print(f"YOLO初期化エラー（従来の差分表示にフォールバック）: {e}")
            if self._yolo_pipeline is not None:
                self.roi_gaussian_check.setEnabled(True)
                self._yolo_pipeline.roi_gaussian_enabled = self.roi_gaussian_check.isChecked()
                self.statusBar().showMessage("処理を開始しました（差分+YOLO）")
            elif self._yolo_gui_requested:
                self.statusBar().showMessage("処理を開始しました（YOLO 未使用・従来差分）")
            else:
                self.statusBar().showMessage("処理を開始しました")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.update_timer.start()
        except Exception as e:
            self.statusBar().showMessage(f"エラー: {e}")
            print(f"開始エラー: {e}")
    
    def on_stop_clicked(self):
        """停止ボタンのクリック処理"""
        if self.processor is None:
            return
        
        try:
            self.processor.stop()
            self.update_timer.stop()
            
            # ブロードキャストから購読解除
            if self.subscriber_queue is not None and self.processor is not None:
                self.processor.frame_broadcaster.unsubscribe(self.subscriber_queue)
                self.subscriber_queue = None
            
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.roi_gaussian_check.setEnabled(False)
            self._prev_bgr_yolo = None
            self._yolo_frame_index = 0
            self.statusBar().showMessage("処理を停止しました")
        except Exception as e:
            self.statusBar().showMessage(f"エラー: {e}")
            print(f"停止エラー: {e}")
    
    def on_live_camera_clicked(self):
        """リアルタイム映像ボタンのクリック処理"""
        if self.live_camera_window is None or not self.live_camera_window.isVisible():
            # ウィンドウを開く
            if self.processor is None:
                self.statusBar().showMessage("プロセッサが初期化されていません")
                return
            
            if not self.processor.is_running:
                self.statusBar().showMessage("メイン処理が動作していません。先に「開始」ボタンを押してください。")
                return
            
            self.live_camera_window = LiveCameraWindow(self.processor, self)
            if self.live_camera_window.start_camera():
                self.live_camera_window.show()
                self.live_camera_button.setText("リアルタイム映像を閉じる")
                self.statusBar().showMessage("リアルタイム映像ウィンドウを開きました")
            else:
                self.live_camera_window = None
                self.statusBar().showMessage("リアルタイム映像の開始に失敗しました")
        else:
            # ウィンドウを閉じる
            self.live_camera_window.stop_camera()
            self.live_camera_window.close()
            self.live_camera_window = None
            self.live_camera_button.setText("リアルタイム映像")
            self.statusBar().showMessage("リアルタイム映像ウィンドウを閉じました")
    
    def update_frames(self):
        """フレームを更新"""
        if self.processor is None or not self.processor.is_running:
            return
        
        use_yolo_panel = self._yolo_pipeline is not None and hasattr(self, "difference_widget")
        
        # ブロードキャストから最新フレーム（元画像表示・YOLO 差分ストリーム用）
        if self.subscriber_queue is not None:
            try:
                latest_frame = None
                while True:
                    try:
                        latest_frame = self.subscriber_queue.get_nowait()
                    except queue.Empty:
                        break
                
                if latest_frame is not None:
                    current_time = datetime.now()
                    if hasattr(self, "original_widget"):
                        # Run YOLO on the original frame too and draw boxes (fast on GPU)
                        display_frame = latest_frame
                        if use_yolo_panel:
                            try:
                                dets = predict_frame(
                                    self._yolo_pipeline.model,
                                    latest_frame,
                                    conf=self._yolo_pipeline._conf,
                                )
                                display_frame = draw_detections_on_bgr(latest_frame, dets)
                            except Exception:
                                display_frame = latest_frame
                        self.original_widget.update_frame(display_frame, current_time)
                    
                    if self.last_frame_time:
                        elapsed = (current_time - self.last_frame_time).total_seconds()
                        if elapsed > 0:
                            self.fps = 1.0 / elapsed
                    self.last_frame_time = current_time
                    self.frame_count += 1
                    
                    if use_yolo_panel:
                        try:
                            if self._prev_bgr_yolo is not None:
                                out = self._yolo_pipeline.process(
                                    self._prev_bgr_yolo,
                                    latest_frame,
                                    self._yolo_frame_index,
                                )
                                self._yolo_frame_index += 1
                                self.difference_widget.update_frame(
                                    out["overlay_bgr"],
                                    current_time,
                                    status="success",
                                )
                            self._prev_bgr_yolo = latest_frame.copy()
                        except Exception as ex:
                            self.difference_widget.update_frame(
                                None,
                                current_time,
                                status="error",
                                error_message=str(ex),
                            )
            except Exception:
                pass
        
        # 差分画像: YOLO 無効時は frame_buffer から。YOLO 時は統計のみ frame_buffer から取得
        if hasattr(self, 'difference_widget'):
            result = self.processor.frame_buffer.get(timeout=0.01)
            if result is not None:
                process_times = self.processor.process_times
                avg_process_time = sum(process_times[-10:]) / len(process_times[-10:]) if process_times else 0.0
                self.stats_widget.update_stats(
                    fps=self.fps,
                    diff_pixels=result.get("diff_pixels"),
                    diff_ratio=result.get("diff_ratio"),
                    process_time=avg_process_time,
                    frame_number=result.get("frame_number"),
                )
                
                if use_yolo_panel:
                    return
                
                status = result.get("status", "success")
                error_message = result.get("error_message")
                diff_frame = result.get("difference")
                if diff_frame is not None:
                    self.difference_widget.update_frame(
                        diff_frame,
                        result.get("timestamp"),
                        status="success",
                    )
                else:
                    if error_message:
                        self.difference_widget.update_frame(
                            None,
                            result.get("timestamp"),
                            status=status,
                            error_message=error_message,
                        )
                    elif status == "no_difference":
                        self.difference_widget.update_frame(
                            None,
                            result.get("timestamp"),
                            status="no_difference",
                        )
                    else:
                        self.difference_widget.update_frame(
                            None,
                            result.get("timestamp"),
                            status="processing",
                        )
            else:
                if not use_yolo_panel:
                    self.difference_widget.update_frame(None, None, status="processing")
    
    def _on_roi_gaussian_toggled(self, checked: bool):
        """YOLO パイプラインの ROI ガウシアン ON/OFF"""
        if self._yolo_pipeline is not None:
            self._yolo_pipeline.roi_gaussian_enabled = checked
    
    def closeEvent(self, event):
        """ウィンドウを閉じる時の処理"""
        if self.processor and self.processor.is_running:
            self.processor.stop()
        
        # ブロードキャストから購読解除
        if self.subscriber_queue is not None and self.processor is not None:
            self.processor.frame_broadcaster.unsubscribe(self.subscriber_queue)
            self.subscriber_queue = None
        
        if self.live_camera_window:
            self.live_camera_window.stop_camera()
            self.live_camera_window.close()
        event.accept()

    def _on_roi_gaussian_toggled(self, checked: bool):
        """YOLO パイプラインの ROI ガウシアン ON/OFF"""
        if self._yolo_pipeline is not None:
            self._yolo_pipeline.roi_gaussian_enabled = checked


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

