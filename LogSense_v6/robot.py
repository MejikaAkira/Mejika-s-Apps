#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LogSense Robot - GUI for the watch robot "ロビ".

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
from robot.tts_client import TtsClient, build_tts_client
from robot.tts_worker import TtsWorker

_CONFIG_PATH = Path(__file__).parent / "robot_config.json"
_FRAME_INTERVAL_MS = 33  # about 30 FPS
_MOTION_PIXEL_THRESHOLD = 25  # treat a pixel diff above this as "changed"
_CAPTION_INTERVAL_MIN_SEC = 3  # min live-commentary interval (spinbox lower bound)
_CAPTION_INTERVAL_MAX_SEC = 300  # max live-commentary interval (spinbox upper bound)
_MAX_VLM_IMAGE_SIDE = 768  # downscale to this longest side before the VLM
# User-facing caption prompt (Japanese on purpose).
_DEFAULT_CAPTION_PROMPT = "この画像に写っているものが何か、それは何をしているか、日本語で一文だけで説明してください。"


def load_robot_config(path: Path = _CONFIG_PATH) -> dict:
    """Load robot_config.json (fall back to defaults if missing)."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "llm": {"model_id": "Qwen/Qwen2.5-VL-3B-Instruct"},
        "vision": {"enable": True},
        "tts": {
            "enable": True,
            "variant": "custom_voice",
            "model_id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
            "language": "Japanese",
            "speaker": "Ono_Anna",
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
        self._raw_yolo_every_ticks = int(vis.get("raw_yolo_every_ticks", 15))
        self._diff_every_ticks = int(vis.get("diff_yolo_every_ticks", 15))
        self._raw_yolo_conf = float(vis.get("raw_yolo_conf", 0.35))
        cap = vis.get("caption", {})
        self._caption_auto_enabled = bool(cap.get("auto_enabled", True))
        self._caption_motion_ratio = float(cap.get("motion_trigger_ratio", 0.06))
        self._caption_cooldown_sec = float(cap.get("cooldown_sec", 20.0))
        self._caption_prompt = cap.get("prompt", _DEFAULT_CAPTION_PROMPT)

    def _load_tts_settings(self, root: Path) -> None:
        tts_cfg = self.config.get("tts", {})
        self._tts_enabled_default = bool(tts_cfg.get("enable", True))
        self.tts: Optional[TtsClient] = None
        self._tts_worker: Optional[TtsWorker] = None
        self._tts_ready = False
        self._tts_synth_busy = False
        self._tts_init_error: Optional[str] = None
        try:
            self.tts = build_tts_client(tts_cfg, root)
        except Exception as exc:
            self.tts = None
            self._tts_init_error = str(exc)

    def _init_ui(self) -> None:
        self.setWindowTitle("LogSense Robot - ロビ")
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
        self.live_caption_check.setToolTip("動きを検知したらロビが自動で実況します")
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
        self.tts_check.setToolTip("チャット返答と実況を Qwen3-TTS で読み上げます")
        self.tts_check.setChecked(self._tts_enabled_default and self.tts is not None)
        self.tts_check.setEnabled(self.tts is not None)
        controls.addWidget(self.tts_check)

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
        self._tick_count = 0
        self._current_frame: Optional[np.ndarray] = None
        self._raw_names: list[str] = []  # original-frame YOLO = "what is there"
        self._diff_dets: list = []  # cached YOLO detections on the diff (for boxes)
        self._last_motion = 0.0  # latest motion amount (0..1)
        self._last_caption = ""  # VLM = "what is happening"
        self._last_caption_time = 0.0
        self._caption_worker: Optional[CaptionWorker] = None

    def _init_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.setInterval(_FRAME_INTERVAL_MS)

    def _start_warmup(self) -> None:
        """Preload VL then TTS in the background to reduce first-response latency."""
        self.statusBar().showMessage("ロビを起こしています…(モデル準備中)")
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
        self.statusBar().showMessage("ロビを起こしています…(音声モデル準備中)")
        self._tts_warmup_worker = WarmupWorker(self.tts)
        self._tts_warmup_worker.done.connect(self._on_tts_warmup_done)
        self._tts_warmup_worker.failed.connect(self._on_tts_warmup_failed)
        self._tts_warmup_worker.start()

    def _on_tts_warmup_done(self) -> None:
        self._tts_ready = True
        self.statusBar().showMessage(f"準備完了 (Lv{self.memory.state.level}) / 音声OK")

    def _on_tts_warmup_failed(self, message: str) -> None:
        self._tts_ready = False
        self.tts_check.setChecked(False)
        self.tts_check.setEnabled(False)
        self.statusBar().showMessage(
            f"準備完了 (Lv{self.memory.state.level}) / TTS失敗: {message}"
        )

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
        """Queue TTS for chat reply or live commentary (interrupt previous)."""
        if not self.tts_check.isChecked() or self.tts is None or not self._tts_ready:
            return
        self._stop_tts_worker()
        worker = TtsWorker(self.tts, text)
        worker.synth_started.connect(self._on_tts_synth_started)
        worker.synth_finished.connect(self._on_tts_synth_finished)
        worker.failed.connect(
            lambda msg: self.statusBar().showMessage(f"音声失敗: {msg}")
        )
        worker.finished.connect(self._clear_tts_worker)
        self._tts_worker = worker
        worker.start()

    def _on_tts_synth_started(self) -> None:
        self._tts_synth_busy = True

    def _on_tts_synth_finished(self) -> None:
        self._tts_synth_busy = False

    def _stop_tts_worker(self) -> None:
        if self._tts_worker is None:
            return
        self._tts_worker.requestInterruption()
        self._tts_worker.wait(2000)
        self._tts_worker = None
        self._tts_synth_busy = False

    def _clear_tts_worker(self) -> None:
        self._tts_worker = None
        self._tts_synth_busy = False

    def _tts_busy(self) -> bool:
        """True only while GPU synthesis runs (not during speaker playback)."""
        return bool(getattr(self, "_tts_synth_busy", False))

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
        frame = self._latest_frame()
        if frame is None:
            return
        self._current_frame = frame  # latest frame for chat / "look now"
        now = datetime.now()
        self.original_widget.update_frame(frame, now)  # always show the video
        # Diff display runs every frame on CPU (not affected by YOLO/LLM load).
        if self._prev_bgr is not None:
            self._update_diff_display(self._prev_bgr, frame, now)
            self._last_motion = self._motion_ratio(self._prev_bgr, frame)
        # YOLO/VLM (GPU) pause only while the LLM runs = serialized; the diff
        # display above is unaffected.
        if not self._gpu_busy():
            self._tick_count += 1
            self._run_diff_yolo(frame)  # throttled: update diff detection boxes (GPU)
            names = self._run_raw_yolo(frame)  # (1) what is there (original frame)
            self._maybe_caption(frame, self._last_motion)  # (3) what is happening (VLM)
            self._apply_perception(names, self._last_motion)
        self._prev_bgr = frame.copy()

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
        self, prev: np.ndarray, curr: np.ndarray, now: datetime
    ) -> None:
        """Draw the diff image every frame (CPU only, lightweight); overlay cached boxes."""
        pack = compute_difference_visual(prev, curr)  # defaults = light CPU path
        diff_bgr = pack["diff_bgr"]
        if self._diff_dets:
            diff_bgr = draw_detections_on_bgr(diff_bgr, self._diff_dets)
        self.difference_widget.update_frame(diff_bgr, now, status="success")

    def _run_diff_yolo(self, frame: np.ndarray) -> None:
        """YOLO on the diff image (throttled); cache detections for the display."""
        if self.yolo_pipeline is None:
            return
        if self._tick_count % self._diff_every_ticks != 0:
            return
        try:
            out = self.yolo_pipeline.process(self._prev_bgr, frame, self._yolo_index)
            self._yolo_index += 1
            self._diff_dets = out["detections"]
        except Exception:
            pass

    @staticmethod
    def _motion_ratio(prev: np.ndarray, curr: np.ndarray) -> float:
        """Fraction of pixels changed between two frames (0..1)."""
        diff = cv2.absdiff(prev, curr)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        return float((gray > _MOTION_PIXEL_THRESHOLD).mean())

    def _run_raw_yolo(self, frame: np.ndarray) -> list[str]:
        """YOLO on the original frame (throttled). Return the latest detection names."""
        if self.yolo_pipeline is None:
            return self._raw_names
        if self._tick_count % self._raw_yolo_every_ticks != 0:
            return self._raw_names
        try:
            dets = predict_frame(
                self.yolo_pipeline.model, frame, conf=self._raw_yolo_conf
            )
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
        worker = CaptionWorker(self.client, image_bytes, self._caption_prompt)
        worker.caption_ready.connect(self._on_caption_ready)
        worker.failed.connect(self._on_caption_failed)
        worker.finished.connect(self._clear_caption_worker)
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
        # Commentary order: facts (YOLO/diff) -> guess (VLM).
        note = f"検出: {objects} / 動き: {motion} → {caption}"
        self.chat.add_robot_note(note)
        self.statusBar().showMessage("様子を見ました")
        self._speak(note)

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
