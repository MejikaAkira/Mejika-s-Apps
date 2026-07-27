#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background workers that run the LLM/VLM off the GUI thread.

The client is duck-typed: it only needs warmup() and describe_image(bytes, str).
Images are JPEG-encoded byte strings.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class WarmupWorker(QThread):
    """Preload the model into VRAM at startup so the first call is not cold."""

    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        try:
            self._client.warmup()
            self.done.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class CaptionWorker(QThread):
    """Get a scene caption for a single image."""

    caption_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, client, image_bytes: bytes, prompt: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._image_bytes = image_bytes
        self._prompt = prompt

    def run(self) -> None:
        try:
            caption = self._client.describe_image(self._image_bytes, self._prompt)
            self.caption_ready.emit(caption)
        except Exception as exc:
            self.failed.emit(str(exc))
