#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen2.5-VL client running on GPU via transformers + bitsandbytes (4-bit).

Exposes the same interface as OllamaClient (chat_stream / describe_image /
warmup), so robot.py only swaps the client. One model serves both chat and
image understanding; an internal lock prevents concurrent generate calls
(running one model from two threads at once would corrupt state).
"""

from __future__ import annotations

import io
import threading
from typing import Iterator, Optional

import torch
from PIL import Image
from transformers import (
    AutoProcessor,
    BitsAndBytesConfig,
    Qwen2_5_VLForConditionalGeneration,
    TextIteratorStreamer,
)
from qwen_vl_utils import process_vision_info

from robot.llm_client import _DEFAULT_PERSONA, ChatTurn

_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
_MAX_NEW_TOKENS_CHAT = 256
_MAX_NEW_TOKENS_CAPTION = 96
# Image token bounds (limit prompt_eval cost). 28*28 = one patch.
_MIN_PIXELS = 256 * 28 * 28
_MAX_PIXELS = 768 * 28 * 28


class QwenVLClient:
    """Single GPU model (4-bit) handling both chat and image captioning."""

    def __init__(
        self,
        model_id: str = _MODEL_ID,
        persona: str = _DEFAULT_PERSONA,
        device: Optional[str] = None,
    ):
        self.model_id = model_id
        self.persona = persona
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._processor = None
        self._lock = threading.Lock()  # serialize chat/image generate

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_id,
            quantization_config=quant,
            device_map=self.device,
            torch_dtype=torch.float16,
        )
        self._processor = AutoProcessor.from_pretrained(
            self.model_id, min_pixels=_MIN_PIXELS, max_pixels=_MAX_PIXELS
        )

    def warmup(self) -> None:
        """Load the model into VRAM (pay the cold load at startup)."""
        with self._lock:
            self._ensure_loaded()

    def _build_messages(
        self,
        user_text: str,
        history: list[ChatTurn],
        perception_summary: Optional[str],
        memory_summary: Optional[str],
        image: Optional[Image.Image] = None,
    ) -> list[dict]:
        system = self.persona
        if memory_summary:
            system += f"\n\n【これまでの記憶】\n{memory_summary}"
        if perception_summary:
            system += f"\n\n【今カメラで見えているもの】\n{perception_summary}"
        if image is not None:
            system += (
                "\n\n添付されたカメラ画像を実際に見て、事実に基づいて答えてください。"
            )
        messages: list[dict] = [
            {"role": "system", "content": [{"type": "text", "text": system}]}
        ]
        for turn in history:
            messages.append(
                {"role": turn.role, "content": [{"type": "text", "text": turn.content}]}
            )
        user_content: list[dict] = []
        if image is not None:
            user_content.append({"type": "image", "image": image})
        user_content.append({"type": "text", "text": user_text})
        messages.append({"role": "user", "content": user_content})
        return messages

    def chat_stream(
        self,
        user_text: str,
        history: Optional[list[ChatTurn]] = None,
        perception_summary: Optional[str] = None,
        memory_summary: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> Iterator[str]:
        """Yield reply tokens one by one (the emotion tag is included).

        When image_bytes is given, the current camera frame is attached to the
        user turn so the model answers from the actual pixels, not just the
        text summary (slower: image prefill, but grounded on what it sees).
        """
        with self._lock:
            self._ensure_loaded()
            image = (
                Image.open(io.BytesIO(image_bytes)).convert("RGB")
                if image_bytes
                else None
            )
            messages = self._build_messages(
                user_text, history or [], perception_summary, memory_summary, image
            )
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            if image is not None:
                image_inputs, video_inputs = process_vision_info(messages)
                inputs = self._processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors="pt",
                ).to(self.device)
            else:
                inputs = self._processor(
                    text=[text], padding=True, return_tensors="pt"
                ).to(self.device)
            streamer = TextIteratorStreamer(
                self._processor.tokenizer, skip_prompt=True, skip_special_tokens=True
            )
            gen_kwargs = dict(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS_CHAT,
                do_sample=False,
                streamer=streamer,
            )
            thread = threading.Thread(target=self._model.generate, kwargs=gen_kwargs)
            thread.start()
            for piece in streamer:
                if piece:
                    yield piece
            thread.join()

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        """Describe a single image (JPEG bytes) in one shot."""
        with self._lock:
            self._ensure_loaded()
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self._processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            out = self._model.generate(
                **inputs, max_new_tokens=_MAX_NEW_TOKENS_CAPTION, do_sample=False
            )
            trimmed = [o[len(i) :] for i, o in zip(inputs.input_ids, out)]
            return self._processor.batch_decode(trimmed, skip_special_tokens=True)[
                0
            ].strip()
