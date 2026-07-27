#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LogSense Robot - GUI for the watch robot "ロギー".

Reuses app.py's video display widgets and RealtimeVideoProcessor, and adds the
robot face (expression) and a chat panel on the right.
  Left  : original frame + difference (YOLO) + stats
  Right : face + chat
Wiring: perception (YOLO/diff) -> expression + memory, chat -> expression + exp.
"""

from __future__ import annotations

import json
import queue
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Path setup to resolve existing modules (same as app.py).
sys.path.insert(0, str(Path(__file__).parent / "video_process"))
sys.path.insert(0, str(Path(__file__).parent / "process"))

from app import DifferenceDisplayWidget, StatsWidget, VideoDisplayWidget
from video_process.diff_mask import compute_difference_visual
from video_process.gui_yolo_bridge import build_streaming_yolo_pipeline
from video_process.realtime_video_processor import RealtimeVideoProcessor
from video_process.streaming_yolo_pipeline import draw_detections_on_bgr
from video_process.yolo_infer import predict_frame

from robot.caption_worker import CaptionWorker, WarmupWorker
from robot.chat_panel import ChatPanel
from robot.emotion import Emotion, decide
from robot.face_widget import FaceWidget
from robot.memory import MemoryStore
from robot.perception_bridge import PerceptionBridge
from robot.qwen_vl_client import QwenVLClient
from robot.tts_client import build_tts_client
from robot.tts_text import split_sentences
from robot.tts_worker import TtsWorker

_CONFIG_PATH = Path(__file__).parent / "robot_v2_config.json"
_FRAME_INTERVAL_MS = 33  # about 30 FPS
_MOTION_PIXEL_THRESHOLD = 25  # treat a pixel diff above this as "changed"
_CAPTION_INTERVAL_MIN_SEC = 3  # min live-commentary interval (spinbox lower bound)
_CAPTION_INTERVAL_MAX_SEC = 300  # max live-commentary interval (spinbox upper bound)
_MAX_VLM_IMAGE_SIDE = 768  # downscale to this longest side before the VLM
# User-facing caption prompt (Japanese on purpose).
_DEFAULT_CAPTION_PROMPT = "この画像に写っているものが何か、それは何をしているか、日本語で一文だけで説明してください。"
_STATS_REFRESH_SEC = 0.5  # how often the FPS/latency readout is repainted
# YOLO pauses while the LLM answers, so its last boxes can outlive the scene.
# Past this age they are no longer drawn instead of sticking to moved objects.
_MAX_BOX_AGE_SEC = 0.3
_TTS_STOP_WAIT_MS = 2000  # how long to wait for an interrupted utterance to end
_DEFAULT_YOLO_INTERVAL_TICKS = 15  # legacy default when only the tick key is set


def _read_interval_sec(vision: dict, ms_key: str, legacy_ticks_key: str) -> float:
    """Read a YOLO interval in seconds.

    The schedule used to count ticks, which made the real interval depend on how
    long the GPU was busy. Intervals are now wall-clock; the old "every N ticks"
    keys are still honoured so existing config files keep working.
    """
    interval_ms = vision.get(ms_key)
    if interval_ms is not None:
        return float(interval_ms) / 1000.0

    ticks = int(vision.get(legacy_ticks_key, _DEFAULT_YOLO_INTERVAL_TICKS))
    return ticks * _FRAME_INTERVAL_MS / 1000.0


def _fresh_dets(dets: list, produced_sec: float, now_sec: float) -> list:
    """Return the boxes only while they still describe the current scene."""
    if now_sec - produced_sec > _MAX_BOX_AGE_SEC:
        return []
    return dets


def load_robot_config(path: Path = _CONFIG_PATH) -> dict:
    """Load robot_config.json (fall back to defaults if missing)."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "llm": {"model_id": "Qwen/Qwen2.5-VL-3B-Instruct"},
        "vision": {"enable": True},
        "tts": {
            "enable": True,
            "engine": "sbv2",
            "max_chars": 240,
            "sbv2": {
                "device": "cuda",
                "model": "jvnv-F1-jp",
                "style": "Neutral",
                "pitch_scale": 1.10,
                "style_weight": 1.0,
                "intonation_scale": 0.95,
                "length": 0.95,
                "python": "venv_sbv2/Scripts/python.exe",
            },
            "voicevox": {
                "style_id": 3,
                "runtime_dir": "voicevox_runtime",
                "gentle_mimamori": True,
                "python": "venv_vv/Scripts/python.exe",
            },
            "qwen": {
                "variant": "custom_voice",
                "model_id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                "language": "Japanese",
                "speaker": "Ono_Anna",
            },
        },
    }


class RobotMainWindow(QMainWindow):
    """The robot's main window."""

    def __init__(self):
        super().__init__()
        self.config = load_robot_config()
        self._build_services()
        self._init_ui()
        self._init_vision_state()
        self._init_timer()
        self._start_warmup()

    # --- initialization -----------------------------------------------------

    def _build_services(self) -> None:
        llm_cfg = self.config.get("llm", {})
        # One model (Qwen2.5-VL 4bit, GPU) serves both chat and image.
        self.client = QwenVLClient(
            model_id=llm_cfg.get("model_id", "Qwen/Qwen2.5-VL-3B-Instruct"),
        )
        mem_cfg = self.config.get("memory", {})
        root = Path(__file__).parent
        self.memory = MemoryStore(
            state_path=root / mem_cfg.get("state_path", "robot_data/robot_state.json"),
            log_path=root / mem_cfg.get("log_path", "robot_data/memory.jsonl"),
        )
        self.bridge = PerceptionBridge()
        self._load_vision_settings()
        self._load_tts_settings(root)

    def _load_vision_settings(self) -> None:
        vis = self.config.get("vision", {})
        self._raw_yolo_interval_sec = _read_interval_sec(
            vis, "raw_yolo_interval_ms", "raw_yolo_every_ticks"
        )
        self._diff_yolo_interval_sec = _read_interval_sec(
            vis, "diff_yolo_interval_ms", "diff_yolo_every_ticks"
        )
        self._raw_yolo_conf = float(vis.get("raw_yolo_conf", 0.35))
        cap = vis.get("caption", {})
        self._caption_auto_enabled = bool(cap.get("auto_enabled", True))
        self._caption_motion_ratio = float(cap.get("motion_trigger_ratio", 0.06))
        self._caption_cooldown_sec = float(cap.get("cooldown_sec", 20.0))
        self._caption_prompt = cap.get("prompt", _DEFAULT_CAPTION_PROMPT)

    def _load_tts_settings(self, root: Path) -> None:
        tts_cfg = self.config.get("tts", {})
        self._tts_enabled_default = bool(tts_cfg.get("enable", True))
        self.tts = None
        self._tts_worker: Optional[TtsWorker] = None
        self._tts_ready = False
        self._tts_warming = False
        self._tts_synth_busy = False
        self._pending_speak: Optional[str] = None
        self._tts_sentence_queue: list[str] = []
        self._tts_queue_index = 0
        self._tts_queue_total = 0
        self._tts_sentence_ok = False
        self._tts_init_error: Optional[str] = None
        try:
            self.tts = build_tts_client(tts_cfg, root)
        except Exception as exc:
            self.tts = None
            self._tts_init_error = str(exc)

    def _init_ui(self) -> None:
        self.setWindowTitle("LogSense Robot - ロギー")
        self.setMinimumSize(1280, 720)
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.addWidget(self._build_vision_panel(), stretch=3)
        root.addWidget(self._build_robot_panel(), stretch=2)
        self.statusBar().showMessage(f"準備完了 (Lv{self.memory.state.level})")

    def _build_vision_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        controls = QHBoxLayout()
        self.start_button = QPushButton("開始")
        self.start_button.clicked.connect(self._on_start)
        controls.addWidget(self.start_button)
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.stop_button)
        self.look_button = QPushButton("今の様子を見て")
        self.look_button.clicked.connect(self._on_look_now)
        self.look_button.setEnabled(False)
        controls.addWidget(self.look_button)

        self.live_caption_check = QCheckBox("ライブ実況")
        self.live_caption_check.setToolTip("動きを検知したらロギーが自動で実況します")
        self.live_caption_check.setChecked(self._caption_auto_enabled)
        controls.addWidget(self.live_caption_check)
        controls.addWidget(QLabel("間隔:"))
        self.caption_interval_spin = QSpinBox()
        self.caption_interval_spin.setRange(
            _CAPTION_INTERVAL_MIN_SEC, _CAPTION_INTERVAL_MAX_SEC
        )
        self.caption_interval_spin.setValue(int(self._caption_cooldown_sec))
        self.caption_interval_spin.setSuffix(" 秒")
        controls.addWidget(self.caption_interval_spin)

        self.tts_check = QCheckBox("音声読み上げ")
        engine = str(self.config.get("tts", {}).get("engine", "sbv2"))
        self.tts_check.setToolTip(
            f"チャット返答と実況を読み上げます（engine={engine} / robot_v2_config.json）"
        )
        self.tts_check.setChecked(self._tts_enabled_default and self.tts is not None)
        self.tts_check.setEnabled(self.tts is not None)
        controls.addWidget(self.tts_check)
        self.tts_test_button = QPushButton("音声テスト")
        self.tts_test_button.setToolTip("短い定型文で読み上げを確認します")
        self.tts_test_button.setEnabled(False)
        self.tts_test_button.clicked.connect(self._on_tts_test)
        controls.addWidget(self.tts_test_button)

        controls.addStretch()
        layout.addLayout(controls)

        images = QHBoxLayout()
        self.original_widget = VideoDisplayWidget("元フレーム")
        images.addWidget(self.original_widget)
        self.difference_widget = DifferenceDisplayWidget()
        images.addWidget(self.difference_widget)
        layout.addLayout(images)

        self.stats_widget = StatsWidget()
        layout.addWidget(self.stats_widget)
        return panel

    def _build_robot_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        face_cfg = self.config.get("face", {})
        root = Path(__file__).parent
        self.face = FaceWidget(
            image_dir=root / face_cfg.get("image_dir", "robot_data/images"),
            expressions=face_cfg.get("expressions", {}),
        )
        layout.addWidget(self.face, stretch=2)
        self.chat = ChatPanel(self.client, context_provider=self._chat_context)
        self.chat.emotion_changed.connect(self._on_emotion)
        self.chat.exchange_done.connect(self._on_exchange_done)
        layout.addWidget(self.chat, stretch=3)
        return panel

    def _init_vision_state(self) -> None:
        self.processor: Optional[RealtimeVideoProcessor] = None
        self.subscriber_queue: Optional[queue.Queue] = None
        self.yolo_pipeline = None
        self._prev_bgr: Optional[np.ndarray] = None
        self._yolo_index = 0
        self._frame_number = 0
        # Stagger the two passes by half a period so they rarely land together.
        self._last_diff_yolo_sec = 0.0
        self._last_raw_yolo_sec = self._raw_yolo_interval_sec / 2
        self._current_frame: Optional[np.ndarray] = None
        self._raw_names: list[str] = []  # original-frame YOLO = "what is there"
        self._raw_dets: list = []  # same pass, kept for the boxes on the video
        self._raw_dets_sec = 0.0  # when those boxes were produced (for staleness)
        self._diff_dets: list = []  # cached YOLO detections on the diff (for boxes)
        self._diff_dets_sec = 0.0  # when those boxes were produced (for staleness)
        self._diff_pack: Optional[dict] = None  # this tick's diff, shared by all users
        self._last_motion = 0.0  # latest motion amount (0..1)
        self._last_caption = ""  # VLM = "what is happening"
        self._last_caption_time = 0.0
        self._caption_worker: Optional[CaptionWorker] = None
        # Telemetry: without it, "it feels slow" cannot be checked against numbers.
        self._tick_durations_ms: list[float] = []
        self._tick_starts_sec: list[float] = []
        self._last_stats_refresh_sec = 0.0

    def _init_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.setInterval(_FRAME_INTERVAL_MS)

    def _start_warmup(self) -> None:
        """Preload VL then TTS in the background to reduce first-response latency."""
        self.statusBar().showMessage("ロギーを起こしています…(モデル準備中)")
        self._warmup_worker = WarmupWorker(self.client)
        self._warmup_worker.done.connect(self._on_vl_warmup_done)
        self._warmup_worker.failed.connect(
            lambda msg: self.statusBar().showMessage(f"モデル準備に失敗: {msg}")
        )
        self._warmup_worker.start()

    def _on_vl_warmup_done(self) -> None:
        if self.tts is None:
            msg = f"準備完了 (Lv{self.memory.state.level})"
            if self._tts_init_error:
                msg += f" / TTS無効: {self._tts_init_error}"
            self.statusBar().showMessage(msg)
            return
        self._tts_warming = True
        self.statusBar().showMessage("ロギーを起こしています…(音声モデル準備中)")
        print("[tts] warmup start", flush=True)
        self._tts_warmup_worker = WarmupWorker(self.tts)
        self._tts_warmup_worker.done.connect(self._on_tts_warmup_done)
        self._tts_warmup_worker.failed.connect(self._on_tts_warmup_failed)
        self._tts_warmup_worker.start()

    def _on_tts_warmup_done(self) -> None:
        self._tts_warming = False
        self._tts_ready = True
        self.tts_test_button.setEnabled(True)
        print("[tts] warmup done", flush=True)
        self.statusBar().showMessage(f"準備完了 (Lv{self.memory.state.level}) / 音声OK")
        pending = self._pending_speak
        self._pending_speak = None
        if pending:
            self._speak(pending)

    def _on_tts_warmup_failed(self, message: str) -> None:
        self._tts_warming = False
        self._tts_ready = False
        self._pending_speak = None
        self.tts_check.setChecked(False)
        self.tts_check.setEnabled(False)
        self.tts_test_button.setEnabled(False)
        print(f"[tts] warmup failed: {message}", flush=True)
        self.statusBar().showMessage(
            f"準備完了 (Lv{self.memory.state.level}) / TTS失敗: {message}"
        )

    def _on_tts_test(self) -> None:
        self.tts_check.setChecked(True)
        self._speak("こんにちは。音声テストです。")

    # --- chat ---------------------------------------------------------------

    def _chat_context(self) -> tuple[Optional[str], Optional[str], Optional[bytes]]:
        """Called by ChatPanel on send.

        Returns (perception summary, memory summary, current frame as JPEG).
        The frame lets the model answer from the actual image; it is None while
        not watching, so chat stays text-only (fast) in that case.
        """
        image_bytes = (
            self._encode_for_vlm(self._current_frame)
            if self._current_frame is not None
            else None
        )
        return self._perception_summary(), self.memory.summary(), image_bytes

    def _perception_summary(self) -> str:
        """YOLO/diff facts then the VLM guess, in facts-then-guess order."""
        objects = ", ".join(sorted(set(self._raw_names))) if self._raw_names else "なし"
        motion = self._motion_label(self._last_motion)
        scene = self._last_caption or "（まだ詳しく見ていません）"
        return (
            f"【YOLO検出物体】{objects} / "
            f"【差分(動き)】{motion} / "
            f"【状況の推測】{scene}"
        )

    @staticmethod
    def _motion_label(ratio: float) -> str:
        if ratio >= 0.10:
            return "大きい"
        if ratio >= 0.02:
            return "あり"
        return "ほぼなし"

    def _on_emotion(self, emotion: Emotion) -> None:
        self.face.set_emotion(emotion)

    def _on_exchange_done(self, user_text: str, reply_text: str) -> None:
        self.memory.record_chat(user_text, reply_text)
        self.statusBar().showMessage(
            f"会話 {self.memory.state.chat_count}回 (Lv{self.memory.state.level})"
        )
        self._speak(reply_text)

    def _speak(self, text: str) -> None:
        """Split into sentences and speak them one-by-one (interrupt previous)."""
        if self.tts is None:
            self.statusBar().showMessage("音声なし（TTS未初期化）")
            print("[tts] skip: client is None", flush=True)
            return
        if not self.tts_check.isChecked():
            print("[tts] skip: checkbox off", flush=True)
            return
        if not self._tts_ready:
            self._pending_speak = text
            self.statusBar().showMessage("音声モデル準備中…完了後に読み上げます")
            print("[tts] queued until warmup done", flush=True)
            return
        chunks = split_sentences(text)
        if not chunks:
            print("[tts] skip: empty after split", flush=True)
            return
        self._pending_speak = None
        self._stop_tts_worker()
        self._tts_sentence_queue = chunks
        self._tts_queue_index = 0
        self._tts_queue_total = len(chunks)
        print(f"[tts] queue {self._tts_queue_total} sentence(s)", flush=True)
        self._start_next_tts_sentence()

    def _start_next_tts_sentence(self) -> None:
        if self.tts is None or not self._tts_sentence_queue:
            self._tts_sentence_queue = []
            self.statusBar().showMessage("読み上げ完了")
            return
        sentence = self._tts_sentence_queue.pop(0)
        self._tts_queue_index += 1
        self._tts_sentence_ok = False
        self.statusBar().showMessage(
            f"読み上げ中 ({self._tts_queue_index}/{self._tts_queue_total})…"
        )
        # Parented so Qt owns the thread (see the caption worker for why).
        worker = TtsWorker(self.tts, sentence, self)
        worker.synth_started.connect(self._on_tts_synth_started)
        worker.synth_finished.connect(self._on_tts_synth_finished)
        worker.failed.connect(self._on_tts_failed)
        worker.finished_ok.connect(self._on_tts_sentence_ok)
        worker.finished.connect(self._on_tts_thread_finished)
        worker.finished.connect(worker.deleteLater)  # freed after the thread ends
        self._tts_worker = worker
        worker.start()

    def _on_tts_sentence_ok(self) -> None:
        self._tts_sentence_ok = True

    def _on_tts_thread_finished(self) -> None:
        """Advance queue only after the worker thread has fully stopped."""
        if self._tts_worker is not None and not self._tts_worker.isFinished():
            return  # signal from an older utterance; the tracked one still runs
        self._tts_worker = None
        self._tts_synth_busy = False
        if self._tts_sentence_ok and self._tts_sentence_queue:
            self._start_next_tts_sentence()
        elif self._tts_sentence_ok:
            self.statusBar().showMessage("読み上げ完了")

    def _on_tts_failed(self, message: str) -> None:
        print(f"[tts] failed signal: {message}", flush=True)
        self._tts_sentence_ok = False
        self._tts_sentence_queue = []
        self.statusBar().showMessage(f"音声失敗: {message}")

    def _on_tts_synth_started(self) -> None:
        self._tts_synth_busy = True

    def _on_tts_synth_finished(self) -> None:
        self._tts_synth_busy = False

    def _stop_tts_worker(self) -> None:
        self._tts_sentence_queue = []
        self._tts_queue_index = 0
        self._tts_queue_total = 0
        self._tts_sentence_ok = False
        if self._tts_worker is None:
            return
        self._tts_worker.requestInterruption()
        # A synthesis longer than this keeps running; dropping the reference is
        # safe because the thread is parented and deletes itself when it ends.
        self._tts_worker.wait(_TTS_STOP_WAIT_MS)
        self._tts_worker = None
        self._tts_synth_busy = False

    def _tts_busy(self) -> bool:
        """True while TTS is warming up or synthesizing (not during playback)."""
        return bool(self._tts_warming or self._tts_synth_busy)

    # --- vision -------------------------------------------------------------

    def _on_start(self) -> None:
        try:
            self.processor = RealtimeVideoProcessor()
            self.processor.start()
            self.subscriber_queue = self.processor.frame_broadcaster.subscribe(
                maxsize=2
            )
            self._try_build_yolo()
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.look_button.setEnabled(True)
            self.timer.start()
            self.statusBar().showMessage("見守りを開始しました")
        except Exception as exc:
            self.statusBar().showMessage(f"開始エラー: {exc}")

    def _try_build_yolo(self) -> None:
        try:
            self.yolo_pipeline = build_streaming_yolo_pipeline()
        except Exception as exc:
            self.yolo_pipeline = None
            self.statusBar().showMessage(f"YOLO無効(差分のみ): {exc}")

    def _on_stop(self) -> None:
        self.timer.stop()
        if self.processor is not None:
            if self.subscriber_queue is not None:
                self.processor.frame_broadcaster.unsubscribe(self.subscriber_queue)
                self.subscriber_queue = None
            self.processor.stop()
        self._prev_bgr = None
        self._yolo_index = 0
        self._current_frame = None
        # Drop cached boxes so a restart never draws them over a new scene.
        self._raw_dets = []
        self._raw_dets_sec = 0.0
        self._diff_dets = []
        self._diff_dets_sec = 0.0
        self._diff_pack = None
        self._tick_durations_ms.clear()
        self._tick_starts_sec.clear()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.look_button.setEnabled(False)
        self.statusBar().showMessage("見守りを停止しました")

    def _gpu_busy(self) -> bool:
        """Whether chat, commentary, or TTS synthesis is using the GPU."""
        return (
            self._caption_worker is not None or self.chat.is_busy() or self._tts_busy()
        )

    def _on_tick(self) -> None:
        tick_start_sec = time.monotonic()
        frame = self._latest_frame()
        if frame is None:
            return
        self._current_frame = frame  # latest frame for chat / "look now"
        self._frame_number += 1
        now = datetime.now()
        # Always show the video, with the boxes from the last raw YOLO pass.
        shown = frame
        raw_dets = _fresh_dets(self._raw_dets, self._raw_dets_sec, tick_start_sec)
        if raw_dets:
            shown = draw_detections_on_bgr(frame, raw_dets)
        self.original_widget.update_frame(shown, now)
        # Diff display runs every frame on CPU (not affected by YOLO/LLM load).
        if self._prev_bgr is not None:
            # One diff per tick, reused by the display, the motion ratio and the
            # diff YOLO. Each of those used to recompute it from scratch.
            self._diff_pack = compute_difference_visual(self._prev_bgr, frame)
            self._update_diff_display(self._diff_pack["diff_bgr"], now, tick_start_sec)
            self._last_motion = self._motion_ratio(self._diff_pack["diff_gray"])
        # YOLO/VLM (GPU) pause only while the LLM runs = serialized; the diff
        # display above is unaffected.
        if not self._gpu_busy():
            # At most one YOLO pass per tick: two of them blow the frame budget.
            if not self._run_diff_yolo(frame, tick_start_sec):
                self._run_raw_yolo(frame, tick_start_sec)
            self._maybe_caption(frame, self._last_motion)  # (3) what is happening (VLM)
            self._apply_perception(self._raw_names, self._last_motion)
        self._prev_bgr = frame.copy()
        self._record_tick(tick_start_sec)

    def _record_tick(self, tick_start_sec: float) -> None:
        """Keep the FPS / tick-time readout fed from real measurements."""
        self._tick_durations_ms.append((time.monotonic() - tick_start_sec) * 1000.0)
        self._tick_starts_sec.append(tick_start_sec)

        if tick_start_sec - self._last_stats_refresh_sec < _STATS_REFRESH_SEC:
            return
        self._last_stats_refresh_sec = tick_start_sec

        elapsed_sec = self._tick_starts_sec[-1] - self._tick_starts_sec[0]
        fps = (len(self._tick_starts_sec) - 1) / elapsed_sec if elapsed_sec > 0 else 0.0
        self.stats_widget.update_stats(
            fps=fps,
            diff_ratio=self._last_motion,
            process_time=max(self._tick_durations_ms),  # worst tick in the window
            frame_number=self._frame_number,
        )
        self._tick_durations_ms.clear()
        self._tick_starts_sec.clear()

    def _latest_frame(self) -> Optional[np.ndarray]:
        """Pull only the most recent frame from the subscriber queue."""
        if self.subscriber_queue is None:
            return None
        frame = None
        while True:
            try:
                frame = self.subscriber_queue.get_nowait()
            except queue.Empty:
                break
        return frame

    def _update_diff_display(
        self, diff_bgr: np.ndarray, now: datetime, tick_start_sec: float
    ) -> None:
        """Show this tick's diff image, overlaying the cached detection boxes."""
        dets = _fresh_dets(self._diff_dets, self._diff_dets_sec, tick_start_sec)
        if dets:
            diff_bgr = draw_detections_on_bgr(diff_bgr, dets)
        self.difference_widget.update_frame(diff_bgr, now, status="success")

    def _run_diff_yolo(self, frame: np.ndarray, now_sec: float) -> bool:
        """YOLO on the diff image; cache detections for the display.

        Returns whether the inference actually ran, so the caller can keep the
        raw pass off this tick.
        """
        if self.yolo_pipeline is None or self._diff_pack is None:
            return False
        if now_sec - self._last_diff_yolo_sec < self._diff_yolo_interval_sec:
            return False
        self._last_diff_yolo_sec = now_sec
        try:
            out = self.yolo_pipeline.process(
                self._prev_bgr,
                frame,
                self._yolo_index,
                precomputed_diff=self._diff_pack,
                draw_overlay=False,  # only "detections" is read; the diff view
            )  # is drawn separately in _update_diff_display
            self._yolo_index += 1
            self._diff_dets = out["detections"]
            self._diff_dets_sec = now_sec
        except Exception:
            pass
        return True

    @staticmethod
    def _motion_ratio(diff_gray: np.ndarray) -> float:
        """Fraction of pixels changed between two frames (0..1)."""
        return float((diff_gray > _MOTION_PIXEL_THRESHOLD).mean())

    def _run_raw_yolo(self, frame: np.ndarray, now_sec: float) -> list[str]:
        """YOLO on the original frame. Return the latest detection names."""
        if self.yolo_pipeline is None:
            return self._raw_names
        if now_sec - self._last_raw_yolo_sec < self._raw_yolo_interval_sec:
            return self._raw_names
        self._last_raw_yolo_sec = now_sec
        try:
            dets = predict_frame(
                self.yolo_pipeline.model, frame, conf=self._raw_yolo_conf
            )
            self._raw_dets = dets
            self._raw_dets_sec = now_sec
            self._raw_names = [d.name for d in dets]
        except Exception:
            pass
        return self._raw_names

    def _maybe_caption(self, frame: np.ndarray, motion_ratio: float) -> None:
        """If live commentary is on and motion is large, request a caption."""
        if not self.live_caption_check.isChecked():
            return
        if motion_ratio >= self._caption_motion_ratio:
            self._request_caption(frame, forced=False)

    def _request_caption(self, frame: np.ndarray, forced: bool) -> None:
        """Start commentary in the background (skip if GPU busy or within interval)."""
        if self._gpu_busy():  # do not run in parallel with chat/commentary
            return
        now = time.monotonic()
        cooldown_sec = float(self.caption_interval_spin.value())
        if not forced and (now - self._last_caption_time) < cooldown_sec:
            return
        image_bytes = self._encode_for_vlm(frame)
        if image_bytes is None:
            return
        self._last_caption_time = now
        # Parented so Qt owns the thread: dropping the Python reference while the
        # thread still runs would destroy a running QThread (qFatal, hard crash).
        worker = CaptionWorker(self.client, image_bytes, self._caption_prompt, self)
        worker.caption_ready.connect(self._on_caption_ready)
        worker.failed.connect(self._on_caption_failed)
        worker.finished.connect(self._clear_caption_worker)
        worker.finished.connect(worker.deleteLater)  # freed after the thread ends
        self._caption_worker = worker
        worker.start()

    @staticmethod
    def _encode_for_vlm(frame: np.ndarray) -> Optional[bytes]:
        """Downscale (CPU) to longest side <= 768 and JPEG-encode for the VLM."""
        h, w = frame.shape[:2]
        side = max(h, w)
        if side > _MAX_VLM_IMAGE_SIDE:
            scale = _MAX_VLM_IMAGE_SIDE / side
            frame = cv2.resize(
                frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
            )
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return buf.tobytes() if ok else None

    def _on_look_now(self) -> None:
        if self._current_frame is not None:
            self._request_caption(self._current_frame, forced=True)
            self.statusBar().showMessage("今の様子を確認しています…")

    def _on_caption_ready(self, caption: str) -> None:
        self._last_caption = caption
        objects = ", ".join(sorted(set(self._raw_names))) if self._raw_names else "なし"
        motion = self._motion_label(self._last_motion)
        # Display: facts (YOLO/diff) then guess. Speak: caption only (short).
        note = f"検出: {objects} / 動き: {motion} → {caption}"
        self.chat.add_robot_note(note)
        self.statusBar().showMessage("様子を見ました")
        self._speak(caption)

    def _on_caption_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"様子の確認に失敗: {message}")

    def _clear_caption_worker(self) -> None:
        self._caption_worker = None

    def _apply_perception(self, names: list[str], motion_ratio: float) -> None:
        """Reflect detections into expression and memory (override face only on event)."""
        perception = self.bridge.update(names, motion_ratio)
        new_objects = self.memory.record_objects(names)
        if new_objects:
            self.statusBar().showMessage(
                f"はじめて見た: {', '.join(new_objects)} (Lv{self.memory.state.level})"
            )
        if perception.to_event() is not None:
            self.face.set_emotion(decide(perception=perception))

    def closeEvent(self, event) -> None:
        self._stop_tts_worker()
        self._on_stop()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = RobotMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
