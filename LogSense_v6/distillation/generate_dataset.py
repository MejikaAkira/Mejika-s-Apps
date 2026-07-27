"""Ask the teacher model for reference answers and store them as JSONL.

The script is resumable: records already present in the output file are
skipped, so an interrupted run can simply be started again.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from config import settings
from persona import SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

RETRY_BACKOFF_SEC = 2


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, turning a broken line into an explicit error."""

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSONL parse error: file={path}, line={line_number}, error={error}"
                ) from error

    logger.info("Loaded JSONL: path=%s count=%d", path, len(records))
    return records


def completed_ids(path: Path) -> set[str]:
    """Collect ids already written, so the run can resume."""

    if not path.exists():
        return set()

    return {
        record["id"] for record in read_jsonl(path) if isinstance(record.get("id"), str)
    }


def strip_thinking(answer: str) -> str:
    """Drop reasoning traces that some Qwen3 servers still emit."""

    if "</think>" in answer:
        return answer.split("</think>", 1)[-1]
    return answer


def ask_teacher(client: OpenAI, model: str, user_message: str) -> str:
    """Request one teacher answer, retrying transient failures."""

    last_error: Exception | None = None

    for attempt in range(1, settings.teacher_max_retries + 1):
        try:
            logger.info(
                "Teacher request: attempt=%d/%d", attempt, settings.teacher_max_retries
            )

            response = client.chat.completions.create(
                model=model,
                temperature=settings.teacher_temperature,
                max_tokens=settings.teacher_max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                # Disable thinking mode: it wastes output tokens and pollutes
                # the dataset. Both spellings are sent because providers differ.
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "reasoning": {"enabled": False},
                },
            )

            answer = response.choices[0].message.content

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Teacher returned an empty answer.")

            return strip_thinking(answer).strip()

        except Exception as error:
            last_error = error
            logger.exception("Teacher request failed: attempt=%d", attempt)
            if attempt < settings.teacher_max_retries:
                time.sleep(attempt * RETRY_BACKOFF_SEC)

    raise RuntimeError(f"Could not get a teacher answer: {last_error}") from last_error


def append_record(
    output_path: Path,
    record_id: str,
    user_message: str,
    answer: str,
) -> None:
    """Append one record in the conversational prompt-completion format TRL expects."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "id": record_id,
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "completion": [
            {"role": "assistant", "content": answer},
        ],
    }

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_teacher_env() -> tuple[str, str, str]:
    """Read teacher connection settings from the environment."""

    load_dotenv()

    base_url = os.getenv("TEACHER_BASE_URL")
    api_key = os.getenv("TEACHER_API_KEY")
    model = os.getenv("TEACHER_MODEL")

    if not base_url:
        raise RuntimeError("TEACHER_BASE_URL is not set.")
    if not api_key:
        raise RuntimeError("TEACHER_API_KEY is not set.")
    if not model:
        raise RuntimeError("TEACHER_MODEL is not set.")

    return base_url, api_key, model


def validate_prompt(prompt: dict[str, Any]) -> tuple[str, str]:
    """Return (id, user message) or raise if the prompt row is malformed."""

    record_id = prompt.get("id")
    user_message = prompt.get("user")

    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError(f"Invalid id: {prompt}")
    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError(f"Invalid user message: id={record_id}")

    return record_id, user_message


def main() -> None:
    base_url, api_key, model = read_teacher_env()

    client = OpenAI(base_url=base_url, api_key=api_key)
    prompts = read_jsonl(settings.prompts_file)
    done = completed_ids(settings.dataset_file)

    logger.info("Teacher=%s prompts=%d already_done=%d", model, len(prompts), len(done))

    for index, prompt in enumerate(prompts, start=1):
        record_id, user_message = validate_prompt(prompt)

        if record_id in done:
            logger.info("Skip (done): %d/%d id=%s", index, len(prompts), record_id)
            continue

        logger.info("Generating: %d/%d id=%s", index, len(prompts), record_id)
        answer = ask_teacher(client, model, user_message)

        append_record(settings.dataset_file, record_id, user_message, answer)
        done.add(record_id)

        logger.info("Saved: id=%s answer_chars=%d", record_id, len(answer))

    logger.info("Dataset generation finished: %s", settings.dataset_file)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Dataset generation failed.")
        raise
