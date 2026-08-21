"""Fine-tune the one unified generative model with SFT/LoRA/QLoRA or DPO."""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["lora", "qlora", "full-sft", "dpo"], default="qlora")
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "genai_training")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "unified_genai_adapter")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    args = parser.parse_args()

    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import BitsAndBytesConfig
        from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer
    except ImportError as error:
        raise SystemExit("Install requirements-genai-training.txt before training.") from error

    args.output.mkdir(parents=True, exist_ok=True)
    peft_config = None
    quantization_config = None
    if args.method in {"lora", "qlora", "dpo"}:
        peft_config = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules="all-linear",
        )
    if args.method == "qlora":
        if not torch.cuda.is_available():
            raise SystemExit("QLoRA requires a compatible CUDA GPU and bitsandbytes.")
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    common = dict(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=2e-4 if peft_config else 2e-5,
        logging_steps=1,
        save_strategy="epoch",
        report_to="none",
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
    )
    if args.method == "dpo":
        dataset = load_dataset("json", data_files=str(args.data / "preference.jsonl"), split="train")
        config = DPOConfig(**common, max_length=2048)
        trainer = DPOTrainer(
            model=args.model,
            args=config,
            train_dataset=dataset,
            peft_config=peft_config,
        )
    else:
        dataset = load_dataset("json", data_files=str(args.data / "sft.jsonl"), split="train")
        config = SFTConfig(
            **common,
            max_length=2048,
            packing=False,
            model_init_kwargs={"quantization_config": quantization_config} if quantization_config else None,
        )
        trainer = SFTTrainer(
            model=args.model,
            args=config,
            train_dataset=dataset,
            peft_config=peft_config,
        )
    trainer.train()
    trainer.save_model(str(args.output))
    print(f"Saved {args.method} output to {args.output.resolve()}")


if __name__ == "__main__":
    main()
