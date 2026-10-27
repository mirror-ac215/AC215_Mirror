"""QLoRA training run: 4-bit Qwen2.5-3B-Instruct + a new LoRA adapter, tracked in W&B.

torch / transformers / peft / trl are imported inside run(): the rest of the
package (and its tests) works without a GPU stack installed.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mirror_llm_finetune.config import check, gcs_to_fuse
from mirror_llm_finetune.data import fingerprint, read_split, to_example


def adapter_metadata(params: dict[str, Any], data_sha: str, run_url: str | None) -> dict[str, Any]:
    """Written next to the adapter: what it was trained from, for reproducibility."""
    return {
        "adapter_name": params["output"]["adapter_name"],
        "base_model": params["base_model"]["name"],
        "base_revision": params["base_model"]["revision"],
        "data_version": params["data"]["version"],
        "data_sha256": data_sha,
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "wandb_run": run_url,
        "lora": params["lora"],
        "training": params["training"],
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def run(params: dict[str, Any], data_dir: Path, out_dir: Path, upload: bool) -> Path:
    check(params, for_training=True)
    target = Path(gcs_to_fuse(params["output"]["gcs_prefix"])) / params["output"]["adapter_name"]
    if upload and target.exists():
        # Adapters are versioned, never overwritten: bump output.adapter_name instead.
        raise FileExistsError(f"{target} already exists")

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    system = params["system_prompt"]
    train = Dataset.from_list([to_example(r, system) for r in read_split(data_dir, "train")])
    val = Dataset.from_list([to_example(r, system) for r in read_split(data_dir, "val")])

    base, quant, t = params["base_model"], params["quantization"], params["training"]
    dtype = getattr(torch, quant["compute_dtype"])
    tokenizer = AutoTokenizer.from_pretrained(base["name"], revision=base["revision"])
    model = AutoModelForCausalLM.from_pretrained(
        base["name"],
        revision=base["revision"],
        dtype=dtype,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=quant["load_in_4bit"],
            bnb_4bit_quant_type=quant["quant_type"],
            bnb_4bit_compute_dtype=dtype,
        ),
    )
    lora = params["lora"]
    peft_config = LoraConfig(
        r=lora["r"],
        lora_alpha=lora["alpha"],
        lora_dropout=lora["dropout"],
        target_modules=lora["target_modules"],
        task_type="CAUSAL_LM",
    )
    os.environ.setdefault("WANDB_PROJECT", params["wandb"]["project"])
    args = SFTConfig(
        output_dir=str(out_dir / "checkpoints"),
        run_name=params["output"]["adapter_name"],
        report_to="wandb",
        seed=t["seed"],
        num_train_epochs=t["epochs"],
        learning_rate=t["learning_rate"],
        per_device_train_batch_size=t["batch_size"],
        gradient_accumulation_steps=t["grad_accum"],
        max_length=t["max_length"],
        warmup_steps=t["warmup_ratio"],  # transformers 5: a float < 1 is a ratio of all steps
        lr_scheduler_type=t["lr_scheduler"],
        completion_only_loss=True,  # learn Mirror's replies, not the prompts
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,  # keep the epoch with the lowest val loss
        bf16=dtype == torch.bfloat16,
        fp16=dtype == torch.float16,
        logging_steps=5,
    )
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=train,
        eval_dataset=val,
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train()

    adapter_dir = out_dir / params["output"]["adapter_name"]
    trainer.save_model(str(adapter_dir))  # adapter weights + config only, not the base model
    tokenizer.save_pretrained(str(adapter_dir))
    import wandb

    run_url = wandb.run.url if wandb.run else None
    meta = adapter_metadata(params, fingerprint(data_dir), run_url)
    (adapter_dir / "mirror_adapter.json").write_text(json.dumps(meta, indent=2) + "\n")
    if upload:
        shutil.copytree(adapter_dir, target)
    return adapter_dir
