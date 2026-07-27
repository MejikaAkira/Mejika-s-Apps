#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Ollama chat client (Qt-independent) plus shared persona/helpers.

Holds the robot persona as the system prompt and makes the model append an
emotion tag "[emotion:normal|happy|worried|noticed]" at the end of its reply.
The caller streams tokens and extracts the tag at the end to drive the face.

NOTE: robot.py now uses QwenVLClient (transformers) instead of OllamaClient,
but this module still provides the shared _DEFAULT_PERSONA, ChatTurn and
split_emotion_tag used by the Qwen client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Optional

import ollama

_EMOTION_TAG_RE = re.compile(r"\[emotion:\s*([a-zA-Z]+)\s*\]")

# User-facing persona (kept in Japanese on purpose: the robot speaks Japanese).
_DEFAULT_PERSONA = (
    "あなたは『ロギー』という名前の小さな見守りロボットです。"
    "ミニドラえもんのように好奇心旺盛で前向き、ユーザーの相棒として成長していきます。"
    "返答は日本語で簡潔に。専門用語は避け、やさしく話します。"
    "カメラの様子を話すときは、まず【YOLO検出物体】と【差分(動き)】の事実を"
    "そのまま伝え、その後に『何が起きていそうか』を推測として付け足してください。"
    "返答の一番最後に、その時の気持ちを必ず1つだけ "
    "[emotion:normal] [emotion:happy] [emotion:worried] [emotion:noticed] "
    "のいずれかで付けてください。"
)


@dataclass
class ChatTurn:
    """One chat turn. role is 'user' or 'assistant'."""

    role: str
    content: str


@dataclass
class OllamaClient:
    """Thin wrapper around the Ollama chat API."""

    model: str = "gemma4:e2b"  # chat model (lightweight text LLM)
    vision_model: Optional[str] = None  # image model; falls back to model
    persona: str = _DEFAULT_PERSONA
    host: Optional[str] = None
    keep_alive: str = "30m"  # keep model resident in VRAM to avoid cold reloads
    _client: ollama.Client = field(init=False)

    def __post_init__(self) -> None:
        self._client = ollama.Client(host=self.host) if self.host else ollama.Client()

    def _vision_model(self) -> str:
        return self.vision_model or self.model

    def warmup(self) -> None:
        """Preload chat and vision models into VRAM (pay the cold load early)."""
        models = [self.model]
        if self._vision_model() != self.model:
            models.append(self._vision_model())
        for name in models:
            self._client.chat(
                model=name,
                messages=[{"role": "user", "content": "hi"}],
                keep_alive=self.keep_alive,
                options={"num_predict": 1},
            )

    def _build_messages(
        self,
        user_text: str,
        history: list[ChatTurn],
        perception_summary: Optional[str],
        memory_summary: Optional[str],
    ) -> list[dict[str, str]]:
        system = self.persona
        if memory_summary:
            system += f"\n\n【これまでの記憶】\n{memory_summary}"
        if perception_summary:
            system += f"\n\n【今カメラで見えているもの】\n{perception_summary}"
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t.role, "content": t.content} for t in history]
        messages.append({"role": "user", "content": user_text})
        return messages

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        """Send one image to the vision model and get a description (no stream)."""
        response = self._client.chat(
            model=self._vision_model(),
            messages=[{"role": "user", "content": prompt, "images": [image_bytes]}],
            stream=False,
            keep_alive=self.keep_alive,
        )
        return response.get("message", {}).get("content", "").strip()

    def chat_stream(
        self,
        user_text: str,
        history: Optional[list[ChatTurn]] = None,
        perception_summary: Optional[str] = None,
        memory_summary: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> Iterator[str]:
        """Yield reply tokens one by one (the emotion tag is included as-is).

        When image_bytes is given, it is attached to the user turn so the model
        can answer from the actual frame (kept for interface parity with the
        Qwen client).
        """
        messages = self._build_messages(
            user_text, history or [], perception_summary, memory_summary
        )
        if image_bytes:
            messages[-1]["images"] = [image_bytes]
        stream = self._client.chat(
            model=self._vision_model() if image_bytes else self.model,
            messages=messages,
            stream=True,
            keep_alive=self.keep_alive,
        )
        for chunk in stream:
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece


def split_emotion_tag(text: str) -> tuple[str, Optional[str]]:
    """Split body and emotion tag. If no tag, return (original text, None)."""
    match = _EMOTION_TAG_RE.search(text)
    if not match:
        return text.strip(), None
    cleaned = _EMOTION_TAG_RE.sub("", text).strip()
    return cleaned, match.group(1).lower()
