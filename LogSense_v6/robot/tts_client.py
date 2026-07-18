#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Qwen3-TTS client (GPU). Qt-independent.

Supports CustomVoice (preset speakers) and Base (voice clone) via config.
serialize generate calls with an internal lock so VL/TTS never corrupt state.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch

_VARIANT_CUSTOM = "custom_voice"
_VARIANT_CLONE = "voice_clone"
_DEFAULT_CUSTOM_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_DEFAULT_CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
_MAX_CHARS = 240
_EMOTION_TAG_RE = re.compile(r"\[emotion:\s*[a-zA-Z]+\s*\]")
_WHITESPACE_RE = re.compile(r"\s+")


def prepare_speak_text(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Strip tags/noise and clamp length for TTS."""
    cleaned = _EMOTION_TAG_RE.sub("", text or "")
    cleaned = cleaned.replace("→", "。").replace("/", "、")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "…"
    return cleaned


class TtsClient:
    """Qwen3-TTS wrapper: warmup + synthesize to float32 mono waveform."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        variant: str = _VARIANT_CUSTOM,
        language: str = "Japanese",
        speaker: str = "Ono_Anna",
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        device: Optional[str] = None,
        dtype: str = "bfloat16",
        max_chars: int = _MAX_CHARS,
    ):
        self.variant = variant
        self.language = language
        self.speaker = speaker
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.max_chars = max_chars
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.dtype = self._resolve_dtype(dtype)
        if model_id:
            self.model_id = model_id
        elif variant == _VARIANT_CLONE:
            self.model_id = _DEFAULT_CLONE_MODEL
        else:
            self.model_id = _DEFAULT_CUSTOM_MODEL
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def _resolve_dtype(name: str) -> torch.dtype:
        mapping = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        return mapping.get(name.lower(), torch.bfloat16)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from qwen_tts import Qwen3TTSModel

        # flash-attn is often unavailable on Windows; prefer SDPA.
        kwargs: dict[str, Any] = {
            "device_map": self.device,
            "dtype": self.dtype if self.device != "cpu" else torch.float32,
            "attn_implementation": "sdpa",
        }
        self._model = Qwen3TTSModel.from_pretrained(self.model_id, **kwargs)

    def warmup(self) -> None:
        """Load weights into VRAM (pay cold start at launch)."""
        with self._lock:
            self._ensure_loaded()

    def is_ready(self) -> bool:
        return self._model is not None

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Return (waveform float32, sample_rate). Raises on empty/invalid input."""
        speak = prepare_speak_text(text, self.max_chars)
        if not speak:
            raise ValueError("empty speak text")
        with self._lock:
            self._ensure_loaded()
            if self.variant == _VARIANT_CLONE:
                wavs, sr = self._synthesize_clone(speak)
            else:
                wavs, sr = self._synthesize_custom(speak)
        wave = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
        return wave, int(sr)

    def _synthesize_custom(self, text: str) -> tuple[Any, int]:
        return self._model.generate_custom_voice(
            text=text,
            language=self.language,
            speaker=self.speaker,
        )

    def _synthesize_clone(self, text: str) -> tuple[Any, int]:
        if not self.ref_audio:
            raise ValueError("voice_clone requires ref_audio in config")
        ref = self.ref_audio
        path = Path(ref)
        if path.is_file():
            ref = str(path.resolve())
        kwargs: dict[str, Any] = {
            "text": text,
            "language": self.language,
            "ref_audio": ref,
        }
        if self.ref_text:
            kwargs["ref_text"] = self.ref_text
        else:
            kwargs["x_vector_only_mode"] = True
        return self._model.generate_voice_clone(**kwargs)


def build_tts_client(cfg: dict, project_root: Path) -> TtsClient:
    """Build TtsClient from robot_config.json['tts'] section."""
    variant = str(cfg.get("variant", _VARIANT_CUSTOM))
    ref_audio = cfg.get("ref_audio")
    if ref_audio and not Path(ref_audio).is_absolute():
        ref_audio = str((project_root / ref_audio).resolve())
    return TtsClient(
        model_id=cfg.get("model_id"),
        variant=variant,
        language=str(cfg.get("language", "Japanese")),
        speaker=str(cfg.get("speaker", "Ono_Anna")),
        ref_audio=ref_audio,
        ref_text=cfg.get("ref_text"),
        dtype=str(cfg.get("dtype", "bfloat16")),
        max_chars=int(cfg.get("max_chars", _MAX_CHARS)),
    )
