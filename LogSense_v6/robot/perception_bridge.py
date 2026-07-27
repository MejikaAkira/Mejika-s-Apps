#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge that turns YOLO detections and motion into the robot's "perception"
(Qt-independent).

Per tick it takes the detected names and diff_ratio and produces:
  - a Perception (new object / idle silence) used to pick the expression
  - a short Japanese summary text passed to the LLM
It keeps the state needed to detect new objects and idle silence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from robot.emotion import Perception

# Consecutive empty ticks before we treat it as "idle silence".
_IDLE_TICKS_FOR_SILENCE = 90  # about 3 seconds at ~30 FPS


@dataclass
class PerceptionBridge:
    """Holds detection history and produces perception events and summaries."""

    _seen_names: set[str] = field(default_factory=set)
    _idle_ticks: int = 0

    def update(self, detected_names: list[str], diff_ratio: float) -> Perception:
        """Build a Perception from one tick of detections."""
        names = tuple(n for n in detected_names if n)
        new_object = any(n not in self._seen_names for n in names)
        self._seen_names.update(names)

        if names:
            self._idle_ticks = 0
        else:
            self._idle_ticks += 1
        idle_silence = self._idle_ticks >= _IDLE_TICKS_FOR_SILENCE

        return Perception(
            detected_names=names,
            diff_ratio=diff_ratio,
            new_object=new_object,
            idle_silence=idle_silence,
        )

    @staticmethod
    def summary_text(detected_names: list[str]) -> str:
        """Summarize detected names into one Japanese sentence (LLM-facing)."""
        names = [n for n in detected_names if n]
        if not names:
            return "今は特に動くものは見えていません。"
        counts = Counter(names)
        parts = [f"{name}を{count}つ" for name, count in counts.items()]
        return "、".join(parts) + "見ています。"
