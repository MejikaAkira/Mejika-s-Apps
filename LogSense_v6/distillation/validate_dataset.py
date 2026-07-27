"""Minimum quality gate before training on teacher output.

This is a rule check only. Human review of the generated answers is still
required; automated checks cannot judge tone or factual honesty.
"""

import json
import logging
import re
from typing import Any

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

MAX_ANSWER_CHARS = 1200

# Overconfident claims only. Do not list words that a correct refusal has to
# quote back ("パスワードを盗む" fired on a well-formed refusal): judging safety
# by keyword presence rejects the good answers, not the bad ones.
FORBIDDEN_PHRASES = (
    "必ず成功します",
    "絶対に正しい",
)

# The persona fixes the first person to the robot's own name.
FORBIDDEN_PRONOUNS = ("私", "僕", "わたし", "ぼく")

# "ロビ" was the earlier working name. Catch it so old-name answers cannot
# slip into the dataset after the rename to ロギー (Loggy).
WRONG_ROBOT_NAMES = ("ロビ",)

# Simplified-Chinese-only characters that Qwen models occasionally leak into
# Japanese output (e.g. 预测 instead of 予測). Not exhaustive by design:
# it catches the frequent cases, human review catches the rest.
SIMPLIFIED_CHINESE_CHARS = "预说这个们讲语请关对应还现实变达进运过边远样无为开业书车东"

# Robi is an original character. If the teacher leaks names, gadgets or
# catchphrases from an existing work, the record must not reach training.
COPYRIGHTED_TERMS = (
    "ドラえもん",
    "のび太",
    "四次元ポケット",
    "どこでもドア",
    "タケコプター",
    "ネコ型ロボット",
    "猫型ロボット",
)

# The persona requires exactly one emotion tag at the end of every answer.
EMOTION_TAG_RE = re.compile(r"\[emotion:\s*(normal|happy|worried|noticed)\s*\]")

# Latin words also leak from other languages (a Spanish "parecido" appeared in
# a Japanese answer). Flag any Latin run that is not an accepted term.
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
ALLOWED_LATIN_WORDS = frozenset({"ai", "yolo", "cpu", "gpu", "wi", "fi", "ok"})


def check_structure(record: dict[str, Any]) -> list[str]:
    """Check the record shape expected by TRL."""

    errors: list[str] = []

    if not isinstance(record.get("id"), str):
        errors.append("missing id")

    prompt = record.get("prompt")
    if not isinstance(prompt, list) or len(prompt) < 2:
        errors.append("malformed prompt")

    completion = record.get("completion")
    if not isinstance(completion, list) or len(completion) != 1:
        errors.append("malformed completion")

    return errors


def check_answer(answer: str) -> list[str]:
    """Check the answer text itself."""

    errors: list[str] = []

    if len(answer) > MAX_ANSWER_CHARS:
        errors.append(f"answer too long: {len(answer)} chars")

    if "</think>" in answer or "<think>" in answer:
        errors.append("thinking trace leaked into the answer")

    tag_count = len(EMOTION_TAG_RE.findall(answer))
    if tag_count != 1:
        errors.append(f"expected exactly 1 emotion tag, found {tag_count}")

    errors.extend(
        f"forbidden phrase: {phrase}"
        for phrase in FORBIDDEN_PHRASES
        if phrase in answer
    )
    errors.extend(
        f"copyrighted term: {term}" for term in COPYRIGHTED_TERMS if term in answer
    )
    errors.extend(
        f"wrong first person: {pronoun}"
        for pronoun in FORBIDDEN_PRONOUNS
        if pronoun in answer
    )
    errors.extend(
        f"outdated robot name: {name}" for name in WRONG_ROBOT_NAMES if name in answer
    )

    leaked = sorted({char for char in answer if char in SIMPLIFIED_CHINESE_CHARS})
    if leaked:
        errors.append(f"simplified chinese leaked: {''.join(leaked)}")

    errors.extend(check_latin_words(answer))

    return errors


def check_latin_words(answer: str) -> list[str]:
    """Flag Latin words that are neither the emotion tag nor an accepted term."""

    without_tag = EMOTION_TAG_RE.sub("", answer)

    return [
        f"unexpected latin word: {word}"
        for word in LATIN_WORD_RE.findall(without_tag)
        if word.lower() not in ALLOWED_LATIN_WORDS
    ]


def validate_record(record: dict[str, Any]) -> list[str]:
    """Return every problem found in one record."""

    errors = check_structure(record)
    if errors:
        return errors

    answer = record["completion"][0].get("content")
    if not isinstance(answer, str) or not answer.strip():
        return ["empty answer"]

    return check_answer(answer)


def main() -> None:
    if not settings.dataset_file.exists():
        raise FileNotFoundError(f"Dataset not found: {settings.dataset_file}")

    total = 0
    invalid = 0

    with settings.dataset_file.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            total += 1
            record = json.loads(line)
            errors = validate_record(record)

            if errors:
                invalid += 1
                logger.error(
                    "Invalid record: line=%d id=%s errors=%s",
                    line_number,
                    record.get("id"),
                    errors,
                )

    logger.info("Validation finished: total=%d invalid=%d", total, invalid)

    if invalid > 0:
        raise RuntimeError("Invalid records found. Check the log above.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Dataset validation failed.")
        raise
