#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background TTS worker: synthesize on GPU then play audio off the GUI thread.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from robot.tts_client import TtsClient, prepare_speak_text


class TtsWorker(QThread):
    """One utterance: synthesize then play. Interruptible via requestInterruption."""

    started_speak = pyqtSignal(str)
    synth_started = pyqtSignal()
    synth_finished = pyqtSignal()  # GPU free; playback may still run
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, client: TtsClient, text: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._text = text

    def run(self) -> None:
        speak = prepare_speak_text(self._text)
        if not speak:
            self.finished_ok.emit()
            return
        try:
            self.started_speak.emit(speak)
            self.synth_started.emit()
            wave, sample_rate = self._client.synthesize(speak)
            self.synth_finished.emit()
            if self.isInterruptionRequested():
                return
            self._play(wave, sample_rate)
            self.finished_ok.emit()
        except Exception as exc:
            self.synth_finished.emit()
            self.failed.emit(str(exc))

    def _play(self, wave: np.ndarray, sample_rate: int) -> None:
        import sounddevice as sd

        chunk = max(sample_rate // 4, 1)
        offset = 0
        while offset < len(wave):
            if self.isInterruptionRequested():
                sd.stop()
                return
            end = min(offset + chunk, len(wave))
            sd.play(wave[offset:end], sample_rate, blocking=True)
            offset = end
