#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen3-TTS JSON-lines worker (separate process from GUI/VL)."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf


def _reply(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class QwenEngine:
    def __init__(self, cfg: dict[str, Any]):
        # Import from project package (cwd = project root).
        from robot.tts_client import TtsClient

        variant = str(cfg.get("variant", "custom_voice"))
        ref_audio = cfg.get("ref_audio")
        self.client = TtsClient(
            model_id=cfg.get("model_id"),
            variant=variant,
            language=str(cfg.get("language", "Japanese")),
            speaker=str(cfg.get("speaker", "Ono_Anna")),
            ref_audio=ref_audio,
            ref_text=cfg.get("ref_text"),
            dtype=str(cfg.get("dtype", "bfloat16")),
            max_chars=int(cfg.get("max_chars", 240)),
        )

    def warmup(self) -> None:
        self.client.warmup()

    def synthesize(self, text: str, out: Path) -> int:
        wave, sr = self.client.synthesize(text)
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), np.asarray(wave, dtype=np.float32), int(sr))
        return int(sr)


def main() -> None:
    engine: Optional[QwenEngine] = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "init":
                engine = QwenEngine(req.get("config") or {})
                _reply({"ok": True, "engine": "qwen"})
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
