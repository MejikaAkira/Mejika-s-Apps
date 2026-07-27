#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background TTS worker: synthesize on GPU then play audio off the GUI thread.

On Windows, playback uses winsound (reliable with Qt). sounddevice is fallback.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from robot.tts_text import prepare_speak_text

_LAST_WAV = Path(__file__).resolve().parent.parent / "robot_data" / "tts_last.wav"
_DEBUG_LOG = Path(__file__).resolve().parent.parent / "robot_data" / "tts_debug.log"


def _log(message: str) -> None:
    line = f"[tts] {message}"
    print(line, flush=True)
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class TtsWorker(QThread):
    """One utterance: synthesize then play. Interruptible via requestInterruption."""

    started_speak = pyqtSignal(str)
    synth_started = pyqtSignal()
    synth_finished = pyqtSignal()  # GPU free; playback may still run
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, client, text: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._text = text

    def run(self) -> None:
        speak = prepare_speak_text(self._text)
        if not speak:
            _log("skip empty text")
            self.finished_ok.emit()
            return
        try:
            _log(f"synthesize: {speak[:80]}")
            self.started_speak.emit(speak)
            self.synth_started.emit()
            wave, sample_rate = self._client.synthesize(speak)
            self.synth_finished.emit()
            if self.isInterruptionRequested():
                _log("interrupted after synth")
                return
            peak = float(np.max(np.abs(wave))) if wave.size else 0.0
            _log(f"wave samples={wave.size} sr={sample_rate} peak={peak:.3f}")
            wav_path = self._write_wav(wave, sample_rate)
            _log(f"wrote {wav_path}")
            self._play_file(wav_path, wave, sample_rate)
            _log("play done")
            self.finished_ok.emit()
        except Exception as exc:
            self.synth_finished.emit()
            _log(f"failed: {exc}")
            self.failed.emit(str(exc))

    @staticmethod
    def _write_wav(wave: np.ndarray, sample_rate: int) -> Path:
        import soundfile as sf

        _LAST_WAV.parent.mkdir(parents=True, exist_ok=True)
        # PCM_16 is required for reliable winsound playback on Windows.
        sf.write(str(_LAST_WAV), wave, sample_rate, subtype="PCM_16")
        return _LAST_WAV

    def _play_file(self, wav_path: Path, wave: np.ndarray, sample_rate: int) -> None:
        if sys.platform.startswith("win"):
            self._play_winsound(wav_path)
            return
        self._play_sounddevice(wave, sample_rate)

    def _play_winsound(self, wav_path: Path) -> None:
        import winsound

        # Synchronous play; check interruption only before/after (API is blocking).
        if self.isInterruptionRequested():
            return
        _log(f"winsound play: {wav_path}")
        winsound.PlaySound(
            str(wav_path),
            winsound.SND_FILENAME | winsound.SND_NODEFAULT,
        )

    def _play_sounddevice(self, wave: np.ndarray, sample_rate: int) -> None:
        import sounddevice as sd

        _log("sounddevice play")
        sd.play(wave, sample_rate, blocking=False)
        duration_sec = float(len(wave)) / float(sample_rate)
        deadline = time.monotonic() + duration_sec + 0.25
        while time.monotonic() < deadline:
            if self.isInterruptionRequested():
                sd.stop()
                return
            time.sleep(0.05)
        sd.wait()
