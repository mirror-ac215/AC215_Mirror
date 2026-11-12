#!/usr/bin/env bash
# M4-08 smoke test: Prometheus scrapes the running gateway and Grafana serves the
# provisioned dashboard from it. CI starts the stack with `--profile monitoring`
# and runs test_compose_chat.sh first, therefore the gateway has real traffic.
set -euo pipefail

compose=(docker compose -f infra/compose.yml --profile monitoring)
dashboard=infra/monitoring/grafana/mirror-gateway.json
grafana=http://127.0.0.1:3001

prom_get() {
  # Prometheus has no host port: query it from inside its own container.
  "${compose[@]}" exec -T prometheus wget -qO- "http://localhost:9090$1"
}

# 1. The gateway scrape target is up (first scrape can take one interval).
for attempt in $(seq 1 12); do
  targets=$(prom_get '/api/v1/targets?state=active')
  if python3 - "$targets" <<'PY'
import json, sys
active = json.loads(sys.argv[1])["data"]["activeTargets"]
gateway = [t for t in active if t["labels"].get("job") == "mirror-api-gateway"]
sys.exit(0 if gateway and all(t["health"] == "up" for t in gateway) else 1)
PY
  then
    echo "PASS Prometheus target mirror-api-gateway is up"
    break
  fi
  if [ "$attempt" -eq 12 ]; then
    echo "FAIL Prometheus target mirror-api-gateway is not up:" >&2
    echo "$targets" >&2
    exit 1
  fi
  sleep 5
done

# 2. The scraped data includes the chat turns from test_compose_chat.sh.
for attempt in $(seq 1 6); do
  result=$(prom_get '/api/v1/query?query=sum(mirror_gateway_requests_total)')
  if python3 -c 'import json,sys; r=json.loads(sys.argv[1])["data"]["result"]; sys.exit(0 if r and float(r[0]["value"][1]) > 0 else 1)' "$result"; then
    echo "PASS Prometheus has gateway request samples"
    break
  fi
  if [ "$attempt" -eq 6 ]; then
    echo "FAIL no mirror_gateway_requests_total samples: $result" >&2
    exit 1
  fi
  sleep 5
done

# 3. Every dashboard query is valid PromQL against the live Prometheus.
while IFS= read -r expr; do
  encoded=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$expr")
  response=$(prom_get "/api/v1/query?query=${encoded}")
  python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1])["status"] == "success" else 1)' "$response" \
    || { echo "FAIL dashboard query rejected by Prometheus: $expr" >&2; exit 1; }
done < <(python3 -c '
import json, sys
for panel in json.load(open(sys.argv[1]))["panels"]:
    for target in panel.get("targets", []):
        print(target["expr"])
' "$dashboard")
echo "PASS every dashboard query evaluates in Prometheus"

# 4. Grafana is healthy, the dashboard is provisioned, and the datasource answers.
curl -fsS "$grafana/api/health" >/dev/null
curl -fsS "$grafana/api/dashboards/uid/mirror-gateway" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)["dashboard"]; assert d["title"] == "Mirror api-gateway", d["title"]'
echo "PASS Grafana serves the provisioned dashboard"

query='{"queries":[{"refId":"A","datasource":{"type":"prometheus","uid":"mirror-prometheus"},"expr":"up{job=\"mirror-api-gateway\"}","instant":true}],"from":"now-5m","to":"now"}'
curl -fsS -H 'Content-Type: application/json' -d "$query" "$grafana/api/ds/query" \
  | python3 -c '
import json, sys
result = json.load(sys.stdin)["results"]["A"]
assert result.get("status", 200) == 200 and not result.get("error"), result
values = [v for frame in result["frames"] for v in frame["data"]["values"][-1]]
assert values and all(v == 1 for v in values), values
'
echo "PASS Grafana reads up{job=\"mirror-api-gateway\"} = 1 through the provisioned datasource"

# 5. Login stays disabled (read-only view).
status=$(curl -s -o /dev/null -w '%{http_code}' -u admin:admin "$grafana/api/admin/settings")
if [ "$status" = "200" ]; then
  echo "FAIL Grafana accepted the default admin login" >&2
  exit 1
fi
echo "PASS Grafana rejects admin login (HTTP $status)"
