#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chat panel widget. Sends input to the LLM and streams the reply.

The LLM call runs in a QThread (LlmWorker) so the UI never freezes. On
completion it extracts the emotion tag (emotion_changed) and the body
(exchange_done). The client is duck-typed (needs chat_stream()).
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from robot.emotion import Emotion
from robot.llm_client import ChatTurn, split_emotion_tag

# Context provider: returns (perception_summary, memory_summary, image_bytes).
# image_bytes is the current camera frame (JPEG) or None when not watching.
ContextProvider = Callable[[], tuple[Optional[str], Optional[str], Optional[bytes]]]


class LlmWorker(QThread):
    """Worker that streams one round of the LLM reply."""

    token_received = pyqtSignal(str)
    failed = pyqtSignal(str)
    completed = pyqtSignal(str)  # full text (including emotion tag)

    def __init__(
        self,
        client,
        user_text: str,
        history: list[ChatTurn],
        perception_summary: Optional[str],
        memory_summary: Optional[str],
        image_bytes: Optional[bytes] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._client = client
        self._user_text = user_text
        self._history = history
        self._perception_summary = perception_summary
        self._memory_summary = memory_summary
        self._image_bytes = image_bytes

    def run(self) -> None:
        chunks: list[str] = []
        try:
            for piece in self._client.chat_stream(
                self._user_text,
                self._history,
                self._perception_summary,
                self._memory_summary,
                self._image_bytes,
            ):
                chunks.append(piece)
                self.token_received.emit(piece)
            self.completed.emit("".join(chunks))
        except Exception as exc:  # network / model not loaded / etc.
            self.failed.emit(str(exc))


class ChatPanel(QWidget):
    """Chat history view and input box."""

    emotion_changed = pyqtSignal(object)  # Emotion
    exchange_done = pyqtSignal(str, str)  # (user_text, reply_text)

    def __init__(
        self,
        client,
        context_provider: Optional[ContextProvider] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._client = client
        self._context_provider = context_provider
        self._history: list[ChatTurn] = []
        self._worker: Optional[LlmWorker] = None
        self._pending_user_text = ""
        self._reply_anchor = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        layout.addWidget(self.history_view)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("ロビに話しかける…")
        self.input_edit.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_edit)
        self.send_button = QPushButton("送信")
        self.send_button.clicked.connect(self._on_send)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

    def _on_send(self) -> None:
        user_text = self.input_edit.text().strip()
        if not user_text or self._worker is not None:
            return
        self.input_edit.clear()
        self._set_busy(True)
        self._append_line(f"あなた: {user_text}")
        self.history_view.append("ロビ: ")
        self._pending_user_text = user_text

        perception_summary, memory_summary, image_bytes = (
            self._context_provider() if self._context_provider else (None, None, None)
        )
        self._worker = LlmWorker(
            self._client,
            user_text,
            list(self._history),
            perception_summary,
            memory_summary,
            image_bytes,
        )
        self._worker.token_received.connect(self._on_token)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_token(self, piece: str) -> None:
        # The emotion tag is stripped at the end, so append tokens as-is here.
        self.history_view.moveCursor(self.history_view.textCursor().MoveOperation.End)
        self.history_view.insertPlainText(piece)

    def _on_completed(self, full_text: str) -> None:
        reply, emotion_tag = split_emotion_tag(full_text)
        self._rewrite_last_reply(reply)
        self._history.append(ChatTurn("user", self._pending_user_text))
        self._history.append(ChatTurn("assistant", reply))
        emotion = Emotion.from_tag(emotion_tag)
        if emotion is not None:
            self.emotion_changed.emit(emotion)
        self.exchange_done.emit(self._pending_user_text, reply)
        self._finish_worker()

    def _on_failed(self, message: str) -> None:
        self._rewrite_last_reply(f"(うまく話せませんでした: {message})")
        self.emotion_changed.emit(Emotion.WORRIED)
        self._finish_worker()

    def _rewrite_last_reply(self, reply: str) -> None:
        """Replace the streamed (tag-included) body with the cleaned body."""
        text = self.history_view.toPlainText()
        idx = text.rfind("ロビ: ")
        if idx >= 0:
            cleaned = text[:idx] + f"ロビ: {reply}"
            self.history_view.setPlainText(cleaned)

    def _finish_worker(self) -> None:
        self._set_busy(False)
        self._worker = None

    def is_busy(self) -> bool:
        """Whether an LLM reply is being generated (used for GPU serialization)."""
        return self._worker is not None

    def add_robot_note(self, text: str) -> None:
        """Show a proactive robot line (e.g. live commentary) without the LLM."""
        self.history_view.append(f"ロビ（実況）: {text}")

    def _append_line(self, line: str) -> None:
        self.history_view.append(line)

    def _set_busy(self, busy: bool) -> None:
        self.input_edit.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
