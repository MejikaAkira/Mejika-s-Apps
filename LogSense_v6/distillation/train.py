"""4bit QLoRA fine-tuning of the student model on RTX 3060 6GB."""

import logging
import random

import numpy as np
import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    set_seed,
)
from trl import SFTConfig, SFTTrainer

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

EVAL_RATIO = 0.1
SMALL_DATASET_WARNING_SIZE = 10
BYTES_PER_GIB = 1024**3

LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def set_reproducible_seed() -> None:
    """Fix every random source we depend on."""

    random.seed(settings.seed)
    np.random.seed(settings.seed)
    torch.manual_seed(settings.seed)
    set_seed(settings.seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(settings.seed)


def log_gpu_memory(label: str) -> None:
    """Report VRAM usage so OOM causes are easy to spot."""

    if not torch.cuda.is_available():
        return

    logger.info(
        "%s | VRAM allocated=%.2fGB reserved=%.2fGB",
        label,
        torch.cuda.memory_allocated() / BYTES_PER_GIB,
        torch.cuda.memory_reserved() / BYTES_PER_GIB,
    )


def load_split_dataset() -> tuple[Dataset, Dataset]:
    """Load the distilled JSONL and split it into train/eval."""

    if not settings.dataset_file.exists():
        raise FileNotFoundError(f"Training data not found: {settings.dataset_file}")

    dataset = load_dataset(
        "json",
        data_files=str(settings.dataset_file),
        split="train",
    )

    if len(dataset) < SMALL_DATASET_WARNING_SIZE:
        logger.warning(
            "Fewer than %d records: smoke test only.", SMALL_DATASET_WARNING_SIZE
        )

    for column in ("id", "category"):
        if column in dataset.column_names:
            dataset = dataset.remove_columns([column])

    test_size = max(1, round(len(dataset) * EVAL_RATIO))
    split = dataset.train_test_split(
        test_size=test_size,
        seed=settings.seed,
        shuffle=True,
    )

    logger.info("Split: train=%d eval=%d", len(split["train"]), len(split["test"]))
    return split["train"], split["test"]


def pick_compute_dtype() -> torch.dtype:
    """bf16 where the GPU supports it, fp16 otherwise."""

    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def build_tokenizer() -> AutoTokenizer:
    """Load the student tokenizer with padding configured for training."""

    tokenizer = AutoTokenizer.from_pretrained(str(settings.student_dir), use_fast=True)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    return tokenizer


def build_quantized_model(compute_dtype: torch.dtype) -> AutoModelForCausalLM:
    """Load the student in 4bit NF4 and prepare it for LoRA training."""

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        # Quantize the quantization constants as well: saves ~0.4GB.
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model = AutoModelForCausalLM.from_pretrained(
        str(settings.student_dir),
        quantization_config=quantization_config,
        device_map={"": 0},
        dtype=compute_dtype,
    )

    model = prepare_model_for_kbit_training(model)

    # Trade compute for activation memory: required at 6GB.
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    return model


def build_lora_config() -> LoraConfig:
    """Small LoRA adapter, the only part that receives gradients."""

    return LoraConfig(
        r=settings.lora_rank,
        lora_alpha=settings.lora_alpha,
        lora_dropout=settings.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=LORA_TARGET_MODULES,
    )


def build_training_args() -> SFTConfig:
    """Training settings tuned for 6GB VRAM."""

    use_bf16 = torch.cuda.is_bf16_supported()

    return SFTConfig(
        output_dir=str(settings.output_dir),
        num_train_epochs=settings.epochs,
        learning_rate=settings.learning_rate,
        per_device_train_batch_size=settings.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=settings.gradient_accumulation_steps,
        max_length=settings.max_length,
        completion_only_loss=True,
        packing=False,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        logging_steps=1,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        bf16=use_bf16,
        fp16=not use_bf16,
        report_to="none",
        seed=settings.seed,
        dataloader_num_workers=0,
    )


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("A CUDA capable GPU is required.")

    set_reproducible_seed()
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("GPU=%s", torch.cuda.get_device_name(0))
    logger.info("Student=%s", settings.student_dir)

    train_dataset, eval_dataset = load_split_dataset()
    tokenizer = build_tokenizer()
    model = build_quantized_model(pick_compute_dtype())

    log_gpu_memory("before training")

    trainer = SFTTrainer(
        model=model,
        args=build_training_args(),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=build_lora_config(),
    )

    result = trainer.train()
    logger.info("Training finished: %s", result.metrics)

    trainer.save_model(str(settings.output_dir))
    tokenizer.save_pretrained(str(settings.output_dir))

    logger.info("Evaluation: %s", trainer.evaluate())
    log_gpu_memory("after training")


if __name__ == "__main__":
    try:
        main()
    except torch.OutOfMemoryError:
        logger.exception(
            "CUDA OOM. Lower max_length to 256 and lora_rank to 4, then retry."
        )
        raise
    except Exception:
        logger.exception("Training failed.")
        raise
