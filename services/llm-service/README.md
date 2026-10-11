# Mirror LLM service

`llm-service` is Mirror's model-serving boundary. It exposes the contracted OpenAI-compatible subset:

```text
GET  /health
GET  /metrics
POST /v1/chat/completions
```

The API gateway builds the prompt and calls this service. The gateway—not this service—owns deterministic text-only crisis handling, text emotion, visual gating, signal fusion, Mirror frontend SSE events, and persistence.

## Modes

| Mode | Build/run target | Purpose |
|---|---|---|
| Mock | default `mock` Docker target | Deterministic laptop and CI behavior with no GPU or model download. |
| Real | explicit `real` Docker target | vLLM serving Qwen with the Mirror LoRA adapter on a compatible NVIDIA GPU. |

Both modes use port `8002` and the same `/v1/chat/completions` request shape. Streaming responses use standard OpenAI-style SSE chunks and terminate with `data: [DONE]`.

## Local mock mode

Prerequisites: Docker and `uv`.

```bash
cd services/llm-service
uv sync --all-groups
uv run pytest -v
uv run ruff check .
docker build --tag mirror-llm-service:mock .
docker run --rm --name mirror-llm-mock -p 18002:8002 mirror-llm-service:mock
```

In another terminal:

```bash
curl http://localhost:18002/health
curl -sS http://localhost:18002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mirror-persona-v1","messages":[{"role":"user","content":"I am overwhelmed today."}]}'
curl -N http://localhost:18002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mirror-persona-v1","messages":[{"role":"user","content":"I am overwhelmed today."}],"stream":true}'
```

The mock reply is intentionally deterministic. It exercises the gateway integration path without asserting any model inference or emotional fact.

## Real GPU mode

Real mode is for an NVIDIA GPU host only. This development machine does not provide an NVIDIA runtime, so it cannot validate real inference.

1. On the approved GPU host, authenticate to GCP using that host's normal credential flow.
2. Download the adapter outside this repository and outside the image:

   ```bash
   gcloud storage cp --recursive gs://mirror-ac215-data/models/llm/adapter-v1 ./adapter-v1
   ```

3. Confirm NVIDIA prerequisites:

   ```bash
   nvidia-smi
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```

4. Build the GPU image on the GPU host and run it with the adapter mounted read-only. Mount a persistent Hugging Face cache so the public base model need not download each time:

   ```bash
   docker build --target real --tag mirror-llm-service:real .
   docker run --rm --gpus all --ipc=host \
     -p 18002:8002 \
     -v "$PWD/adapter-v1:/models/adapter-v1:ro" \
     -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
     mirror-llm-service:real
   ```

5. Run the same health, non-streaming, and streaming requests above. Record the GPU model, driver/CUDA version, vLLM image version, startup result, and one single-request latency in the PR or learning record.

The real-mode entrypoint uses:

```text
Qwen/Qwen2.5-3B-Instruct
--enable-lora
--lora-modules mirror-persona-v1=/models/adapter-v1
--max-lora-rank 32
--gpu-memory-utilization 0.9
--dtype auto
--max-model-len 2048
--max-num-seqs 1
```

The LoRA adapter, model cache, credentials, and any tokens must never be committed. `M3-13` will repeat this real-mode smoke test in the later GCP GPU VM deployment.

## Validation commands

```bash
uv lock --check
uv run ruff check .
uv run pytest -v
docker build --tag mirror-llm-service:mock .
```

## Configuration

Copy `.env.example` only for local non-secret configuration. Do not commit a `.env` file. `MOCK_MODE` documents the active run mode; the Docker target determines whether mock or real server software is present.
