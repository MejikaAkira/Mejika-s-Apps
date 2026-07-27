#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOICEVOX Core JSON-lines worker (run under venv_vv)."""

from __future__ import annotations

import io
import json
import sys
import traceback
import wave
from pathlib import Path
from typing import Any, Optional


def _reply(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def apply_gentle_mimamori(aq: Any) -> None:
    """Match bench_vv_dora_zundamon_normal pitch tweak for 見守り."""
    for ap in aq.accent_phrases:
        texts = [m.text for m in ap.moras]
        for i in range(len(texts) - 3):
            if texts[i : i + 4] != ["ミ", "マ", "モ", "リ"]:
                continue
            mi, ma, mo, ri = ap.moras[i : i + 4]
            base = mi.pitch
            mi.pitch = base
            ma.pitch = base + 0.18
            mo.pitch = base + 0.15
            ri.pitch = base + 0.12
            ap.accent = 2
            mo.vowel_length *= 1.08
            ri.vowel_length *= 1.05
            return


class VoicevoxEngine:
    def __init__(self, cfg: dict[str, Any]):
        from voicevox_core.blocking import (
            Onnxruntime,
            OpenJtalk,
            Synthesizer,
            VoiceModelFile,
        )

        runtime = Path(cfg.get("runtime_dir", "voicevox_runtime"))
        if not runtime.is_absolute():
            runtime = Path.cwd() / runtime
        self.style_id = int(cfg.get("style_id", 3))
        self.gentle_mimamori = bool(cfg.get("gentle_mimamori", True))
        ort = runtime / "onnxruntime" / "lib" / Onnxruntime.LIB_VERSIONED_FILENAME
        dic = runtime / "dict" / "open_jtalk_dic_utf_8-1.11"
        self.syn = Synthesizer(
            Onnxruntime.load_once(filename=str(ort)),
            OpenJtalk(str(dic)),
        )
        vvms = sorted((runtime / "models" / "vvms").glob("*.vvm"))
        if not vvms:
            raise FileNotFoundError(f"no vvm under {runtime / 'models' / 'vvms'}")
        for vvm in vvms:
            with VoiceModelFile.open(str(vvm)) as model:
                self.syn.load_voice_model(model)

    def warmup(self) -> None:
        self.syn.tts("テスト。", self.style_id)

    def synthesize(self, text: str, out: Path) -> int:
        if self.gentle_mimamori:
            aq = self.syn.create_audio_query(text, self.style_id)
            apply_gentle_mimamori(aq)
            wav_bytes = self.syn.synthesis(aq, self.style_id)
        else:
            wav_bytes = self.syn.tts(text, self.style_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(wav_bytes)
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            return int(w.getframerate())


def main() -> None:
    engine: Optional[VoicevoxEngine] = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "init":
                engine = VoicevoxEngine(req.get("config") or {})
                _reply({"ok": True, "engine": "voicevox", "style_id": engine.style_id})
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
