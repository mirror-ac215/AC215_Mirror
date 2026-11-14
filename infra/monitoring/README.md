# Monitoring (M4-08)

Prometheus scrapes the api-gateway's `/metrics` (M3-15). Grafana reads Prometheus and shows
`grafana/mirror-gateway.json`.

## Panels
- **Requests per second by status:** traffic and error codes.
- **Latency p95 by route:** from `mirror_gateway_request_seconds`. For streams it is time to the first byte.
- **Gate pass-rate:** share of turns with gate status `ok` (`mirror_gateway_gate_total`).
  Shows 0% when there are turns but none passed (e.g. camera off); "No data" only when there are no turns.
- **Text-emotion fallback rate:** messages sent without a text reading, out of all messages.
  The denominator is scored messages plus fallbacks, since the gateway counts them separately.
  Both percent panels use "Percent (0.0-1.0)" with the axis fixed at 0 to 1 (0% to 100%).
- **Crisis hits by rule:** count per hour, from `mirror_gateway_crisis_hits_total`.
- **Fusion outcomes by agreement:** `agree`, `disagree` or `n/a` per hour.
- **Gate outcomes per hour (stacked):** `ok`, `uncertain`, `dropped` and `camera_off` in one stacked view, so the mix and the volume both show.
- **Fixed safety replies per hour (stacked):** crisis, medication and camera-question replies from `mirror_gateway_*_hits_total`. This shows how often the fixed replies fire.

## Run it locally

Prometheus and Grafana are opt-in (`monitoring` profile in `infra/compose.yml`) and not public:
Prometheus has no host port and scrapes `api-gateway:8000/metrics` on the compose network;
Grafana listens on `127.0.0.1:3001` only, with login disabled and a read-only anonymous view.
Grafana provisions the Prometheus datasource (uid `mirror-prometheus`) and this dashboard from
`grafana/provisioning/`, therefore nothing is imported by hand.

From the repository root:

```bash
docker compose -f infra/compose.yml --profile monitoring up --build -d
```

Then open http://localhost:3001. Send a few chat messages first, or the panels stay empty.
Stop with `docker compose -f infra/compose.yml --profile monitoring down`.

## Tests

- `infra/tests/test_monitoring_assets.py` (CI, fail-closed): parses every asset, checks the scrape
  target, the datasource uid on every panel, that the dashboard queries only metrics declared in
  `services/api-gateway/app/metrics.py`, and that both services stay opt-in and non-public.
- `infra/tests/test_compose_monitoring.sh` (CI compose smoke): the gateway target is `up`, every
  dashboard query evaluates in Prometheus, and Grafana serves the dashboard and reads the datasource.

## Evidence

`docs/evidence/m4_08_grafana_dashboard.png`: the dashboard on the local stack after a few chat
turns (no patient content, no public endpoint, no cloud metadata).
