"""Download the student weights into the project.

The shared Hugging Face cache cannot be used here: creating it requires
symlink privileges that this Windows account does not have (WinError 1314).
`local_dir` copies real files instead, so the download works without
Developer Mode or an elevated shell.
"""

import logging

from huggingface_hub import snapshot_download

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Weights, tokenizer and configs only: no ONNX or GGUF variants.
ALLOWED_PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.py", "*.md"]


def main() -> None:
    settings.student_dir.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading %s -> %s", settings.student_model_id, settings.student_dir)

    snapshot_download(
        repo_id=settings.student_model_id,
        local_dir=str(settings.student_dir),
        allow_patterns=ALLOWED_PATTERNS,
    )

    logger.info("Download finished: %s", settings.student_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Student download failed.")
        raise
