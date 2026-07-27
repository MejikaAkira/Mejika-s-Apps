#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS text helpers: clean speak text and split into sentence chunks.
"""

from __future__ import annotations

import re

_MAX_CHARS = 240
_EMOTION_TAG_RE = re.compile(r"\[emotion:\s*[a-zA-Z]+\s*\]")
_WHITESPACE_RE = re.compile(r"\s+")
# Keep the delimiter on the sentence (。！？ and ASCII !?).
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?\n]?")
# Latin token (letters, optional digits like v2 / GPT4).
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:'[A-Za-z]+)?")

# Common mixed-in English → Japanese reading (lowercase keys).
_EN_READINGS: dict[str, str] = {
    "ok": "オーケー",
    "ng": "エヌジー",
    "yes": "イエス",
    "no": "ノー",
    "ai": "エーアイ",
    "gpu": "ジーピーユー",
    "cpu": "シーピーユー",
    "tts": "ティーティーエス",
    "llm": "エルエルエム",
    "vl": "ブイエル",
    "api": "エーピーアイ",
    "url": "ユーアールエル",
    "http": "エイチティーティーピー",
    "https": "エイチティーティーピーエス",
    "wifi": "ワイファイ",
    "usb": "ユーエスビー",
    "pc": "ピーシー",
    "os": "オーエス",
    "id": "アイディー",
    "ui": "ユーアイ",
    "app": "アップ",
    "bot": "ボット",
    "robot": "ロボット",
    "test": "テスト",
    "error": "エラー",
    "warning": "ワーニング",
    "debug": "デバッグ",
    "log": "ログ",
    "logs": "ログ",
    "file": "ファイル",
    "folder": "フォルダ",
    "path": "パス",
    "version": "バージョン",
    "update": "アップデート",
    "download": "ダウンロード",
    "upload": "アップロード",
    "start": "スタート",
    "stop": "ストップ",
    "ready": "レディ",
    "online": "オンライン",
    "offline": "オフライン",
    "cuda": "クーダ",
    "onnx": "オンエックス",
    "qwen": "クウェン",
    "voicevox": "ボイスボックス",
    "sbv2": "エスビーブイツー",
}

_LETTER_READINGS: dict[str, str] = {
    "a": "エー",
    "b": "ビー",
    "c": "シー",
    "d": "ディー",
    "e": "イー",
    "f": "エフ",
    "g": "ジー",
    "h": "エイチ",
    "i": "アイ",
    "j": "ジェー",
    "k": "ケー",
    "l": "エル",
    "m": "エム",
    "n": "エヌ",
    "o": "オー",
    "p": "ピー",
    "q": "キュー",
    "r": "アール",
    "s": "エス",
    "t": "ティー",
    "u": "ユー",
    "v": "ブイ",
    "w": "ダブリュー",
    "x": "エックス",
    "y": "ワイ",
    "z": "ゼット",
}

_DIGIT_READINGS: dict[str, str] = {
    "0": "ゼロ",
    "1": "ワン",
    "2": "ツー",
    "3": "スリー",
    "4": "フォー",
    "5": "ファイブ",
    "6": "シックス",
    "7": "セブン",
    "8": "エイト",
    "9": "ナイン",
}


def _spell_latin_token(token: str) -> str:
    """Fallback: read unknown Latin token letter/digit by letter."""
    parts: list[str] = []
    for ch in token:
        low = ch.lower()
        if low in _LETTER_READINGS:
            parts.append(_LETTER_READINGS[low])
        elif ch in _DIGIT_READINGS:
            parts.append(_DIGIT_READINGS[ch])
    return "".join(parts)


def normalize_english_for_ja_tts(text: str) -> str:
    """Replace light English fragments with Japanese readings for JA TTS."""

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        key = token.lower()
        if key in _EN_READINGS:
            return _EN_READINGS[key]
        spelled = _spell_latin_token(token)
        return spelled if spelled else token

    return _LATIN_TOKEN_RE.sub(repl, text)


def prepare_speak_text(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Strip tags/noise, normalize light English, and clamp length for TTS."""
    cleaned = _EMOTION_TAG_RE.sub("", text or "")
    cleaned = cleaned.replace("→", "。").replace("/", "、")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    cleaned = normalize_english_for_ja_tts(cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "…"
    return cleaned


def split_sentences(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
    """Split cleaned text into sentence chunks for sequential TTS."""
    cleaned = prepare_speak_text(text, max_chars=max_chars * 4)
    if not cleaned:
        return []
    parts = [p.strip() for p in _SENTENCE_RE.findall(cleaned)]
    chunks = [p for p in parts if p]
    if not chunks:
        return [cleaned] if cleaned else []
    # Clamp each chunk; overlong chunks are truncated (rare).
    return [prepare_speak_text(c, max_chars=max_chars) for c in chunks if c.strip()]
