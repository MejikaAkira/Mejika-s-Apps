#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the robot's pure logic (emotion, memory, perception, tag split).

Only the parts independent of the LLM and Qt are covered here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot.emotion import Emotion, Perception, decide
from robot.llm_client import split_emotion_tag
from robot.memory import MemoryStore
from robot.perception_bridge import PerceptionBridge


# --- Emotion ---------------------------------------------------------------


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("happy", Emotion.HAPPY),
        ("HAPPY", Emotion.HAPPY),
        ("joy", Emotion.HAPPY),
        ("normal", Emotion.NORMAL),
        ("neutral", Emotion.NORMAL),
        ("worried", Emotion.WORRIED),
        ("sad", Emotion.WORRIED),
        ("anger", Emotion.WORRIED),
        ("noticed", Emotion.NOTICED),
        ("surprise", Emotion.NOTICED),
        ("unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_emotion_from_tag(tag, expected):
    assert Emotion.from_tag(tag) == expected


def test_decide_perception_event_overrides_llm():
    # A perception event (noticing a new object) beats the LLM tag.
    perception = Perception(new_object=True)
    assert decide(llm_tag="happy", perception=perception) == Emotion.NOTICED


def test_decide_falls_back_to_llm_then_default():
    assert decide(llm_tag="happy") == Emotion.HAPPY
    assert decide() == Emotion.NORMAL
    assert decide(default=Emotion.WORRIED) == Emotion.WORRIED


def test_perception_event_priority_error_over_new():
    p = Perception(new_object=True, error_burst=True)
    assert p.to_event() == "error_burst"


# --- emotion tag split -----------------------------------------------------


def test_split_emotion_tag_extracts_and_cleans():
    text = "こんにちは！ [emotion:joy]"
    body, tag = split_emotion_tag(text)
    assert body == "こんにちは！"
    assert tag == "joy"


def test_split_emotion_tag_without_tag():
    body, tag = split_emotion_tag("ただの文章です")
    assert body == "ただの文章です"
    assert tag is None


# --- PerceptionBridge ------------------------------------------------------


def test_bridge_detects_new_object_then_not_new():
    bridge = PerceptionBridge()
    first = bridge.update(["person"], 0.1)
    assert first.new_object is True
    second = bridge.update(["person"], 0.1)
    assert second.new_object is False


def test_bridge_idle_silence_after_threshold():
    bridge = PerceptionBridge()
    p = None
    for _ in range(100):
        p = bridge.update([], 0.0)
    assert p.idle_silence is True


def test_bridge_summary_text():
    assert "person" in PerceptionBridge.summary_text(["person", "person"])
    assert PerceptionBridge.summary_text([]).startswith("今は")


# --- MemoryStore -----------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "memory.jsonl",
    )


def test_memory_record_chat_increases_exp(tmp_path):
    store = _make_store(tmp_path)
    store.record_chat("やあ", "こんにちは")
    assert store.state.chat_count == 1
    assert store.state.exp > 0


def test_memory_record_objects_only_new(tmp_path):
    store = _make_store(tmp_path)
    new1 = store.record_objects(["cat", "dog"])
    assert set(new1) == {"cat", "dog"}
    new2 = store.record_objects(["cat"])
    assert new2 == []


def test_memory_persists_across_instances(tmp_path):
    store = _make_store(tmp_path)
    store.record_objects(["cat"])
    store.record_chat("a", "b")
    reloaded = _make_store(tmp_path)
    assert "cat" in reloaded.state.known_objects
    assert reloaded.state.chat_count == 1


def test_memory_level_rises_with_exp(tmp_path):
    store = _make_store(tmp_path)
    base_level = store.state.level
    for i in range(20):
        store.record_objects([f"obj{i}"])
    assert store.state.level > base_level


# --- TTS text prep ---------------------------------------------------------


def test_prepare_speak_text_strips_emotion_and_clamps():
    from robot.tts_client import prepare_speak_text

    body = prepare_speak_text("こんにちは！ [emotion:happy]")
    assert "[emotion" not in body
    assert "こんにちは" in body
    long = "あ" * 300
    clipped = prepare_speak_text(long, max_chars=50)
    assert len(clipped) <= 51
    assert prepare_speak_text("   ") == ""
