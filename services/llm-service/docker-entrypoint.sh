#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  mode="$1"
else
  case "${MOCK_MODE:-1}" in
    1|true|TRUE|yes|YES) mode="mock" ;;
    0|false|FALSE|no|NO) mode="real" ;;
    *)
      echo "Invalid MOCK_MODE: ${MOCK_MODE}. Use 1/0 or true/false." >&2
      exit 64
      ;;
  esac
fi

case "$mode" in
  mock)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8002}"
    ;;
  real)
    # Serves the plain base model unless LORA_ADAPTER_PATH is set (D-006).
    set --
    if [ -n "${LORA_ADAPTER_PATH:-}" ]; then
      if [ ! -d "$LORA_ADAPTER_PATH" ]; then
        echo "LoRA adapter directory not found at $LORA_ADAPTER_PATH." >&2
        exit 1
      fi
      set -- \
        --enable-lora \
        --lora-modules "${SERVED_MODEL_NAME:-mirror-persona-v1}=$LORA_ADAPTER_PATH" \
        --max-lora-rank "${MAX_LORA_RANK:-32}"
    fi

    exec vllm serve "${MODEL_NAME:-Qwen/Qwen2.5-3B-Instruct}" \
      --served-model-name "${SERVED_MODEL_NAME:-mirror-persona-v1}" \
      --host 0.0.0.0 \
      --port "${PORT:-8002}" \
      --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.9}" \
      --dtype "${DTYPE:-auto}" \
      --max-model-len "${MAX_MODEL_LEN:-2048}" \
      --max-num-seqs "${MAX_NUM_SEQS:-1}" \
      "$@"
    ;;
  *)
    echo "Unknown serving mode: $mode (expected mock or real)." >&2
    exit 64
    ;;
esac
