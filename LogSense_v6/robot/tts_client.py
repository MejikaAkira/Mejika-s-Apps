#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Qwen3-TTS client (GPU). Qt-independent.

Supports CustomVoice (preset speakers) and Base (voice clone) via config.
serialize generate calls with an internal lock so VL/TTS never corrupt state.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch

from robot.tts_text import prepare_speak_text

_VARIANT_CUSTOM = "custom_voice"
_VARIANT_CLONE = "voice_clone"
_DEFAULT_CUSTOM_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_DEFAULT_CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
_MAX_CHARS = 240

# Re-export for existing imports.
__all__ = ["TtsClient", "build_tts_client", "prepare_speak_text"]


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


def build_qwen_tts_client(cfg: dict, project_root: Path) -> TtsClient:
    """In-process Qwen3-TTS client (legacy / tests). Prefer subprocess via engine=qwen."""
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


def build_tts_client(cfg: dict, project_root: Path):
    """Build TTS client from robot_config.json['tts'].

    engine:
      - qwen / voicevox / sbv2 → separate worker process (venv isolated)
      - qwen_inplace → in-process TtsClient (tests / fallback)
    Missing engine with flat keys → qwen_inplace (backward compatible).
    """
    from robot.tts_subprocess import SubprocessTtsClient, resolve_python

    engine = str(cfg.get("engine", "")).strip().lower()
    max_chars = int(cfg.get("max_chars", _MAX_CHARS))
    workers = project_root / "robot" / "tts_workers"

    if not engine:
        # Legacy flat config used by robot.py
        return build_qwen_tts_client(cfg, project_root)

    if engine in {"qwen_inplace", "qwen-inplace"}:
        qcfg = cfg.get("qwen") if isinstance(cfg.get("qwen"), dict) else cfg
        return build_qwen_tts_client(qcfg, project_root)

    if engine == "qwen":
        qcfg = dict(cfg.get("qwen") or {})
        # Allow top-level legacy keys as fallback.
        for key in (
            "variant",
            "model_id",
            "language",
            "speaker",
            "dtype",
            "ref_audio",
            "ref_text",
            "max_chars",
        ):
            if key not in qcfg and key in cfg:
                qcfg[key] = cfg[key]
        if qcfg.get("ref_audio") and not Path(str(qcfg["ref_audio"])).is_absolute():
            qcfg["ref_audio"] = str((project_root / qcfg["ref_audio"]).resolve())
        qcfg.setdefault("max_chars", max_chars)
        python = resolve_python(qcfg.get("python"), project_root, sys.executable)
        return SubprocessTtsClient(
            python_exe=python,
            worker_script=workers / "qwen_worker.py",
            worker_config=qcfg,
            project_root=project_root,
            max_chars=max_chars,
        )

    if engine in {"sbv2", "style_bert_vits2"}:
        scfg = dict(cfg.get("sbv2") or {})
        scfg.setdefault("device", "cuda")
        scfg.setdefault("model", "jvnv-F1-jp")
        scfg.setdefault("style", "Neutral")
        scfg.setdefault("pitch_scale", 1.10)
        scfg.setdefault("style_weight", 1.0)
        scfg.setdefault("intonation_scale", 0.95)
        scfg.setdefault("length", 0.95)
        python = resolve_python(
            scfg.get("python"), project_root, "venv_sbv2/Scripts/python.exe"
        )
        return SubprocessTtsClient(
            python_exe=python,
            worker_script=workers / "sbv2_worker.py",
            worker_config=scfg,
            project_root=project_root,
            max_chars=max_chars,
        )

    if engine in {"voicevox", "vv"}:
        vcfg = dict(cfg.get("voicevox") or {})
        vcfg.setdefault("style_id", 3)
        vcfg.setdefault("runtime_dir", "voicevox_runtime")
        vcfg.setdefault("gentle_mimamori", True)
        runtime = Path(str(vcfg["runtime_dir"]))
        if not runtime.is_absolute():
            vcfg["runtime_dir"] = str((project_root / runtime).resolve())
        python = resolve_python(
            vcfg.get("python"), project_root, "venv_vv/Scripts/python.exe"
        )
        return SubprocessTtsClient(
            python_exe=python,
            worker_script=workers / "vv_worker.py",
            worker_config=vcfg,
            project_root=project_root,
            max_chars=max_chars,
        )

    raise ValueError(f"unknown tts.engine: {engine!r}")
