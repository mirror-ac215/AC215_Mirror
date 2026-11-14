"""M4-09 blind pairwise preference: rater sees A and B only; the key stays sealed until tallying."""

# The three pairs from the board: base vs LoRA, base vs LoRA + visual context, LoRA vs LoRA + visual.
PAIRS = (("base", "lora"), ("base", "lora_visual"), ("lora", "lora_visual"))
