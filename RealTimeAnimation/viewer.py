import os
import json
import socket
import struct
import threading
import time
from pathlib import Path
import webview
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = Path(BASE_DIR) / 'viewer' / 'index.html'
GRAPH_HTML = Path(BASE_DIR) / 'viewer' / 'graph.html'


class UdpReceiver:
    """UDP 受信して 2D/3D へ配信する簡易リスナ。

    packet: <seq:uint32><t_ms:uint64><count:uint16><float32[count]>
    """

    @staticmethod
    def detect_timestamp_unit(t_tick: float) -> float:
        """タイムスタンプの単位を自動判定して秒へ変換する。
        - エポック基準: ns/us/ms を現在時刻に近さで推定
        - 相対時間(perf_counter系): 最大1日分の範囲で桁から推定
        """
        try:
            now = time.time()
            epoch_ns = now * 1e9
            epoch_us = now * 1e6
            epoch_ms = now * 1e3
            relative_max_sec = 86400.0

            # 近傍判定（許容誤差を広めに）
            if abs(t_tick - epoch_ns) < 1e11:
                return float(t_tick) / 1e9
            if abs(t_tick - epoch_us) < 1e8:
                return float(t_tick) / 1e6
            if abs(t_tick - epoch_ms) < 1e5:
                return float(t_tick) / 1e3

            # 相対時間の可能性
            if t_tick >= 0 and (float(t_tick) / 1e9) <= relative_max_sec:
                # 桁に応じて推定
                if t_tick > 1e9:
                    return float(t_tick) / 1e9
                if t_tick > 1e6:
                    return float(t_tick) / 1e6
                if t_tick > 1e3:
                    return float(t_tick) / 1e3
                return float(t_tick)

            # デフォルト: ミリ秒扱い
            return float(t_tick) / 1e3
        except Exception:
            return float(t_tick) / 1e3

    def convert_timestamp(self, t_tick: float, force_mode: str | None = None) -> float:
        mode = (force_mode or getattr(self, 'ts_mode', 'auto')).lower()
        if mode == 'auto':
            return self.detect_timestamp_unit(t_tick)
        if mode == 'sec':
            return float(t_tick)
        if mode == 'ms':
            return float(t_tick) / 1000.0
        if mode == 'us':
            return float(t_tick) / 1e6
        if mode == 'ns':
            return float(t_tick) / 1e9
        if mode == 'relative':
            if getattr(self, '_ts_base', None) is None:
                self._ts_base = t_tick
            base = self._ts_base
            if t_tick > 1e9:
                return float(t_tick - base) / 1e9
            if t_tick > 1e6:
                return float(t_tick - base) / 1e6
            if t_tick > 1e3:
                return float(t_tick - base) / 1e3
            return float(t_tick - base)
        return float(t_tick) / 1000.0

    def __init__(self, anim_window: webview.Window, graph_window: webview.Window,
                 host: str = '0.0.0.0', port: int = 1500, max_hz: float = 1000.0,
                 expected_count: int | None = None,
                 graph_hz: float = 30.0, anim_hz: float = 30.0,
                 ts_mode: str = 'auto'):
        self.anim_window = anim_window
        self.graph_window = graph_window
        self.host = host
        self.port = port
        self.max_interval = 1.0 / max_hz if max_hz > 0 else 0.0
        self._stop = threading.Event()
        self._thread = None
        self._last_sent = 0.0
        self.ready_anim = False
        self.ready_graph = False
        self.expected_count = int(expected_count) if expected_count else None
        self._last_mismatch_log = 0.0
        # 集約ディスパッチ用
        self.graph_interval = 1.0 / graph_hz if graph_hz > 0 else 0.0
        self.anim_interval = 1.0 / anim_hz if anim_hz > 0 else 0.0
        self._last_graph_send = 0.0
        self._last_anim_send = 0.0
        self._graph_buf: list[tuple[float, list[float]]] = []
        self._latest_floats: list[float] | None = None
        self._latest_t_sec: float | None = None
        # 動的バッチング
        self._graph_batch_size = 20
        self._last_batch_time = 0.0
        self._batch_count = 0
        # TSモード
        self.ts_mode = ts_mode
        self._ts_base = None

    def mark_anim_ready(self):
        self.ready_anim = True

    def mark_graph_ready(self):
        self.ready_graph = True

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            try:
                sock.bind((self.host, self.port))
            except OSError as e:
                # 10049: The requested address is not valid in its context → フォールバック
                if isinstance(e, OSError) and getattr(e, 'winerror', None) == 10049:
                    print(f"[udp] bind failed on {self.host}:{self.port} (10049). Fallback to 0.0.0.0")
                    sock.bind(('0.0.0.0', self.port))
                    self.host = '0.0.0.0'
                else:
                    raise
            sock.settimeout(0.5)
            print(f'[udp] listening on {self.host}:{self.port}')
            pkt_counter = 0
            last_log = time.perf_counter()
            while not self._stop.is_set():
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    floats = None
                    t_sec = time.time()
                    # v2 プロトコル判定（magic='UDP2'）
                    if len(data) >= 22:
                        try:
                            magic = struct.unpack_from('<I', data, 0)[0]
                            if magic == 0x55445032:
                                magic, version, ts_unit, reserved, seq, t_tick, count = struct.unpack_from('<IBBHIQH', data, 0)
                                if version != 2:
                                    print(f"[udp] Unsupported protocol version: {version}")
                                else:
                                    if ts_unit == 0:
                                        t_sec = self.convert_timestamp(float(t_tick), force_mode='sec')
                                    elif ts_unit == 1:
                                        t_sec = self.convert_timestamp(float(t_tick), force_mode='ms')
                                    elif ts_unit == 2:
                                        t_sec = self.convert_timestamp(float(t_tick), force_mode='us')
                                    elif ts_unit == 3:
                                        t_sec = self.convert_timestamp(float(t_tick), force_mode='ns')
                                    else:
                                        t_sec = self.convert_timestamp(float(t_tick))
                                    expected = 22 + 4 * count
                                    if len(data) >= expected and 0 < count <= 4096:
                                        floats = struct.unpack_from('<' + 'f' * count, data, 22)
                            else:
                                raise ValueError('not v2')
                        except Exception:
                            # v1 フォールバック: <seq:uint32><t_ms:uint64><count:uint16><float32[count]>
                            try:
                                seq, t_tick, count = struct.unpack_from('<IQH', data, 0)
                                expected = 14 + 4 * count
                                if len(data) >= expected and count > 0 and count <= 4096:
                                    floats = struct.unpack_from('<' + 'f' * count, data, 14)
                                    t_sec = self.convert_timestamp(float(t_tick))
                            except Exception:
                                pass
                    # 形式B: float32配列のみ (LE)
                    if floats is None and (len(data) % 4 == 0) and (1 <= len(data) // 4 <= 4096):
                        try:
                            count = len(data) // 4
                            floats = struct.unpack('<' + 'f' * count, data)
                        except Exception:
                            pass
                    # 形式C: double配列 (LE)
                    if floats is None and (len(data) % 8 == 0) and (1 <= len(data) // 8 <= 4096):
                        try:
                            count = len(data) // 8
                            doubles = struct.unpack('<' + 'd' * count, data)
                            floats = [float(v) for v in doubles]
                        except Exception:
                            pass
                    if floats is None:
                        continue
                    # 受信数チェック（不足は0埋め、超過は切り捨て）
                    if self.expected_count is not None and len(floats) != self.expected_count:
                        now_sec = time.perf_counter()
                        if now_sec - self._last_mismatch_log > 1.0:
                            missing_ids = []
                            if len(floats) < self.expected_count:
                                missing_ids = list(range(len(floats), self.expected_count))
                            msg = f"Expected {self.expected_count} samples, got {len(floats)}. Missing IDs: {missing_ids}"
                            print(f"[udp] MISMATCH: {msg}")
                            try:
                                if self.anim_window is not None:
                                    self.anim_window.evaluate_js(
                                        f"(function(){{var e=document.getElementById('error');if(e){{e.textContent='{msg}'.replace(/'/g,'\\\'');e.style.display='block';}}}})();"
                                    )
                                if self.graph_window is not None:
                                    self.graph_window.evaluate_js(
                                        f"(function(){{var e=document.getElementById('error');if(e){{e.textContent='{msg}'.replace(/'/g,'\\\'');e.style.display='block';}}}})();"
                                    )
                            except Exception:
                                pass
                            self._last_mismatch_log = now_sec
                        # 正規化
                        if len(floats) > self.expected_count:
                            floats = floats[:self.expected_count]
                        else:
                            floats = list(floats) + [0.0] * (self.expected_count - len(floats))
                    now = time.perf_counter()
                    # 受信値をバッファへ蓄積
                    try:
                        self._graph_buf.append((float(t_sec), list(map(float, floats))))
                        # バッファの伸びすぎを防止（最大3秒分程度を保持）
                        if len(self._graph_buf) > 6000:
                            self._graph_buf = self._graph_buf[-6000:]
                    except Exception:
                        pass
                    self._latest_floats = list(map(float, floats))
                    self._latest_t_sec = float(t_sec)
                    # 毎秒ログ
                    pkt_counter += 1
                    if now - last_log >= 1.0:
                        try:
                            print(f"[udp] rx={pkt_counter}/s nodes={len(floats)} size={len(data)}B")
                        except Exception:
                            pass
                        pkt_counter = 0
                        last_log = now
                    # 2D グラフへ（動的バッチング: 件数閾値または最大遅延で送信）
                    if self.ready_graph and self.graph_window is not None:
                        if len(self._graph_buf) >= self._graph_batch_size or (self._graph_buf and (now - self._last_graph_send) >= 0.1):
                            try:
                                ts = [item[0] for item in self._graph_buf]
                                frames = [item[1] for item in self._graph_buf]
                                payload = {'ts': ts, 'frames': frames}
                                self.graph_window.evaluate_js(f"window.pushGraphBatch({json.dumps(payload)})")
                                # 動的調整（10バッチごと）
                                self._batch_count += 1
                                if self._batch_count % 10 == 0:
                                    batch_time = now - self._last_batch_time if self._last_batch_time else 0.1
                                    if batch_time < 0.05:
                                        self._graph_batch_size = min(50, self._graph_batch_size + 5)
                                    elif batch_time > 0.15:
                                        self._graph_batch_size = max(5, self._graph_batch_size - 5)
                                    self._last_batch_time = now
                                self._graph_buf.clear()
                            except Exception as e:
                                print('graph batch error:', e)
                            finally:
                                self._last_graph_send = now
                    # 3D へ（約 anim_hz で最新のみ）
                    if self.ready_anim and self.anim_window is not None and self.anim_interval > 0:
                        if (now - self._last_anim_send) >= self.anim_interval and self._latest_floats is not None:
                            try:
                                nodes = [{'id': i, 'amplitude': float(f)} for i, f in enumerate(self._latest_floats)]
                                ts = self._latest_t_sec if self._latest_t_sec is not None else time.time()
                                js_anim = f"window.updateNodes({json.dumps({'timestamp': ts, 'nodes': nodes})})"
                                self.anim_window.evaluate_js(js_anim)
                            except Exception as e:
                                print('anim push error:', e)
                            finally:
                                self._last_anim_send = now
                except Exception as e:
                    print('udp packet parse error:', e)
        finally:
            sock.close()

def main():
    if not INDEX_HTML.exists():
        raise FileNotFoundError(f'index.html not found: {INDEX_HTML}')
    if not GRAPH_HTML.exists():
        raise FileNotFoundError(f'graph.html not found: {GRAPH_HTML}')

    url = INDEX_HTML.as_uri()
    url_graph = GRAPH_HTML.as_uri()

    window = webview.create_window(
        title='RealTime Animation Viewer',
        url=url,
        width=1280,
        height=800,
        resizable=True
    )

    graph_window = webview.create_window(
        title='RealTime Data Graph',
        url=url_graph,
        width=1000,
        height=400,
        resizable=True
    )

    # UDP設定をconfig.jsonから読み込み（mode: auto|loopback|nic）
    udp_host = '0.0.0.0'
    udp_port = 1500
    expected_count = None
    max_hz = 1000.0
    try:
        with open(Path(BASE_DIR) / 'viewer' / 'config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            if 'udp' in cfg:
                udp_port = int(cfg['udp'].get('port', udp_port))
                mode = str(cfg['udp'].get('mode', 'auto')).lower()
                if mode == 'loopback':
                    udp_host = '127.0.0.1'
                elif mode == 'nic':
                    udp_host = str(cfg['udp'].get('nic_ip', cfg['udp'].get('host', '0.0.0.0')))
                else:
                    # auto
                    udp_host = str(cfg['udp'].get('bind', cfg['udp'].get('bind_host', cfg['udp'].get('host', '0.0.0.0'))))
                try:
                    max_hz = float(cfg['udp'].get('max_hz', max_hz))
                except Exception:
                    pass
            if 'nodes' in cfg and isinstance(cfg['nodes'].get('count'), int):
                expected_count = int(cfg['nodes']['count'])
    except Exception:
        pass

    # UDP リスナを起動（ウィンドウ読み込み完了後に送出）
    udp = UdpReceiver(window, graph_window, host=udp_host, port=udp_port, max_hz=max_hz, expected_count=expected_count)
    def on_anim_loaded():
        udp.mark_anim_ready()
        try:
            if expected_count:
                window.evaluate_js(f"window.setNodeCount && window.setNodeCount({expected_count});")
        except Exception:
            pass
    def on_graph_loaded():
        udp.mark_graph_ready()
        try:
            # 2Dはconfig側で固定行にしている想定
            pass
        except Exception:
            pass
    window.events.loaded += on_anim_loaded
    graph_window.events.loaded += on_graph_loaded
    # JS から TS モードを変更可能に
    global global_udp
    global_udp = udp
    class JSBridge:
        @staticmethod
        def set_ts_mode(mode: str):
            try:
                if global_udp:
                    global_udp.ts_mode = str(mode)
                    if global_udp.ts_mode != 'relative':
                        global_udp._ts_base = None
                    print(f"[udp] Timestamp mode changed to: {global_udp.ts_mode}")
                    return True
            except Exception:
                return False
            return False
    try:
        graph_window.expose(JSBridge.set_ts_mode)
    except Exception:
        pass
    udp.start()

    try:
        # Force Edge (Chromium) engine for modern JS/WebGL support
        webview.start(gui='edgechromium', debug=False)
    except Exception as e:
        print('webview failed to start with Edge Chromium:', e)
        print('Falling back to system browser...')
        webbrowser.open(url)

if __name__ == '__main__':
    main()


