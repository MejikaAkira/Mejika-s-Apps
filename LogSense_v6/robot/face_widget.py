#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Widget that shows the robot's face as a character image.

Switches between per-expression images (normal / noticed / happy / worried).
The Emotion -> filename mapping is passed in via `expressions`. Images are
static (no animation). Falls back to the normal face if an image is missing.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from robot.emotion import Emotion

_BG_COLOR = QColor(28, 32, 44)


class FaceWidget(QWidget):
    """The robot's face shown as a character image (static)."""

    def __init__(self, image_dir: Path, expressions: dict[str, str], parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.image_dir = Path(image_dir)
        self._frames = self._load_frames(expressions)
        self._emotion = Emotion.NORMAL

    def _load_frames(
        self, expressions: dict[str, str]
    ) -> dict[Emotion, QPixmap | None]:
        """Load images per the expressions mapping (emotion value -> filename)."""
        frames: dict[Emotion, QPixmap | None] = {}
        for emo in Emotion:
            filename = expressions.get(emo.value)
            pixmap = QPixmap(str(self.image_dir / filename)) if filename else None
            frames[emo] = pixmap if (pixmap and not pixmap.isNull()) else None
        return frames

    def set_emotion(self, emotion: Emotion) -> None:
        if emotion != self._emotion:
            self._emotion = emotion
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), _BG_COLOR)
        pixmap = self._frames.get(self._emotion) or self._frames.get(Emotion.NORMAL)
        if pixmap and not pixmap.isNull():
            self._draw_pixmap(painter, pixmap)

    def _draw_pixmap(self, painter: QPainter, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


# Default mapping for the standalone demo (same as robot_config.json).
_DEMO_EXPRESSIONS = {
    "normal": "dog.png",
    "noticed": "notice.png",
    "happy": "smile.png",
    "worried": "worry.png",
}


def _demo() -> None:
    """Standalone launch to eyeball the 4 expressions."""
    import sys

    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout
    from PyQt6.QtWidgets import QWidget as QW

    app = QApplication(sys.argv)
    root = QW()
    root.setWindowTitle("FaceWidget demo")
    layout = QVBoxLayout(root)
    image_dir = Path(__file__).resolve().parent.parent / "robot_data" / "images"
    face = FaceWidget(image_dir, _DEMO_EXPRESSIONS)
    layout.addWidget(face)

    buttons = QHBoxLayout()
    # Button captions stay Japanese (user-facing UI).
    for label, emo in [
        ("普通", Emotion.NORMAL),
        ("気づいた", Emotion.NOTICED),
        ("うれしい", Emotion.HAPPY),
        ("困った", Emotion.WORRIED),
    ]:
        btn = QPushButton(label)
        btn.clicked.connect(lambda _checked, e=emo: face.set_emotion(e))
        buttons.addWidget(btn)
    layout.addLayout(buttons)

    root.resize(360, 460)
    root.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
