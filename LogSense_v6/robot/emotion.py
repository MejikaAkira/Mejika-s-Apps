#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robot facial expressions (4 kinds) and the logic that picks one from inputs.

The expression is decided from two sources:
  1. A tag the LLM appends to its reply (e.g. "[emotion:happy]")
  2. A perception event (e.g. noticed a new object) -- this overrides the tag.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Emotion(str, Enum):
    """The robot's 4 expressions. Values are the lowercase keys used in tags/logs."""

    NORMAL = "normal"  # idle / default
    NOTICED = "noticed"  # noticed a new object
    HAPPY = "happy"  # praised / enjoyable chat
    WORRIED = "worried"  # error / cannot answer / no reaction for a while

    @classmethod
    def from_tag(cls, tag: Optional[str]) -> Optional["Emotion"]:
        """Map a string tag (case-insensitive, with aliases) to Emotion, or None."""
        if not tag:
            return None
        key = tag.strip().lower()
        aliases = {
            "joy": cls.HAPPY,
            "neutral": cls.NORMAL,
            "sad": cls.WORRIED,
            "anger": cls.WORRIED,
            "angry": cls.WORRIED,
            "notice": cls.NOTICED,
            "surprise": cls.NOTICED,
        }
        for member in cls:
            if member.value == key:
                return member
        return aliases.get(key)


# How perception events map to an expression (priority decided in to_event).
_PERCEPTION_PRIORITY = {
    "new_object": Emotion.NOTICED,
    "error_burst": Emotion.WORRIED,
    "idle_silence": Emotion.WORRIED,
}


@dataclass
class Perception:
    """Perception badge produced by perception_bridge once per tick."""

    detected_names: tuple[str, ...] = ()
    diff_ratio: float = 0.0
    new_object: bool = False
    error_burst: bool = False
    idle_silence: bool = False

    def to_event(self) -> Optional[str]:
        """Return the highest-priority perception event name (or None)."""
        for event in ("error_burst", "new_object", "idle_silence"):
            if getattr(self, event):
                return event
        return None


def decide(
    llm_tag: Optional[str] = None,
    perception: Optional[Perception] = None,
    default: Emotion = Emotion.NORMAL,
) -> Emotion:
    """Decide the final expression from LLM tag and perception (event wins)."""
    if perception is not None:
        event = perception.to_event()
        if event is not None:
            return _PERCEPTION_PRIORITY[event]
    from_llm = Emotion.from_tag(llm_tag)
    if from_llm is not None:
        return from_llm
    return default
