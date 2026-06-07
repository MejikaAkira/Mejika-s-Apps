#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robot memory and growth.

Appends chats and observations to memory.jsonl and keeps exp / level / seen
objects in robot_state.json. Loaded at startup; produces a summary injected
into the persona to give a sense of "growing".
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Experience awarded per event (avoid magic numbers).
_EXP_PER_CHAT = 5
_EXP_PER_NEW_OBJECT = 20
_EXP_PER_LEVEL = 100  # exp coefficient per level step


def _level_from_exp(exp: int) -> int:
    """Compute level from exp (gentle square-root curve)."""
    return int(math.isqrt(max(0, exp) // _EXP_PER_LEVEL)) + 1


@dataclass
class RobotState:
    """Persisted growth state of the robot."""

    exp: int = 0
    known_objects: set[str] = field(default_factory=set)
    chat_count: int = 0

    @property
    def level(self) -> int:
        return _level_from_exp(self.exp)

    def to_dict(self) -> dict:
        return {
            "exp": self.exp,
            "known_objects": sorted(self.known_objects),
            "chat_count": self.chat_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RobotState":
        return cls(
            exp=int(data.get("exp", 0)),
            known_objects=set(data.get("known_objects", [])),
            chat_count=int(data.get("chat_count", 0)),
        )


class MemoryStore:
    """Persists the growth state and appends the event log (jsonl)."""

    def __init__(self, state_path: Path, log_path: Path):
        self.state_path = Path(state_path)
        self.log_path = Path(log_path)
        self.state = self._load_state()

    def _load_state(self) -> RobotState:
        if self.state_path.is_file():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                return RobotState.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass
        return RobotState()

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_log(self, kind: str, payload: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **payload,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def record_chat(self, user_text: str, reply_text: str) -> None:
        """Record a chat exchange and add experience."""
        self.state.chat_count += 1
        self.state.exp += _EXP_PER_CHAT
        self._append_log("chat", {"user": user_text, "reply": reply_text})
        self._save_state()

    def record_objects(self, names: list[str]) -> list[str]:
        """Record observed objects. Return the list of first-seen names."""
        new_names = [n for n in names if n and n not in self.state.known_objects]
        if new_names:
            self.state.known_objects.update(new_names)
            self.state.exp += _EXP_PER_NEW_OBJECT * len(new_names)
            self._append_log("observe", {"new_objects": new_names})
            self._save_state()
        return new_names

    def summary(self) -> str:
        """Growth summary (Japanese) injected into the persona."""
        objects = sorted(self.state.known_objects)
        seen = "、".join(objects[:12]) if objects else "まだ何も覚えていない"
        return (
            f"あなたは今レベル{self.state.level}。"
            f"これまで{self.state.chat_count}回会話しました。"
            f"今まで見て覚えたもの: {seen}。"
        )
