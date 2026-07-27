"""Interactive check of the distilled student (4bit base + LoRA adapter)."""

import logging

import torch
from peft import PeftModel
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

from config import settings
from persona import SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

MAX_NEW_TOKENS = 192
TEMPERATURE = 0.7
TOP_P = 0.9
REPETITION_PENALTY = 1.1
EXIT_COMMANDS = {"exit", "quit"}


def load_model() -> tuple[PeftModel, AutoTokenizer]:
    """Attach the trained LoRA adapter to the 4bit base model."""

    if not torch.cuda.is_available():
        raise RuntimeError("A CUDA capable GPU is required.")

    if not settings.output_dir.exists():
        raise FileNotFoundError(f"LoRA adapter not found: {settings.output_dir}")

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        str(settings.student_dir),
        quantization_config=quantization_config,
        device_map={"": 0},
        dtype=compute_dtype,
    )

    model = PeftModel.from_pretrained(base_model, str(settings.output_dir))
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(str(settings.output_dir), use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    logger.info("Model loaded: %s", settings.student_dir)
    return model, tokenizer


def generate_answer(
    model: PeftModel,
    tokenizer: AutoTokenizer,
    user_message: str,
) -> str:
    """Generate a single reply for one user message."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
        enable_thinking=False,
    ).to(model.device)

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    new_tokens = output_ids[0, inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def main() -> None:
    model, tokenizer = load_model()

    print("ロギー起動。終了は exit")

    while True:
        user_message = input("あなた > ").strip()
        if not user_message:
            continue
        if user_message.lower() in EXIT_COMMANDS:
            break

        try:
            print(f"ロギー > {generate_answer(model, tokenizer, user_message)}")
        except Exception:
            logger.exception("Reply generation failed.")
            print("ロギー > エラーが発生しました。ログを確認してください。")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Chat startup failed.")
        raise
