#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS client that talks JSON-lines to a worker in a separate venv/process."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf

from robot.tts_text import prepare_speak_text

_MAX_CHARS = 240


class SubprocessTtsClient:
    """Keep a worker alive; synthesize writes a WAV the parent loads."""

    def __init__(
        self,
        python_exe: Path,
        worker_script: Path,
        worker_config: dict[str, Any],
        project_root: Path,
        max_chars: int = _MAX_CHARS,
        out_wav: Optional[Path] = None,
    ):
        self._python = Path(python_exe)
        self._worker_script = Path(worker_script)
        self._worker_config = worker_config
        self._project_root = Path(project_root)
        self.max_chars = max_chars
        self._out_wav = out_wav or (
            self._project_root / "robot_data" / "tts_worker_last.wav"
        )
        self._proc: Optional[subprocess.Popen[str]] = None
        self._stderr_fh = None
        self._lock = threading.Lock()
        self._ready = False

    def warmup(self) -> None:
        with self._lock:
            self._ensure_proc()
            self._rpc({"op": "warmup"})
            self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        speak = prepare_speak_text(text, self.max_chars)
        if not speak:
            raise ValueError("empty speak text")
        with self._lock:
            self._ensure_proc()
            self._out_wav.parent.mkdir(parents=True, exist_ok=True)
            self._rpc(
                {
                    "op": "synthesize",
                    "text": speak,
                    "out": str(self._out_wav.resolve()),
                }
            )
            wave, sr = sf.read(str(self._out_wav), always_2d=False)
            if getattr(wave, "ndim", 1) > 1:
                wave = np.mean(wave, axis=1)
            return np.asarray(wave, dtype=np.float32).reshape(-1), int(sr)

    def close(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            try:
                self._rpc({"op": "shutdown"}, allow_fail=True)
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            self._ready = False
            if self._stderr_fh is not None:
                try:
                    self._stderr_fh.close()
                except Exception:
                    pass
                self._stderr_fh = None

    def _ensure_proc(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if not self._python.is_file():
            raise FileNotFoundError(f"TTS python not found: {self._python}")
        if not self._worker_script.is_file():
            raise FileNotFoundError(f"TTS worker not found: {self._worker_script}")
        log_path = self._project_root / "robot_data" / "tts_worker_stderr.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr_fh = open(log_path, "a", encoding="utf-8", errors="replace")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self._project_root) + (
            (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
        )
        env["PYTHONIOENCODING"] = "utf-8"
        self._proc = subprocess.Popen(
            [str(self._python), "-u", str(self._worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_fh,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self._project_root),
            bufsize=1,
            env=env,
        )
        # First line from worker must be ready handshake after sending config.
        self._rpc({"op": "init", "config": self._worker_config})

    def _rpc(self, payload: dict[str, Any], allow_fail: bool = False) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdin and self._proc.stdout
        line = json.dumps(payload, ensure_ascii=False)
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except BrokenPipeError as exc:
            err = self._read_stderr_tail()
            raise RuntimeError(f"TTS worker pipe broken: {err}") from exc
        raw = ""
        while True:
            raw = self._proc.stdout.readline()
            if not raw:
                err = self._read_stderr_tail()
                code = self._proc.poll()
                raise RuntimeError(f"TTS worker exited (code={code}): {err}")
            stripped = raw.strip()
            if not stripped:
                continue
            # Skip non-JSON noise (progress bars / colored logs).
            if not stripped.startswith("{"):
                continue
            break
        try:
            resp = json.loads(stripped)
        except json.JSONDecodeError as exc:
            err = self._read_stderr_tail()
            raise RuntimeError(f"bad TTS worker JSON: {stripped!r} / {err}") from exc
        if not resp.get("ok", False):
            if allow_fail:
                return resp
            raise RuntimeError(str(resp.get("error", "TTS worker error")))
        return resp

    def _read_stderr_tail(self) -> str:
        path = self._project_root / "robot_data" / "tts_worker_stderr.log"
        try:
            if not path.is_file():
                return ""
            data = path.read_text(encoding="utf-8", errors="replace")
            return data[-4000:]
        except Exception:
            return ""

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def resolve_python(
    cfg_path: Optional[str], project_root: Path, default_rel: str
) -> Path:
    raw = cfg_path or default_rel
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()
