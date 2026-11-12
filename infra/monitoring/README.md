# Monitoring (M4-08)

Prometheus scrapes the api-gateway's `/metrics` (M3-15). Grafana reads Prometheus and shows
`grafana/mirror-gateway.json`.

## Panels
- **Requests per second by status:** traffic and error codes.
- **Latency p95 by route:** from `mirror_gateway_request_seconds`. For streams it is time to the first byte.
- **Gate pass-rate:** share of turns with gate status `ok` (`mirror_gateway_gate_total`).
- **Text-emotion fallback rate:** messages sent without a text reading, out of all messages.
  The denominator is scored messages plus fallbacks, since the gateway counts them separately.
- **Crisis hits by rule:** count per hour, from `mirror_gateway_crisis_hits_total`.
- **Fusion outcomes by agreement:** `agree`, `disagree` or `n/a` per hour.

## Not yet done
- Wiring Prometheus and Grafana into `infra/compose.yml` (Owen helps with the Prometheus container).
- The screenshot for the M4-08 definition of done, once the stack runs.
