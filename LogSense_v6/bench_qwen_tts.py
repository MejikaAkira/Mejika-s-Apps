#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 0 bench: load Qwen3-TTS CustomVoice and synthesize a short Japanese line.
Usage (venv): python bench_qwen_tts.py
Optional: python bench_qwen_tts.py --play
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import torch

from robot.tts_client import TtsClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--play", action="store_true", help="Play audio via sounddevice"
    )
    parser.add_argument(
        "--text",
        default="こんにちは、わたしはロビです。見守りを始めます。",
    )
    args = parser.parse_args()

    print(f"cuda_available={torch.cuda.is_available()}")
    client = TtsClient(variant="custom_voice", language="Japanese", speaker="Ono_Anna")
    t0 = time.perf_counter()
    client.warmup()
    print(f"warmup_sec={time.perf_counter() - t0:.2f}")
    if torch.cuda.is_available():
        print(f"vram_gb={torch.cuda.memory_allocated() / 1e9:.2f}")

    t1 = time.perf_counter()
    wave, sr = client.synthesize(args.text)
    synth_sec = time.perf_counter() - t1
    duration_sec = len(wave) / sr
    print(f"synth_sec={synth_sec:.2f} audio_sec={duration_sec:.2f} sr={sr}")
    print(f"rtf={synth_sec / max(duration_sec, 1e-6):.3f}")

    out = Path("robot_data") / "tts_bench_out.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    import soundfile as sf

    sf.write(str(out), wave, sr)
    print(f"wrote {out}")

    if args.play:
        import sounddevice as sd

        sd.play(wave, sr, blocking=True)
        print("playback done")


if __name__ == "__main__":
    main()
