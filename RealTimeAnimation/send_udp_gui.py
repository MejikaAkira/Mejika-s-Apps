import math
import socket
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path


class UdpSineSender:
    def __init__(self, timestamp_unit: str = 'ms'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.thread = None
        self.stop_evt = threading.Event()
        self.seq = 0
        self._lock = threading.Lock()
        self._target_nodes = 21
        self._target_freq = 100.0
        self._target_rate = 120.0
        self.timestamp_unit = str(timestamp_unit).lower()

    def _get_timestamp(self) -> int:
        if self.timestamp_unit == 'ns':
            return int(time.time_ns())
        if self.timestamp_unit == 'us':
            return int(time.time() * 1e6)
        if self.timestamp_unit == 's':
            return int(time.time())
        return int(time.time() * 1e3)

    def start(self, host: str, port: int, nodes: int, freq_hz: float, rate_pps: float):
        if self.thread and self.thread.is_alive():
            return
        self.stop_evt.clear()
        with self._lock:
            self._target_nodes = int(nodes)
            self._target_freq = float(freq_hz)
            self._target_rate = float(rate_pps)
        self.thread = threading.Thread(
            target=self._run, args=(host, port, nodes, freq_hz, rate_pps), daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stop_evt.set()
        if self.thread:
            self.thread.join(timeout=1.0)

    def set_params(self, *, nodes: int | None = None, freq_hz: float | None = None, rate_pps: float | None = None):
        with self._lock:
            if nodes is not None:
                self._target_nodes = int(nodes)
            if freq_hz is not None:
                self._target_freq = float(freq_hz)
            if rate_pps is not None:
                self._target_rate = float(rate_pps)

    def _run(self, host: str, port: int, nodes: int, freq_hz: float, rate_pps: float):
        with self._lock:
            count = max(1, int(self._target_nodes))
            freq = float(self._target_freq)
            rate = max(1.0, float(self._target_rate))
        period = 1.0 / rate
        amplitudes = [0.1 + (0.5 * i) / (count - 1) if count > 1 else 0.3 for i in range(count)]

        t0 = time.perf_counter()
        next_ts = t0
        sent = 0
        while not self.stop_evt.is_set():
            # 動的パラメータ反映
            with self._lock:
                new_count = max(1, int(self._target_nodes))
                new_freq = float(self._target_freq)
                new_rate = max(1.0, float(self._target_rate))
            if new_count != count:
                count = new_count
                amplitudes = [0.1 + (0.5 * i) / (count - 1) if count > 1 else 0.3 for i in range(count)]
                # バッファ再開タイミングを合わせる
                next_ts = time.perf_counter()
            if new_rate != rate:
                rate = new_rate
                period = 1.0 / rate
                next_ts = time.perf_counter()
            freq = new_freq

            t = time.perf_counter() - t0
            # 設定された単位でタイムスタンプを生成
            ts = self._get_timestamp()
            omega = 2.0 * math.pi * freq
            values = [float(amplitudes[i] * math.sin(omega * t)) for i in range(count)]
            # v2 パケットヘッダ（22 bytes）
            MAGIC = 0x55445032  # 'UDP2'
            VERSION = 2
            unit_map = {'s': 0, 'ms': 1, 'us': 2, 'ns': 3}
            ts_unit_code = unit_map.get(self.timestamp_unit, 1)
            header = struct.pack('<IBBHIQH', MAGIC, VERSION, ts_unit_code, 0, int(self.seq), int(ts), int(count))
            body = struct.pack('<' + 'f' * count, *values)
            payload = header + body
            try:
                self.sock.sendto(payload, (host, port))
                sent += 1
            except OSError:
                break
            self.seq = (self.seq + 1) & 0xFFFFFFFF
            next_ts += period
            sleep_for = next_ts - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('UDP Sine Sender')
        self.geometry('380x270')
        self.resizable(False, False)

        # Defaults from viewer/config.json
        self.nic_ip_default = '10.8.1.100'
        self.mode_default = 'loopback'
        self.port_default = 1500
        self.nodes_default = 21
        try:
            cfg_path = Path(__file__).parent / 'viewer' / 'config.json'
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                if 'udp' in cfg:
                    self.mode_default = str(cfg['udp'].get('mode', self.mode_default)).lower()
                    self.nic_ip_default = str(cfg['udp'].get('nic_ip', self.nic_ip_default))
                    self.port_default = int(cfg['udp'].get('port', self.port_default))
                if 'nodes' in cfg and isinstance(cfg['nodes'].get('count'), int):
                    self.nodes_default = int(cfg['nodes']['count'])
        except Exception:
            pass

        pad = {'padx': 8, 'pady': 6}
        row = 0

        ttk.Label(self, text='Mode').grid(row=row, column=0, sticky='e', **pad)
        self.mode_var = tk.StringVar(value=self.mode_default)
        self.mode_cb = ttk.Combobox(self, textvariable=self.mode_var, values=['loopback','nic'], state='readonly', width=12)
        self.mode_cb.grid(row=row, column=1, sticky='w', **pad)
        self.mode_cb.bind('<<ComboboxSelected>>', lambda e: self.on_mode_change())
        row += 1

        ttk.Label(self, text='Host').grid(row=row, column=0, sticky='e', **pad)
        initial_host = '127.0.0.1' if self.mode_default == 'loopback' else self.nic_ip_default
        self.host_var = tk.StringVar(value=initial_host)
        ttk.Entry(self, textvariable=self.host_var, width=18).grid(row=row, column=1, **pad)
        row += 1

        ttk.Label(self, text='Port').grid(row=row, column=0, sticky='e', **pad)
        self.port_var = tk.IntVar(value=self.port_default)
        ttk.Entry(self, textvariable=self.port_var, width=8).grid(row=row, column=1, sticky='w', **pad)
        row += 1

        ttk.Label(self, text='Nodes').grid(row=row, column=0, sticky='e', **pad)
        self.nodes_var = tk.IntVar(value=self.nodes_default)
        ttk.Entry(self, textvariable=self.nodes_var, width=8).grid(row=row, column=1, sticky='w', **pad)
        row += 1

        ttk.Label(self, text='Freq [Hz]').grid(row=row, column=0, sticky='e', **pad)
        self.freq_var = tk.DoubleVar(value=100.0)
        ttk.Entry(self, textvariable=self.freq_var, width=8).grid(row=row, column=1, sticky='w', **pad)
        row += 1

        ttk.Label(self, text='Rate [pps]').grid(row=row, column=0, sticky='e', **pad)
        # 既定はナイキストの十分上（20x）
        initial_rate = max(2.0 * float(self.freq_var.get()), 20.0 * float(self.freq_var.get()))
        self.rate_var = tk.DoubleVar(value=initial_rate)
        rate_entry = ttk.Entry(self, textvariable=self.rate_var, width=8)
        rate_entry.grid(row=row, column=1, sticky='w', **pad)
        self._auto_rate = True
        def on_rate_manual(event=None):
            self._auto_rate = True if str(self.rate_var.get()) == str(initial_rate) else False
            # ユーザーがキーボード入力したら自動更新を停止
            self._auto_rate = False
        rate_entry.bind('<KeyRelease>', on_rate_manual)
        row += 1

        btns = ttk.Frame(self)
        btns.grid(row=row, column=0, columnspan=2, pady=12)
        self.start_btn = ttk.Button(btns, text='Start', command=self.on_start)
        self.stop_btn = ttk.Button(btns, text='Stop', command=self.on_stop)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.stop_btn.grid(row=0, column=1, padx=6)

        # config.jsonのtimestamp_unitがあれば反映
        ts_unit = 'ms'
        try:
            cfg_path = Path(__file__).parent / 'config.json'
            if cfg_path.exists():
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    ts_unit = str(cfg.get('udp', {}).get('timestamp_unit', ts_unit)).lower()
        except Exception:
            pass
        self.sender = UdpSineSender(timestamp_unit=ts_unit)

        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def on_mode_change(self):
        mode = self.mode_var.get().lower()
        if mode == 'loopback':
            self.host_var.set('127.0.0.1')
        else:
            self.host_var.set(self.nic_ip_default)

    def on_start(self):
        self.sender.start(
            host=self.host_var.get(),
            port=int(self.port_var.get()),
            nodes=int(self.nodes_var.get()),
            freq_hz=float(self.freq_var.get()),
            rate_pps=float(self.rate_var.get()),
        )
        # ランタイム変更を反映するため、変数にトレースを仕掛ける
        try:
            def on_freq_change(*args):
                f = float(self.freq_var.get())
                # 自動レート: ナイキストの 20x を目安に追従
                if getattr(self, '_auto_rate', True):
                    try:
                        self.rate_var.set(max(2.0 * f, 20.0 * f))
                    except Exception:
                        pass
                self.sender.set_params(freq_hz=f)
            self.freq_var.trace_add('write', on_freq_change)
            self.rate_var.trace_add('write', lambda *args: self.sender.set_params(rate_pps=float(self.rate_var.get())))
            self.nodes_var.trace_add('write', lambda *args: self.sender.set_params(nodes=int(self.nodes_var.get())))
        except Exception:
            pass

    def on_stop(self):
        self.sender.stop()

    def on_close(self):
        try:
            self.sender.stop()
        finally:
            self.destroy()


if __name__ == '__main__':
    App().mainloop()


