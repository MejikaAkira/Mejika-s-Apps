"""Central settings for the LLM response distillation pipeline."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """All tunable values live here so scripts stay free of magic numbers."""

    root_dir: Path = Path(__file__).resolve().parent

    prompts_file: Path = root_dir / "prompts.jsonl"
    dataset_file: Path = root_dir / "data" / "distilled.jsonl"
    output_dir: Path = root_dir / "outputs" / "student-lora"

    # Student that fits comfortably in 6GB VRAM when loaded in 4bit.
    # Weights live in the project because the shared HF cache needs symlink
    # privileges this Windows account does not have. See download_student.py.
    student_model_id: str = "Qwen/Qwen3-0.6B"
    student_dir: Path = root_dir / "models" / "Qwen3-0.6B"

    # Teacher generation limits (guards against runaway token billing).
    teacher_max_tokens: int = 512
    teacher_temperature: float = 0.7
    teacher_max_retries: int = 3

    # Conservative training settings for RTX 3060 Laptop 6GB.
    # 1024, not the guide's 512: the persona system prompt alone is ~750 tokens,
    # so 512 truncates every completion away and TRL then drops all samples
    # (train_dataset becomes empty). Measured maximum is 846 tokens.
    max_length: int = 1024
    epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 1
    gradient_accumulation_steps: int = 8

    # Small LoRA keeps the optimizer state tiny.
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05

    seed: int = 42


settings = Settings()
