#!/usr/bin/env python3
"""
高速リアルタイムUDPデータビューア (PyQtGraph版) - 修正版
Loopbackモード対応・スレッド管理改善
"""
import sys
import time
import socket
import struct
import threading
import queue
from collections import deque
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
try:
    import pyqtgraph.opengl as gl
except Exception:
    gl = None

pg.setConfigOptions(antialias=True)


class UDPReceiver(threading.Thread):
    """UDP受信スレッド"""

    def __init__(self, data_queue: queue.Queue, host: str = '0.0.0.0', port: int = 1500):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.host = host
        self.port = port
        self.running = False
        self.sock: socket.socket | None = None

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((self.host, self.port))
        except OSError as e:
            # 10049 は無効アドレス。0.0.0.0 にフォールバック
            if getattr(e, 'winerror', None) == 10049:
                print(f"Bind failed on {self.host}:{self.port}, fallback to 0.0.0.0")
                self.sock.bind(('0.0.0.0', self.port))
        self.sock.settimeout(0.5)
        print(f"[UDP] Listening on {self.host}:{self.port}")
        self.running = True

        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                if not self.running:
                    break
                self.parse_packet(data)
            except socket.timeout:
                continue
            except OSError as e:
                # 10038: クローズ後の操作 → 正常終了
                if getattr(e, 'winerror', None) == 10038:
                    break
                if self.running:
                    print(f"UDP error: {e}")
                break
            except Exception as e:
                if self.running:
                    print(f"UDP error: {e}")
                break

    def parse_packet(self, data: bytes):
        """パケット解析: v2優先, v1フォールバック"""
        try:
            if len(data) >= 20:
                magic = struct.unpack_from('<I', data, 0)[0]
                # v2: magic='UDP2'(0x55445032)
                if magic == 0x55445032:
                    _, version, ts_unit, _, seq, t_tick, count = struct.unpack_from('<IBBHIQH', data, 0)
                    if version != 2:
                        return
                    expected = 20 + 4 * count
                    if len(data) >= expected and 0 < count <= 4096:
                        values = struct.unpack_from('<' + 'f' * count, data, 20)
                        t_sec = self.convert_timestamp(t_tick, ts_unit)
                        self.data_queue.put(('udp', t_sec, values))
                        return

            # v1フォールバック
            if len(data) >= 14:
                seq, t_tick, count = struct.unpack_from('<IQH', data, 0)
                expected = 14 + 4 * count
                if len(data) >= expected and 0 < count <= 4096:
                    values = struct.unpack_from('<' + 'f' * count, data, 14)
                    t_sec = float(t_tick) / 1000.0
                    self.data_queue.put(('udp', t_sec, values))
        except Exception as e:
            if self.running:
                print(f"Parse error: {e}")

    @staticmethod
    def convert_timestamp(t_tick: int, unit: int) -> float:
        if unit == 0:  # sec
            return float(t_tick)
        if unit == 1:  # ms
            return float(t_tick) / 1000.0
        if unit == 2:  # us
            return float(t_tick) / 1e6
        if unit == 3:  # ns
            return float(t_tick) / 1e9
        return float(t_tick) / 1000.0

    def stop(self):
        """安全停止"""
        self.running = False
        if self.sock:
            try:
                # ブロッキング解除
                dummy = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                dummy.sendto(b"\x00", ('127.0.0.1', self.port))
                dummy.close()
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class LocalSineGenerator(threading.Thread):
    """ループバック用のローカルサイン波生成スレッド（改善版）"""

    def __init__(self, data_queue: queue.Queue, node_count: int = 21,
                 freq_hz: float = 10.0, rate_pps: float = 200.0):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.node_count = max(1, int(node_count))
        self.freq_hz = float(freq_hz)
        self.rate_pps = max(1.0, float(rate_pps))
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

        # 各ノードに位相・振幅・周波数差を与えて可視的な違いを出す
        self.node_configs = []
        for i in range(self.node_count):
            self.node_configs.append({
                'amplitude': 0.5 + (1.5 * i) / max(1, self.node_count - 1),
                'freq_mult': 1.0 + (0.2 * i),
                'phase': (i / self.node_count) * 2 * np.pi
            })

        # 生成チャンク（約10ms）
        self._chunk_size = max(1, int(self.rate_pps / 100))

    def set_frequency(self, freq_hz: float):
        with self._lock:
            self.freq_hz = float(freq_hz)

    def set_rate(self, rate_pps: float):
        with self._lock:
            self.rate_pps = max(1.0, float(rate_pps))
            # レート変更時はチャンクも更新
            self._chunk_size = max(1, int(self.rate_pps / 100))

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=1.0)

    def run(self):
        """バッチ生成＋一括送信（壁時計ベースで安定化）"""
        get_perf = getattr(time, 'perf_counter', time.time)
        dt = 1.0 / max(1.0, float(self.rate_pps))

        # バッチ長をレートに応じて可変（約20～100ms）
        def compute_batch_size(rate: float) -> int:
            if rate <= 100:
                return max(1, int(rate * 0.10))  # 100ms
            if rate <= 1000:
                return max(1, int(rate * 0.05))  # 50ms
            return max(1, int(rate * 0.02))     # 20ms

        with self._lock:
            batch_size = compute_batch_size(self.rate_pps)

        # 全ノード同一位相・同一振幅で生成する（配列は使用しない）

        # 基準時刻（壁時計/高分解能）
        t0_wall = time.time()
        t0_perf = get_perf()
        sample_count = 0

        while not self._stop_evt.is_set():
            # パラメータ取得
            with self._lock:
                local_freq = float(self.freq_hz)
                local_rate = float(self.rate_pps)
                # レートが変わったら dt/batch 更新
                dt = 1.0 / max(1.0, local_rate)
                batch_size = compute_batch_size(local_rate)

            # バッチ時刻（相対）
            t_batch = (np.arange(batch_size, dtype=np.float64) * dt) + (sample_count * dt)

            # 一括生成（ベクトル）: 全ノード同一振幅・同一位相
            omega_base = 2.0 * np.pi * local_freq
            s = np.sin(omega_base * t_batch)
            # 振幅は1.0固定（必要ならUIで拡張可能）
            s *= 1.0
            batch_data = np.repeat(s[:, None], self.node_count, axis=1)

            # 送信（一括 put_nowait, 溢れたら再試行）
            for j in range(batch_size):
                if self._stop_evt.is_set():
                    break
                wall_time = t0_wall + (sample_count + j) * dt
                try:
                    self.data_queue.put_nowait(('loopback', wall_time, batch_data[j].astype(float).tolist()))
                except queue.Full:
                    time.sleep(0.001)
                    try:
                        self.data_queue.put_nowait(('loopback', wall_time, batch_data[j].astype(float).tolist()))
                    except Exception:
                        pass

            sample_count += batch_size

            # 実効ppsログ（1秒毎）
            if int(sample_count) % int(max(1.0, local_rate)) == 0:
                elapsed = get_perf() - t0_perf
                if elapsed > 0:
                    actual = sample_count / elapsed
                    print(f"[Gen] Target: {local_rate:.0f}pps, Actual: {actual:.0f}pps")

            # 次バッチまで待機（壁時計で精度維持）
            target_perf = t0_perf + (sample_count * dt)
            wait = target_perf - get_perf()
            if wait > 0:
                time.sleep(wait)


class RealtimeGraphWidget(QtWidgets.QWidget):
    """高速リアルタイムグラフウィジェット（改善版）"""

    def __init__(self, node_count: int = 21, window_sec: float = 5.0, sample_rate: int = 100):
        super().__init__()
        self.node_count = node_count
        self.window_sec = window_sec
        self.sample_rate = sample_rate
        self.max_samples = int(window_sec * sample_rate * 1.5)

        # 受信側バッファ
        self.time_buffer = deque(maxlen=self.max_samples)
        self.data_buffers = [deque(maxlen=self.max_samples) for _ in range(node_count)]

        # 送信（上段）専用バッファ
        self.tx_time_buffer = deque(maxlen=self.max_samples)
        self.tx_data_buffer = deque(maxlen=self.max_samples)

        # データキュー
        self.data_queue: queue.Queue = queue.Queue(maxsize=10000)

        # 表示ノード（最大8）
        self.visible_nodes = set(range(min(8, node_count)))

        # アイドル検知
        self.inactive_timeout_sec = 1.0
        self.idle_behavior = 'freeze'  # 'continue' | 'freeze' | 'clear'
        self._last_rx_monotonic = 0.0

        # データソース
        self.source_mode = 'udp'
        self.udp_receiver: UDPReceiver | None = None
        self.local_gen: LocalSineGenerator | None = None
        self.loop_freq = 10.0
        self.loop_rate = 200.0
        self.selected_tx_node = 0

        # 3D 表示準備
        self.gl_enabled = gl is not None
        loaded_pos = self._load_node_positions(self.node_count)
        self.node_positions = loaded_pos if loaded_pos is not None else self._make_layout_positions(self.node_count)
        self.amp_scale = 0.2  # 3D変位スケール
        self.gl_view = None
        self.gl_scatter = None

        # UI
        self.init_ui()

        # UDP受信開始
        self.start_udp()

        # タイマ
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(16)

        self.fps_counter = {'last_time': time.time(), 'frames': 0}

    # ----- UI -----
    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()

        sender_panel = self.create_sender_panel()
        layout.addWidget(sender_panel)

        self.tx_widget = pg.GraphicsLayoutWidget()
        self.tx_widget.setBackground('#0b0e12')
        self.tx_widget.setMaximumHeight(160)
        layout.addWidget(self.tx_widget)
        self.create_tx_plot()

        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)

        # 下段: 左=3D, 右=2D（Splitterで半々）
        self.graph_widget = pg.GraphicsLayoutWidget()
        self.graph_widget.setBackground('#0b0e12')

        bottom_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        if self.gl_enabled:
            self.gl_view = self.create_gl_view()
            bottom_split.addWidget(self.gl_view)
        else:
            placeholder = QtWidgets.QLabel('OpenGL未利用: PyOpenGL の導入で3D表示が有効化されます')
            placeholder.setStyleSheet('color:#aaa; padding: 12px;')
            bottom_split.addWidget(placeholder)
        bottom_split.addWidget(self.graph_widget)
        bottom_split.setStretchFactor(0, 1)
        bottom_split.setStretchFactor(1, 1)
        layout.addWidget(bottom_split)

        self.plots: dict[int, pg.PlotItem] = {}
        self.curves: dict[int, pg.PlotDataItem] = {}
        self.create_plots()

        self.setLayout(layout)
        self.setWindowTitle('PyQtGraph Realtime Viewer (Fixed)')
        self.resize(1200, 900)

    def _make_layout_positions(self, n: int) -> np.ndarray:
        """ノード基本配置（正方グリッドをXZ平面に）"""
        side = int(np.ceil(np.sqrt(n)))
        xs, zs = [], []
        for i in range(n):
            r = i // side
            c = i % side
            xs.append((c - (side - 1) / 2) / max(1, side - 1) * 1.0)
            zs.append((r - (side - 1) / 2) / max(1, side - 1) * 1.0)
        pos = np.stack([np.array(xs), np.zeros(n), np.array(zs)], axis=1).astype(np.float32)
        return pos

    def _load_node_positions(self, n: int) -> np.ndarray | None:
        """`viewer/nodes.csv` があれば読み込んで配置に反映。
        CSV: id,x,y,z を想定。PyQtGraph GL は z が上方向なので、
        csv の z をそのまま上方向に使用する（面直=Z）。
        """
        try:
            nodes_csv = Path(__file__).parent / 'viewer' / 'nodes.csv'
            if not nodes_csv.exists():
                nodes_csv = Path('viewer') / 'nodes.csv'
            if not nodes_csv.exists():
                return None
            import csv
            pos = np.zeros((n, 3), dtype=np.float32)
            with open(nodes_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    idx = int(row['id'])
                    if 0 <= idx < n:
                        x = float(row.get('x', 0.0))
                        y = float(row.get('y', 0.0))
                        z = float(row.get('z', 0.0))
                        # map: csv(x, y, z) -> GL (x, y, z) そのまま
                        pos[idx, 0] = x
                        pos[idx, 1] = y
                        pos[idx, 2] = z
                        count += 1
            if count >= 1:
                return pos
        except Exception:
            return None
        return None

    def create_gl_view(self):
        view = gl.GLViewWidget()
        view.setBackgroundColor((11, 14, 18))
        view.opts['distance'] = 3
        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        view.addItem(grid)
        # 散布
        self.gl_scatter = gl.GLScatterPlotItem(pos=self.node_positions, size=8, pxMode=True, color=(0.31, 0.76, 0.97, 0.9))
        view.addItem(self.gl_scatter)
        return view

    def create_sender_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(QtWidgets.QLabel('Source:'))
        self.source_cb = QtWidgets.QComboBox()
        self.source_cb.addItems(['UDP受信', 'Loopback'])
        self.source_cb.currentIndexChanged.connect(self.on_source_changed)
        layout.addWidget(self.source_cb)

        layout.addWidget(QtWidgets.QLabel('表示Node:'))
        self.tx_node_spin = QtWidgets.QSpinBox()
        self.tx_node_spin.setRange(0, self.node_count - 1)
        self.tx_node_spin.valueChanged.connect(self.on_tx_node_changed)
        layout.addWidget(self.tx_node_spin)

        layout.addWidget(QtWidgets.QLabel('Freq:'))
        self.freq_spin = QtWidgets.QDoubleSpinBox()
        self.freq_spin.setRange(0.1, 100.0)
        self.freq_spin.setValue(self.loop_freq)
        self.freq_spin.setSuffix(' Hz')
        self.freq_spin.valueChanged.connect(self.on_freq_changed)
        layout.addWidget(self.freq_spin)

        layout.addWidget(QtWidgets.QLabel('Rate:'))
        self.rate_spin = QtWidgets.QDoubleSpinBox()
        self.rate_spin.setRange(10.0, 5000.0)
        self.rate_spin.setValue(self.loop_rate)
        self.rate_spin.setSuffix(' pps')
        self.rate_spin.setSingleStep(50.0)
        self.rate_spin.valueChanged.connect(self.on_rate_changed)
        layout.addWidget(self.rate_spin)

        self.start_btn = QtWidgets.QPushButton('Start')
        self.stop_btn = QtWidgets.QPushButton('Stop')
        self.start_btn.clicked.connect(self.start_loopback)
        self.stop_btn.clicked.connect(self.stop_loopback)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)

        layout.addStretch()
        panel.setLayout(layout)

        self.update_source_controls()
        return panel

    def create_tx_plot(self):
        self.tx_widget.clear()
        self.tx_plot = self.tx_widget.addPlot()
        self.tx_plot.setLabel('left', 'TX')
        self.tx_plot.setLabel('bottom', 'Time', units='s')
        self.tx_plot.showGrid(x=True, y=True, alpha=0.3)
        self.tx_plot.setYRange(-2, 2)
        self.tx_curve = self.tx_plot.plot(pen=pg.mkPen(color=(255, 193, 7), width=2))

    def create_control_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()

        layout.addWidget(QtWidgets.QLabel('Window:'))
        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(0.5, 60.0)
        self.window_spin.setValue(self.window_sec)
        self.window_spin.setSuffix(' sec')
        self.window_spin.valueChanged.connect(self.on_window_changed)
        layout.addWidget(self.window_spin)

        self.select_btn = QtWidgets.QPushButton('表示ノード選択')
        self.select_btn.clicked.connect(self.show_node_selector)
        layout.addWidget(self.select_btn)

        self.pause_btn = QtWidgets.QPushButton('Pause')
        self.pause_btn.setCheckable(True)
        layout.addWidget(self.pause_btn)

        clear_btn = QtWidgets.QPushButton('Clear')
        clear_btn.clicked.connect(self.clear_data)
        layout.addWidget(clear_btn)

        self.status_label = QtWidgets.QLabel('● 停止')
        self.status_label.setStyleSheet('color: #666; font-size: 14px;')
        layout.addWidget(self.status_label)

        self.fps_label = QtWidgets.QLabel('FPS: 0')
        layout.addWidget(self.fps_label)

        self.rate_label = QtWidgets.QLabel('Rate: 0 Hz')
        layout.addWidget(self.rate_label)

        layout.addWidget(QtWidgets.QLabel('停止時:'))
        self.idle_cb = QtWidgets.QComboBox()
        self.idle_cb.addItems(['継続', 'フリーズ', 'クリア'])
        self.idle_cb.setCurrentIndex(1)
        self.idle_cb.currentIndexChanged.connect(
            lambda i: setattr(self, 'idle_behavior', ['continue', 'freeze', 'clear'][i])
        )
        layout.addWidget(self.idle_cb)

        layout.addStretch()
        panel.setLayout(layout)
        return panel

    def create_plots(self):
        self.graph_widget.clear()
        self.plots.clear()
        self.curves.clear()
        for i, node_id in enumerate(sorted(self.visible_nodes)):
            plot = self.graph_widget.addPlot(row=i, col=0)
            plot.setLabel('left', f'N{node_id}')
            plot.setLabel('bottom', 'Time', units='s')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setYRange(-2, 2, padding=0.1)
            curve = plot.plot(pen=pg.mkPen(color=(79, 195, 247), width=2))
            self.plots[node_id] = plot
            self.curves[node_id] = curve

    # ----- ソース切替/制御 -----
    def on_source_changed(self, index: int):
        if index == 0:
            self.stop_loopback()
            self.start_udp()
            self.source_mode = 'udp'
        else:
            self.stop_udp()
            self.source_mode = 'loopback'
        self.update_source_controls()
        self.clear_data()

    def update_source_controls(self):
        is_loopback = (self.source_mode == 'loopback')
        self.freq_spin.setEnabled(is_loopback)
        self.rate_spin.setEnabled(is_loopback)
        self.start_btn.setEnabled(is_loopback)
        self.stop_btn.setEnabled(is_loopback)
        self.tx_node_spin.setEnabled(is_loopback)

    def start_udp(self):
        if not self.udp_receiver:
            self.udp_receiver = UDPReceiver(self.data_queue)
            self.udp_receiver.start()

    def stop_udp(self):
        if self.udp_receiver:
            self.udp_receiver.stop()
            self.udp_receiver = None

    def start_loopback(self):
        self.stop_loopback()
        self.clear_data()
        self.local_gen = LocalSineGenerator(self.data_queue, self.node_count, self.loop_freq, self.loop_rate)
        self.local_gen.start()
        print(f"[Loopback] Started: {self.loop_freq}Hz @ {self.loop_rate}pps")

    def stop_loopback(self):
        if self.local_gen:
            print("[Loopback] Stopping...")
            self.local_gen.stop()
            self.local_gen = None
            print("[Loopback] Stopped")

    def on_freq_changed(self, value: float):
        self.loop_freq = float(value)
        if self.local_gen:
            self.local_gen.set_frequency(self.loop_freq)

    def on_rate_changed(self, value: float):
        self.loop_rate = float(value)
        if self.local_gen:
            self.local_gen.set_rate(self.loop_rate)

    def on_tx_node_changed(self, value: int):
        self.selected_tx_node = int(value)

    def on_window_changed(self, value: float):
        self.window_sec = float(value)
        self.max_samples = int(self.window_sec * self.sample_rate * 1.5)

    def show_node_selector(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('表示ノード選択')
        layout = QtWidgets.QVBoxLayout()
        grid = QtWidgets.QGridLayout()
        checkboxes = {}
        for i in range(self.node_count):
            cb = QtWidgets.QCheckBox(f'Node {i}')
            cb.setChecked(i in self.visible_nodes)
            checkboxes[i] = cb
            grid.addWidget(cb, i // 4, i % 4)
        layout.addLayout(grid)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        if dialog.exec_():
            self.visible_nodes = {i for i, cb in checkboxes.items() if cb.isChecked()}
            self.visible_nodes = set(list(self.visible_nodes)[:8])
            self.create_plots()

    def clear_data(self):
        self.time_buffer.clear()
        for buf in self.data_buffers:
            buf.clear()
        self.tx_time_buffer.clear()
        self.tx_data_buffer.clear()
        # キューもクリア
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except Exception:
                break
        # 曲線クリア
        if hasattr(self, 'tx_curve') and self.tx_curve is not None:
            try:
                self.tx_curve.setData([], [])
            except Exception:
                pass
        for curve in self.curves.values():
            try:
                curve.setData([], [])
            except Exception:
                pass
        # ステータスリセット
        self._last_rx_monotonic = 0.0
        self.rate_label.setText('Rate: 0 Hz')
        self.status_label.setText('● 停止')
        self.status_label.setStyleSheet('color: #666; font-size: 14px;')

    # ----- 更新ループ -----
    def update_plots(self):
        if self.pause_btn.isChecked():
            return
        new_data = []
        try:
            for _ in range(20):
                source, t, values = self.data_queue.get_nowait()
                new_data.append((source, t, values))
        except queue.Empty:
            pass

        had_new_data = False
        for source, t, values in new_data:
            if source == 'loopback':
                self.tx_time_buffer.append(t)
                if self.selected_tx_node < len(values):
                    self.tx_data_buffer.append(values[self.selected_tx_node])
                else:
                    self.tx_data_buffer.append(0.0)
            self.time_buffer.append(t)
            for i, val in enumerate(values[:self.node_count]):
                self.data_buffers[i].append(val)
            had_new_data = True

        if had_new_data:
            self._last_rx_monotonic = time.monotonic()

        self.update_status(had_new_data)

        if not had_new_data and self._last_rx_monotonic:
            idle_time = time.monotonic() - self._last_rx_monotonic
            if idle_time > self.inactive_timeout_sec:
                if self.idle_behavior == 'clear':
                    self.clear_data()
                    self.update_fps()
                    return
                if self.idle_behavior == 'freeze':
                    self.update_fps()
                    return

        # 3D更新（最新値をYに反映）
        if self.gl_enabled and self.gl_scatter is not None and len(self.data_buffers[0]) > 0:
            latest = np.array([self.data_buffers[i][-1] if len(self.data_buffers[i]) > 0 else 0.0 for i in range(self.node_count)], dtype=np.float32)
            base = self.node_positions
            pos = base.copy()
            # 縦方向は GL の z 軸
            pos[:, 2] = base[:, 2] + latest * self.amp_scale
            try:
                self.gl_scatter.setData(pos=pos)
            except Exception:
                pass

        self.draw_graphs()
        self.update_fps()

    def draw_graphs(self):
        # 上段送信
        if len(self.tx_time_buffer) > 1:
            tx_time = np.array(self.tx_time_buffer)
            tx_data = np.array(self.tx_data_buffer)
            t_max = tx_time[-1]
            t_min = max(tx_time[0], t_max - self.window_sec)
            mask = (tx_time >= t_min) & (tx_time <= t_max)
            if mask.any():
                self.tx_curve.setData(tx_time[mask], tx_data[mask])

        # 下段受信
        if len(self.time_buffer) > 1:
            t_arr = np.array(self.time_buffer)
            t_max = t_arr[-1]
            t_min = max(t_arr[0], t_max - self.window_sec)
            mask = (t_arr >= t_min) & (t_arr <= t_max)
            if not mask.any():
                return
            disp_t = t_arr[mask]
            for node_id in self.visible_nodes:
                if node_id in self.curves and node_id < len(self.data_buffers):
                    v_arr = np.array(self.data_buffers[node_id])
                    if len(v_arr) == len(t_arr):
                        disp_v = v_arr[mask]
                    else:
                        # 長さ不一致時は末尾合わせ
                        disp_v = v_arr[-len(disp_t):]
                    if len(disp_v) > 0:
                        self.curves[node_id].setData(disp_t, disp_v)
                        y_min, y_max = float(np.min(disp_v)), float(np.max(disp_v))
                        if abs(y_max - y_min) > 1e-3:
                            margin = (y_max - y_min) * 0.1
                            self.plots[node_id].setYRange(y_min - margin, y_max + margin, padding=0)

    def update_status(self, has_new_data: bool):
        if has_new_data:
            if self.source_mode == 'loopback':
                self.status_label.setText('● Loopback')
            else:
                self.status_label.setText('● 受信中')
            self.status_label.setStyleSheet('color: #4CAF50; font-size: 14px;')
            if len(self.time_buffer) >= 10:
                # 直近10サンプルの dt から中央値で推定（0/非正を除外）
                t_list = list(self.time_buffer)[-10:]
                dt = np.diff(t_list)
                dt = dt[np.isfinite(dt) & (dt > 0)]
                if dt.size > 0:
                    med = float(np.median(dt))
                    if med > 0:
                        rate = 1.0 / med
                        self.rate_label.setText(f'Rate: {rate:.1f} Hz')
        else:
            if self._last_rx_monotonic:
                idle = time.monotonic() - self._last_rx_monotonic
                if idle < self.inactive_timeout_sec:
                    self.status_label.setText(f'● 待機 {idle:.1f}s')
                    self.status_label.setStyleSheet('color: #FFC107; font-size: 14px;')
                else:
                    self.status_label.setText('● 停止')
                    self.status_label.setStyleSheet('color: #666; font-size: 14px;')

    def update_fps(self):
        self.fps_counter['frames'] += 1
        now = time.time()
        dt = now - self.fps_counter['last_time']
        if dt >= 1.0:
            fps = self.fps_counter['frames'] / dt
            self.fps_label.setText(f'FPS: {fps:.0f}')
            self.fps_counter['frames'] = 0
            self.fps_counter['last_time'] = now

    def closeEvent(self, event):
        self.timer.stop()
        self.stop_loopback()
        self.stop_udp()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    # ダークテーマ
    app.setStyle('Fusion')
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(11, 14, 18))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(25, 28, 35))
    palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    app.setPalette(palette)

    widget = RealtimeGraphWidget(node_count=21)
    widget.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()


