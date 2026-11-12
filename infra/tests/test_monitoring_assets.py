#!/usr/bin/env python3
"""Fail-closed checks for the M4-08 monitoring assets (Prometheus + Grafana).

Run in CI with PyYAML pinned:
    uv run --no-project --with pyyaml==6.0.2 python infra/tests/test_monitoring_assets.py

Checks:
- prometheus.yml, the Grafana provisioning files and infra/compose.yml parse;
- Prometheus scrapes exactly api-gateway:8000/metrics;
- Grafana provisions that Prometheus as datasource uid `mirror-prometheus`, and
  every dashboard panel and target uses that uid;
- every metric a dashboard query names is declared in the gateway's
  app/metrics.py (a renamed or removed metric fails here, not silently in Grafana);
- the monitoring services stay opt-in and non-public: Prometheus has no host
  port, Grafana binds to 127.0.0.1 only, and Grafana's login is disabled.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "infra" / "monitoring"
PROMETHEUS = MONITORING / "prometheus.yml"
DASHBOARD = MONITORING / "grafana" / "mirror-gateway.json"
DATASOURCES = MONITORING / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
PROVIDERS = MONITORING / "grafana" / "provisioning" / "dashboards" / "mirror.yml"
COMPOSE = ROOT / "infra" / "compose.yml"
GATEWAY_METRICS = ROOT / "services" / "api-gateway" / "app" / "metrics.py"

DATASOURCE_UID = "mirror-prometheus"
DASHBOARD_MOUNT = "/var/lib/grafana/dashboards"

# Suffixes Prometheus adds to a histogram's series.
HISTOGRAM_SUFFIXES = ("_bucket", "_count", "_sum")
# PromQL words that look like identifiers but are not metric names.
PROMQL_WORDS = {
    "sum", "rate", "increase", "by", "without", "histogram_quantile", "clamp_min",
    "clamp_max", "avg", "max", "min", "count", "le", "on", "ignoring", "and", "or",
    "unless", "offset", "irate", "topk", "bottomk",
}


def load_yaml(path: Path) -> dict:
    assert path.is_file(), f"missing monitoring asset: {path.relative_to(ROOT)}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.relative_to(ROOT)} must be a YAML mapping"
    return data


def declared_gateway_series() -> set[str]:
    """Series names the gateway exposes, from the Counter/Histogram declarations."""
    text = GATEWAY_METRICS.read_text(encoding="utf-8")
    series: set[str] = set()
    for kind, name in re.findall(r'\b(Counter|Histogram|Gauge)\(\s*"([a-z_:][a-z0-9_:]*)"', text):
        if kind == "Histogram":
            series.update(name + suffix for suffix in HISTOGRAM_SUFFIXES)
        elif kind == "Counter" and not name.endswith("_total"):
            series.add(name + "_total")
        else:
            series.add(name)
    assert series, "found no metric declarations in services/api-gateway/app/metrics.py"
    return series


def metric_names(expr: str) -> set[str]:
    # Drop label matchers ({...}), label lists in by (...) and range selectors ([5m]).
    stripped = re.sub(r"\{[^}]*\}", "", expr)
    stripped = re.sub(r"\b(by|without|on|ignoring)\s*\([^)]*\)", "", stripped)
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)
    names = set(re.findall(r"\b[a-zA-Z_:][a-zA-Z0-9_:]*\b", stripped))
    return {n for n in names if n not in PROMQL_WORDS and not re.fullmatch(r"\d.*|e\d+", n)}


def test_prometheus_scrapes_only_the_gateway() -> None:
    config = load_yaml(PROMETHEUS)
    jobs = config.get("scrape_configs") or []
    assert len(jobs) == 1, "prometheus.yml must define exactly one scrape job (the gateway)"
    job = jobs[0]
    assert job.get("metrics_path", "/metrics") == "/metrics"
    targets = [t for sc in job.get("static_configs", []) for t in sc.get("targets", [])]
    assert targets == ["api-gateway:8000"], f"unexpected scrape targets: {targets}"


def test_grafana_provisions_the_prometheus_datasource() -> None:
    sources = load_yaml(DATASOURCES).get("datasources") or []
    assert len(sources) == 1, "provision exactly one datasource"
    source = sources[0]
    assert source.get("uid") == DATASOURCE_UID
    assert source.get("type") == "prometheus"
    assert source.get("url") == "http://prometheus:9090"
    assert source.get("editable") is False

    providers = load_yaml(PROVIDERS).get("providers") or []
    assert len(providers) == 1 and providers[0].get("type") == "file"
    assert providers[0].get("options", {}).get("path") == DASHBOARD_MOUNT
    assert providers[0].get("allowUiUpdates") is False


def test_dashboard_uses_the_provisioned_datasource_and_declared_metrics() -> None:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dashboard.get("uid") == "mirror-gateway"
    panels = dashboard.get("panels") or []
    assert panels, "the dashboard has no panels"

    declared = declared_gateway_series()
    for panel in panels:
        title = panel.get("title", "<untitled>")
        assert panel.get("datasource", {}).get("uid") == DATASOURCE_UID, (
            f"panel {title!r} must use datasource uid {DATASOURCE_UID!r}"
        )
        targets = panel.get("targets") or []
        assert targets, f"panel {title!r} has no queries"
        for target in targets:
            uid = target.get("datasource", {}).get("uid", DATASOURCE_UID)
            assert uid == DATASOURCE_UID, f"a query in {title!r} uses datasource {uid!r}"
            names = metric_names(target.get("expr", ""))
            assert names, f"a query in {title!r} names no metric"
            unknown = names - declared
            assert not unknown, (
                f"panel {title!r} queries metrics the gateway does not declare: {sorted(unknown)}"
            )


def test_monitoring_services_are_opt_in_and_not_public() -> None:
    services = load_yaml(COMPOSE).get("services") or {}
    for name in ("prometheus", "grafana"):
        assert name in services, f"infra/compose.yml has no {name} service"
        assert services[name].get("profiles") == ["monitoring"], f"{name} must be opt-in"
        image = services[name].get("image", "")
        assert re.fullmatch(r"[\w./-]+:v?\d+\.\d+\.\d+", image), f"{name} image must pin a version"

    assert "ports" not in services["prometheus"], "Prometheus must not publish a host port"
    grafana_ports = services["grafana"].get("ports") or []
    assert grafana_ports and all(str(p).startswith("127.0.0.1:") for p in grafana_ports), (
        "Grafana may only listen on 127.0.0.1"
    )
    env = services["grafana"].get("environment") or {}
    assert env.get("GF_AUTH_DISABLE_LOGIN_FORM") == "true"
    assert env.get("GF_AUTH_BASIC_ENABLED") == "false"
    assert env.get("GF_AUTH_ANONYMOUS_ORG_ROLE") == "Viewer"

    mounts = " ".join(services["grafana"].get("volumes") or [])
    assert "./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro" in mounts
    assert f"./monitoring/grafana/mirror-gateway.json:{DASHBOARD_MOUNT}/mirror-gateway.json:ro" in mounts


def main() -> int:
    tests = [obj for name, obj in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
