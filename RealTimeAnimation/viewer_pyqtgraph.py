#!/usr/bin/env python3
"""
高速リアルタイムUDPデータビューア (PyQtGraph版)
100Hz×21ノードの表示も可能
"""
import sys
import time
import socket
import struct
import threading
import queue
import json
from pathlib import Path
from collections import deque
import numpy as np

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
pg.setConfigOptions(antialias=True)


class UDPReceiver(threading.Thread):
    """UDP受信スレッド"""
    def __init__(self, data_queue, host='0.0.0.0', port=1500):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.host = host
        self.port = port
        self.running = False
        self.sock = None
        
    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((self.host, self.port))
        except OSError as e:
            if getattr(e, 'winerror', None) == 10049:
                print(f"Bind failed on {self.host}:{self.port}, fallback to 0.0.0.0")
                self.sock.bind(('0.0.0.0', self.port))
        
        self.sock.settimeout(0.5)
        print(f'[UDP] Listening on {self.host}:{self.port}')
        self.running = True
        
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                self.parse_packet(data)
            except socket.timeout:
                continue
            except OSError as e:
                # ソケットクローズ後の 10038 は無視して終了
                if getattr(e, 'winerror', None) == 10038:
                    break
                if self.running:
                    print(f"UDP error: {e}")
                break
            except Exception as e:
                if self.running:
                    print(f"UDP error: {e}")
                break
                
    def parse_packet(self, data):
        """パケット解析"""
        try:
            # v2プロトコル判定
            if len(data) >= 22:
                magic = struct.unpack_from('<I', data, 0)[0]
                if magic == 0x55445032:  # 'UDP2'
                    _, version, ts_unit, _, seq, t_tick, count = struct.unpack_from('<IBBHIQH', data, 0)
                    if len(data) >= 22 + 4 * count:
                        values = struct.unpack_from('<' + 'f' * count, data, 22)
                        t_sec = self.convert_timestamp(t_tick, ts_unit)
                        self.data_queue.put((t_sec, values))
                        return
            
            # v1プロトコル
            if len(data) >= 14:
                seq, t_tick, count = struct.unpack_from('<IQH', data, 0)
                if len(data) >= 14 + 4 * count:
                    values = struct.unpack_from('<' + 'f' * count, data, 14)
                    t_sec = float(t_tick) / 1000.0  # デフォルトms
                    self.data_queue.put((t_sec, values))
                    
        except Exception as e:
            print(f"Parse error: {e}")
            
    def convert_timestamp(self, t_tick, unit):
        """タイムスタンプ単位変換"""
        if unit == 0:  # seconds
            return float(t_tick)
        elif unit == 1:  # milliseconds
            return float(t_tick) / 1000.0
        elif unit == 2:  # microseconds
            return float(t_tick) / 1e6
        elif unit == 3:  # nanoseconds
            return float(t_tick) / 1e9
        else:
            return float(t_tick) / 1000.0
            
    def stop(self):
        self.running = False
        try:
            if self.sock:
                # ダミー送信でブロッキングrecvfromを解除
                try:
                    self.sock.sendto(b"\x00", (self.host if self.host != '0.0.0.0' else '127.0.0.1', self.port))
                except Exception:
                    pass
                self.sock.close()
                self.sock = None
        except Exception:
            pass
        try:
            self.join(timeout=0.5)
        except Exception:
            pass


class LocalSineGenerator(threading.Thread):
    """ループバック用のローカルサイン波生成スレッド（送信統合）"""
    def __init__(self, data_queue: queue.Queue, node_count: int, target_node: int = 0,
                 freq_hz: float = 10.0, rate_pps: float = 200.0, amplitude: float = 1.0):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.node_count = max(1, int(node_count))
        self.target_node = max(0, int(target_node))
        self.freq_hz = float(freq_hz)
        self.rate_pps = max(1.0, float(rate_pps))
        self.amplitude = float(amplitude)
        self._stop_evt = threading.Event()
        self._phase = 0.0

    def stop(self):
        self._stop_evt.set()

    def run(self):
        period = 1.0 / self.rate_pps
        two_pi = 6.283185307179586
        last = time.perf_counter()
        while not self._stop_evt.is_set():
            now = time.time()
            dt = time.perf_counter() - last
            last += dt
            self._phase += dt * self.freq_hz * two_pi
            val = self.amplitude * np.sin(self._phase)
            values = [0.0] * self.node_count
            if 0 <= self.target_node < self.node_count:
                values[self.target_node] = float(val)
            self.data_queue.put((now, values))
            if period > 0:
                time.sleep(period)


class RealtimeGraphWidget(QtWidgets.QWidget):
    """高速リアルタイムグラフウィジェット"""
    
    def __init__(self, node_count=21, window_sec=5.0, sample_rate=100):
        super().__init__()
        self.node_count = node_count
        self.window_sec = window_sec
        self.sample_rate = sample_rate
        self.max_samples = int(window_sec * sample_rate * 1.5)  # バッファに余裕
        
        # データバッファ（NumPy配列で高速化）
        self.time_buffer = deque(maxlen=self.max_samples)
        self.data_buffers = [deque(maxlen=self.max_samples) 
                            for _ in range(node_count)]
        
        # データキュー
        self.data_queue = queue.Queue()
        
        # 表示するノードの選択
        self.visible_nodes = set(range(min(8, node_count)))  # 初期は最大8個

        # アイドル検知/自動クリア設定
        self.inactive_timeout_sec = 1.0
        self.auto_clear_on_idle = True
        self._last_rx_monotonic = 0.0
        # 停止時の動作モード: 'clear' | 'freeze' | 'continue'
        self.idle_behavior = 'clear'
        # アイドル時のタイマー間隔制御
        self._active_interval_ms = 16
        self._idle_interval_ms = 200
        # ソース切替
        self.source_mode = 'udp'  # 'udp' | 'loopback'
        self.local_gen = None
        self.loop_node = 0
        self.loop_freq = 10.0
        self.loop_rate = 200.0
        self.loop_amp = 1.0
        
        # UI構築
        self.init_ui()
        
        # UDP受信スレッド起動
        self.udp_receiver = UDPReceiver(self.data_queue)
        self.udp_receiver.start()
        
        # 更新タイマー（60fps）
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(self._active_interval_ms)
        
        # 統計情報
        self.fps_counter = {'last_time': time.time(), 'frames': 0}
        
    def init_ui(self):
        """UI初期化"""
        layout = QtWidgets.QVBoxLayout()

        # 送信側（上段）
        sender_panel = self.create_sender_panel()
        layout.addWidget(sender_panel)
        self.tx_widget = pg.GraphicsLayoutWidget()
        self.tx_widget.setBackground('#0b0e12')
        layout.addWidget(self.tx_widget)
        self.tx_plot = None
        self.tx_curve = None
        self.create_tx_plot()
        
        # コントロールパネル
        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)
        
        # グラフエリア
        self.graph_widget = pg.GraphicsLayoutWidget()
        self.graph_widget.setBackground('#0b0e12')
        layout.addWidget(self.graph_widget)
        
        # グラフ作成
        self.plots = {}
        self.curves = {}
        self.create_plots()
        
        self.setLayout(layout)
        self.setWindowTitle('PyQtGraph Realtime Viewer')
        self.resize(1200, 800)
        
    def create_sender_panel(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel('Sender:'))

        # ソース切替
        self.source_cb = QtWidgets.QComboBox()
        self.source_cb.addItems(['UDP受信', 'Loopback送信'])
        self.source_cb.setCurrentIndex(0)
        self.source_cb.currentIndexChanged.connect(self.on_source_changed)
        layout.addWidget(self.source_cb)

        # Loopback 設定
        self.loop_node_cb = QtWidgets.QComboBox()
        for i in range(self.node_count):
            self.loop_node_cb.addItem(f'N{i}', userData=i)
        self.loop_node_cb.currentIndexChanged.connect(lambda i: self.on_loop_node_changed(int(self.loop_node_cb.itemData(i))))
        layout.addWidget(QtWidgets.QLabel('Node'))
        layout.addWidget(self.loop_node_cb)

        self.loop_freq_spin = QtWidgets.QDoubleSpinBox(); self.loop_freq_spin.setRange(0.01, 500.0); self.loop_freq_spin.setValue(self.loop_freq); self.loop_freq_spin.setSuffix(' Hz')
        self.loop_freq_spin.valueChanged.connect(lambda v: setattr(self, 'loop_freq', float(v)))
        layout.addWidget(QtWidgets.QLabel('Freq'))
        layout.addWidget(self.loop_freq_spin)

        self.loop_rate_spin = QtWidgets.QDoubleSpinBox(); self.loop_rate_spin.setRange(1.0, 5000.0); self.loop_rate_spin.setValue(self.loop_rate); self.loop_rate_spin.setSuffix(' pps')
        self.loop_rate_spin.valueChanged.connect(lambda v: setattr(self, 'loop_rate', float(v)))
        layout.addWidget(QtWidgets.QLabel('Rate'))
        layout.addWidget(self.loop_rate_spin)

        self.loop_amp_spin = QtWidgets.QDoubleSpinBox(); self.loop_amp_spin.setRange(0.0, 5.0); self.loop_amp_spin.setSingleStep(0.1); self.loop_amp_spin.setValue(self.loop_amp)
        self.loop_amp_spin.valueChanged.connect(lambda v: setattr(self, 'loop_amp', float(v)))
        layout.addWidget(QtWidgets.QLabel('Amp'))
        layout.addWidget(self.loop_amp_spin)

        self.loop_start_btn = QtWidgets.QPushButton('LB Start')
        self.loop_stop_btn = QtWidgets.QPushButton('LB Stop')
        self.loop_start_btn.clicked.connect(self.start_loopback)
        self.loop_stop_btn.clicked.connect(self.stop_loopback)
        layout.addWidget(self.loop_start_btn)
        layout.addWidget(self.loop_stop_btn)

        layout.addStretch()
        panel.setLayout(layout)
        self.update_source_controls()
        return panel

    def create_tx_plot(self):
        self.tx_widget.clear()
        self.tx_plot = self.tx_widget.addPlot(row=0, col=0)
        self.tx_plot.setLabel('left', 'Sender', units='')
        self.tx_plot.setLabel('bottom', 'Time', units='s')
        self.tx_plot.showGrid(x=True, y=True, alpha=0.3)
        pen = pg.mkPen(color=(255, 193, 7), width=2)
        self.tx_curve = self.tx_plot.plot(pen=pen)

    def create_control_panel(self):
        """コントロールパネル作成"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()
        
        # ウィンドウ幅
        layout.addWidget(QtWidgets.QLabel('Window:'))
        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(0.5, 60.0)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(self.window_sec)
        self.window_spin.setSuffix(' sec')
        self.window_spin.valueChanged.connect(self.on_window_changed)
        layout.addWidget(self.window_spin)
        
        # ノード選択ボタン
        self.select_btn = QtWidgets.QPushButton('表示ノード選択')
        self.select_btn.clicked.connect(self.show_node_selector)
        layout.addWidget(self.select_btn)
        
        # 一時停止
        self.pause_btn = QtWidgets.QPushButton('Pause')
        self.pause_btn.setCheckable(True)
        layout.addWidget(self.pause_btn)
        
        # クリア
        clear_btn = QtWidgets.QPushButton('Clear')
        clear_btn.clicked.connect(self.clear_data)
        layout.addWidget(clear_btn)
        
        # FPS表示
        self.fps_label = QtWidgets.QLabel('FPS: 0')
        layout.addWidget(self.fps_label)
        
        # サンプリングレート表示
        self.rate_label = QtWidgets.QLabel('Rate: 0 Hz')
        layout.addWidget(self.rate_label)

        # 自動クリアトグル
        self.auto_clear_cb = QtWidgets.QCheckBox('AutoClear')
        self.auto_clear_cb.setChecked(True)
        self.auto_clear_cb.stateChanged.connect(lambda s: setattr(self, 'auto_clear_on_idle', bool(s)))
        layout.addWidget(self.auto_clear_cb)

        # 受信ステータス表示
        self.status_label = QtWidgets.QLabel('● 停止')
        self.status_label.setStyleSheet('color:#F44336; font-size:16px;')
        layout.addWidget(self.status_label)

        # 停止時の挙動
        layout.addWidget(QtWidgets.QLabel('停止時:'))
        self.idle_mode = QtWidgets.QComboBox()
        self.idle_mode.addItems(['継続表示', 'フリーズ', '自動クリア'])
        self.idle_mode.setCurrentIndex(2)
        def _on_mode(i):
            self.idle_behavior = ['continue','freeze','clear'][i]
        self.idle_mode.currentIndexChanged.connect(_on_mode)
        layout.addWidget(self.idle_mode)

        # 送信側UIは上段に移設したため、ここでは削除
        
        layout.addStretch()
        panel.setLayout(layout)
        return panel
        
    def create_plots(self):
        """グラフ作成"""
        self.graph_widget.clear()
        self.plots.clear()
        self.curves.clear()
        
        for i, node_id in enumerate(sorted(self.visible_nodes)):
            plot = self.graph_widget.addPlot(row=i, col=0)
            plot.setLabel('left', f'N{node_id}', units='')
            plot.setLabel('bottom', 'Time', units='s')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setYRange(-2, 2, padding=0.1)
            
            # アンチエイリアス付きの高速曲線
            pen = pg.mkPen(color=(79, 195, 247), width=2)
            curve = plot.plot(pen=pen)
            
            self.plots[node_id] = plot
            self.curves[node_id] = curve
            
    def on_source_changed(self, idx: int):
        self.source_mode = 'udp' if idx == 0 else 'loopback'
        if self.source_mode == 'loopback':
            self.stop_udp()
        else:
            self.start_udp()
        self.update_source_controls()

    def update_source_controls(self):
        is_loop = (self.source_mode == 'loopback')
        # 上段UIの有効/無効
        for w in [self.loop_node_cb, self.loop_freq_spin, self.loop_rate_spin, self.loop_amp_spin, self.loop_start_btn, self.loop_stop_btn]:
            w.setEnabled(is_loop)

    def start_udp(self):
        if self.udp_receiver and not self.udp_receiver.running:
            try:
                self.udp_receiver = UDPReceiver(self.data_queue)
                self.udp_receiver.start()
            except Exception:
                pass

    def stop_udp(self):
        if self.udp_receiver and self.udp_receiver.running:
            try:
                self.udp_receiver.stop()
            except Exception:
                pass

    def start_loopback(self):
        self.stop_loopback()
        self.local_gen = LocalSineGenerator(self.data_queue, self.node_count,
                                            target_node=self.loop_node,
                                            freq_hz=self.loop_freq,
                                            rate_pps=self.loop_rate,
                                            amplitude=self.loop_amp)
        self.local_gen.start()
        # Loopback開始直後は受信側バッファをクリアして視覚的に分かりやすく
        self.clear_data()
        self.on_loop_node_changed(self.loop_node)

    def stop_loopback(self):
        if self.local_gen:
            try:
                self.local_gen.stop()
            except Exception:
                pass
            self.local_gen = None

    def on_loop_node_changed(self, node_idx: int):
        self.loop_node = int(node_idx)
        # 送信波形の単独グラフに、最新データから選択ノードの時系列を表示
        if len(self.time_buffer) > 1:
            time_array = np.array(self.time_buffer)
            t_max = time_array[-1]
            t_min = max(time_array[0], t_max - self.window_sec)
            mask = (time_array >= t_min) & (time_array <= t_max)
            display_time = time_array[mask]
            data_array = np.array(self.data_buffers[self.loop_node]) if self.loop_node < len(self.data_buffers) else np.array([])
            if data_array.size > 0 and display_time.size > 0:
                display_data = data_array[-len(display_time):]
                self.tx_curve.setData(display_time, display_data)

    def update_plots(self):
        """グラフ更新（メインループ）"""
        if self.pause_btn.isChecked():
            return
            
        # キューからデータ取得（バッチ処理で高速化）
        new_data = []
        try:
            while True:
                t, values = self.data_queue.get_nowait()
                new_data.append((t, values))
                if len(new_data) >= 10:  # バッチサイズ
                    break
        except queue.Empty:
            pass
            
        # データ追加
        for t, values in new_data:
            self.time_buffer.append(t)
            for i, val in enumerate(values[:self.node_count]):
                self.data_buffers[i].append(val)
        if new_data:
            self._last_rx_monotonic = time.monotonic()
            # 受信が再開されたら更新間隔を復帰
            if self.timer.interval() != self._active_interval_ms:
                self.timer.setInterval(self._active_interval_ms)
            # Loopbackでも上段の曲線を随時更新
            if self.tx_curve is not None and self.loop_node < len(self.data_buffers):
                try:
                    arr_t = np.array(self.time_buffer)
                    t_max = arr_t[-1]
                    t_min = max(arr_t[0], t_max - self.window_sec)
                    mask = (arr_t >= t_min) & (arr_t <= t_max)
                    arr_v = np.array(self.data_buffers[self.loop_node])
                    if arr_v.size > 0:
                        self.tx_curve.setData(arr_t[mask], arr_v[-mask.sum():])
                except Exception:
                    pass
        had_new_data = bool(new_data)

        # ステータス表示
        if had_new_data:
            self.status_label.setStyleSheet('color:#4CAF50; font-size:16px;')
            self.status_label.setText('● 受信中')
        elif self._last_rx_monotonic:
            idle_time = time.monotonic() - self._last_rx_monotonic
            if idle_time < self.inactive_timeout_sec:
                self.status_label.setStyleSheet('color:#FFC107; font-size:16px;')
                self.status_label.setText(f'● 待機 {idle_time:.1f}s')
            else:
                self.status_label.setStyleSheet('color:#F44336; font-size:16px;')
                self.status_label.setText('● 停止')
        else:
            self.status_label.setStyleSheet('color:#F44336; font-size:16px;')
            self.status_label.setText('● 停止')
                
        # 送信停止のアイドル検知（自動クリア/停止）
        if self._last_rx_monotonic:
            idle_elapsed = (time.monotonic() - self._last_rx_monotonic)
            # アイドル期間は描画間隔を下げる（CPU削減と見かけの停止を安定化）
            if not had_new_data and self.timer.interval() != self._idle_interval_ms:
                self.timer.setInterval(self._idle_interval_ms)
            if self.idle_behavior == 'clear' and self.auto_clear_on_idle and idle_elapsed > self.inactive_timeout_sec:
                self.clear_data()
                self.rate_label.setText('Rate: 0.0 Hz')
                self._last_rx_monotonic = 0.0
                self.update_fps()
                return
            if (not had_new_data) and self.idle_behavior == 'freeze':
                # 何も更新しない（完全停止表示）
                self.update_fps()
                return

        # サンプリングレート推定（新規受信時のみ、ゼロ割防止）
        if had_new_data and len(self.time_buffer) >= 10:
            arr = np.array(self.time_buffer, dtype=float)[-10:]
            dt = np.diff(arr)
            dt = dt[np.isfinite(dt)]
            dt = dt[dt > 0]
            if dt.size > 0:
                med = float(np.median(dt))
                if med > 0:
                    rate = 1.0 / med
                    self.rate_label.setText(f'Rate: {rate:.1f} Hz')
                else:
                    self.rate_label.setText('Rate: 0.0 Hz')
            else:
                self.rate_label.setText('Rate: 0.0 Hz')
                
        # グラフ描画（新規データが無い場合の処理）
        if not had_new_data:
            if self.idle_behavior == 'continue':
                pass  # 直近データをそのまま描画（軸固定）
            else:
                self.update_fps()
                return

        if len(self.time_buffer) > 1:
            # NumPy配列に変換（高速化）
            time_array = np.array(self.time_buffer)
            
            # 表示範囲計算
            t_max = time_array[-1]
            t_min = max(time_array[0], t_max - self.window_sec)
            
            # 表示範囲のインデックス取得
            mask = (time_array >= t_min) & (time_array <= t_max)
            display_time = time_array[mask]
            
            for node_id in self.visible_nodes:
                if node_id in self.curves:
                    data_array = np.array(self.data_buffers[node_id])
                    if len(data_array) > 0:
                        display_data = data_array[mask] if len(data_array) == len(time_array) else data_array
                        
                        # setDataは非常に高速
                        self.curves[node_id].setData(display_time, display_data[-len(display_time):])

                        # 上段送信ビュー（Loopback時は送信、UDP時は選択ノードの受信プレビュー）
                        if self.tx_curve is not None and node_id == self.loop_node:
                            self.tx_curve.setData(display_time, display_data[-len(display_time):])
                        
                        # Y軸自動調整
                        if len(display_data) > 0:
                            y_min, y_max = display_data.min(), display_data.max()
                            margin = (y_max - y_min) * 0.1 + 0.01
                            self.plots[node_id].setYRange(y_min - margin, y_max + margin, padding=0)
                            
        # FPS更新
        self.update_fps()
        
    def update_fps(self):
        """FPS計算と表示"""
        self.fps_counter['frames'] += 1
        now = time.time()
        dt = now - self.fps_counter['last_time']
        if dt >= 1.0:
            fps = self.fps_counter['frames'] / dt
            self.fps_label.setText(f'FPS: {fps:.0f}')
            self.fps_counter['frames'] = 0
            self.fps_counter['last_time'] = now
            
    def show_node_selector(self):
        """ノード選択ダイアログ"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('表示ノード選択')
        layout = QtWidgets.QVBoxLayout()
        
        # チェックボックスグリッド
        grid = QtWidgets.QGridLayout()
        checkboxes = {}
        for i in range(self.node_count):
            cb = QtWidgets.QCheckBox(f'Node {i}')
            cb.setChecked(i in self.visible_nodes)
            checkboxes[i] = cb
            grid.addWidget(cb, i // 4, i % 4)
        layout.addLayout(grid)
        
        # ボタン
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec_():
            # 選択を反映
            self.visible_nodes = {i for i, cb in checkboxes.items() if cb.isChecked()}
            self.visible_nodes = set(list(self.visible_nodes)[:8])  # 最大8個
            self.create_plots()
            
    def on_window_changed(self, value):
        """ウィンドウ幅変更"""
        self.window_sec = value
        self.max_samples = int(value * self.sample_rate * 1.5)
        
    def clear_data(self):
        """データクリア"""
        self.time_buffer.clear()
        for buf in self.data_buffers:
            buf.clear()
            
    def closeEvent(self, event):
        """終了処理"""
        self.timer.stop()
        self.udp_receiver.stop()
        event.accept()


def main():
    # config.json読み込み
    config = {}
    try:
        with open('viewer/config.json', 'r') as f:
            config = json.load(f)
    except Exception:
        pass
        
    app = QtWidgets.QApplication(sys.argv)
    
    # ダークテーマ
    app.setStyle('Fusion')
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(11, 14, 18))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(25, 28, 35))
    palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    app.setPalette(palette)
    
    # メインウィンドウ
    node_count = config.get('nodes', {}).get('count', 21)
    widget = RealtimeGraphWidget(node_count=node_count)
    widget.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()


