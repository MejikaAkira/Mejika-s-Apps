#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Style-Bert-VITS2 JSON-lines worker (run under venv_sbv2)."""

from __future__ import annotations

import json
import sys
import traceback
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np


def _reply(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _save_wav(path: Path, sr: int, audio: Any) -> None:
    arr = np.asarray(audio)
    if arr.dtype != np.int16:
        peak = float(np.max(np.abs(arr))) or 1.0
        pcm = (arr / peak * 32767.0).astype(np.int16)
    else:
        pcm = arr.astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())


class Sbv2Engine:
    def __init__(self, cfg: dict[str, Any]):
        import torch
        from huggingface_hub import snapshot_download
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.nlp import bert_models
        from style_bert_vits2.tts_model import TTSModel

        self.device = str(cfg.get("device", "cuda"))
        if self.device == "cuda" and not torch.cuda.is_available():
            self.device = "cpu"
        model_name = str(cfg.get("model", "jvnv-F1-jp"))
        self.style = str(cfg.get("style", "Neutral"))
        self.pitch_scale = float(cfg.get("pitch_scale", 1.10))
        self.style_weight = float(cfg.get("style_weight", 1.0))
        self.intonation_scale = float(cfg.get("intonation_scale", 0.95))
        self.length = float(cfg.get("length", 0.95))

        root = Path(
            snapshot_download(
                "litagin/style_bert_vits2_jvnv",
                allow_patterns=[f"{model_name}/*"],
                local_files_only=bool(cfg.get("local_files_only", False)),
            )
        )
        jp_dir = root / model_name
        safetensors = sorted(jp_dir.glob("*.safetensors"))
        if not safetensors:
            raise FileNotFoundError(f"no safetensors in {jp_dir}")
        bert_models.load_model(
            Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm"
        )
        bert_models.load_tokenizer(
            Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm"
        )
        bert_models.load_model(Languages.JP).float().eval()
        self.model = TTSModel(
            model_path=safetensors[0],
            config_path=jp_dir / "config.json",
            style_vec_path=jp_dir / "style_vectors.npy",
            device=self.device,
        )

    def warmup(self) -> None:
        self.model.infer(text="\u30c6\u30b9\u30c8\u3002")

    def synthesize(self, text: str, out: Path) -> int:
        sr, audio = self.model.infer(
            text=text,
            style=self.style,
            style_weight=self.style_weight,
            pitch_scale=self.pitch_scale,
            intonation_scale=self.intonation_scale,
            length=self.length,
        )
        _save_wav(out, int(sr), audio)
        return int(sr)


def main() -> None:
    # Keep stdout JSON-only (style-bert-vits2 / loguru may log to stdout).
    try:
        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
    except Exception:
        pass

    engine: Optional[Sbv2Engine] = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "init":
                engine = Sbv2Engine(req.get("config") or {})
                _reply({"ok": True, "engine": "sbv2", "device": engine.device})
            elif op == "warmup":
                if engine is None:
                    raise RuntimeError("not initialized")
                engine.warmup()
                _reply({"ok": True})
            elif op == "synthesize":
                if engine is None:
                    raise RuntimeError("not initialized")
                out = Path(req["out"])
                sr = engine.synthesize(str(req.get("text", "")), out)
                _reply({"ok": True, "sr": sr, "path": str(out)})
            elif op == "shutdown":
                _reply({"ok": True})
                break
            else:
                _reply({"ok": False, "error": f"unknown op: {op}"})
        except Exception as exc:
            _reply({"ok": False, "error": f"{exc}\n{traceback.format_exc()}"})


if __name__ == "__main__":
    main()
