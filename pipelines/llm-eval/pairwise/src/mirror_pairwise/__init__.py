"""M4-09 blind pairwise preference: rater sees A and B only; the key stays sealed until tallying."""

# First run (agreed on #100, Nov 14): plain Qwen without vs with the camera note in the prompt.
# Since D-006 production serves plain Qwen with no adapter, and this is the question that matters now.
FIRST_RUN_PAIRS = (("plain", "plain_camera"),)

# The original board design, kept for a later run if an adapter is ever served again:
# base vs LoRA, base vs LoRA + visual context, LoRA vs LoRA + visual.
LORA_PAIRS = (("base", "lora"), ("base", "lora_visual"), ("lora", "lora_visual"))

PAIRS = FIRST_RUN_PAIRS
