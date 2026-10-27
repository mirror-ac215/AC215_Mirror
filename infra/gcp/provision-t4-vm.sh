#!/usr/bin/env bash
# Provision one fail-closed, manually-operated M3-13 GPU VM.
set -euo pipefail

require() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'Required environment variable %s is not set.\n' "$name" >&2
    exit 64
  fi
}

fail_drift() {
  printf '%s drift detected; refusing to reuse the existing resource.\n' "$1" >&2
  exit 65
}

validate_public_source_ranges() {
  python3 - "$1" <<'PY'
import ipaddress
import sys

raw_ranges = sys.argv[1].split(",")
normalized_ranges = []
for raw_range in raw_ranges:
    value = raw_range.strip()
    if not value:
        print("M3_13_PUBLIC_SOURCE_RANGES must name approved narrow source ranges, not Internet-wide access.", file=sys.stderr)
        raise SystemExit(64)
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        print("M3_13_PUBLIC_SOURCE_RANGES must name approved narrow source ranges, not Internet-wide access.", file=sys.stderr)
        raise SystemExit(64)
    minimum_prefix = 24 if network.version == 4 else 64
    if network.prefixlen < minimum_prefix:
        print("M3_13_PUBLIC_SOURCE_RANGES must name approved narrow source ranges, not Internet-wide access.", file=sys.stderr)
        raise SystemExit(64)
    normalized_ranges.append(str(network))

print(",".join(normalized_ranges))
PY
}

for variable in M3_13_PROJECT_ID M3_13_ZONE M3_13_SERVICE_ACCOUNT_EMAIL M3_13_PUBLIC_SOURCE_RANGES; do
  require "$variable"
done

M3_13_REGION="${M3_13_REGION:-${M3_13_ZONE%-*}}"
M3_13_VM_NAME="${M3_13_VM_NAME:-mirror-gpu-prod}"
M3_13_ADDRESS_NAME="${M3_13_ADDRESS_NAME:-mirror-gpu-prod-ip}"
M3_13_NETWORK="${M3_13_NETWORK:-mirror-stage-a-vpc}"
M3_13_SUBNETWORK="${M3_13_SUBNETWORK:-mirror-stage-a-subnet}"
M3_13_SUBNET_RANGE="${M3_13_SUBNET_RANGE:-10.42.0.0/24}"
M3_13_MACHINE_TYPE="${M3_13_MACHINE_TYPE:-n1-standard-4}"
M3_13_BOOT_DISK_SIZE="${M3_13_BOOT_DISK_SIZE:-100GB}"
M3_13_IMAGE_FAMILY="${M3_13_IMAGE_FAMILY:-ubuntu-2204-lts}"
M3_13_IMAGE_PROJECT="${M3_13_IMAGE_PROJECT:-ubuntu-os-cloud}"
M3_13_HTTP_FIREWALL_RULE="${M3_13_HTTP_FIREWALL_RULE:-mirror-allow-public-http}"
M3_13_HTTPS_FIREWALL_RULE="${M3_13_HTTPS_FIREWALL_RULE:-mirror-allow-public-https}"
M3_13_IAP_SSH_FIREWALL_RULE="${M3_13_IAP_SSH_FIREWALL_RULE:-mirror-allow-iap-ssh}"
M3_13_PUBLIC_SOURCE_RANGES="$(validate_public_source_ranges "$M3_13_PUBLIC_SOURCE_RANGES")"

if [[ "$M3_13_NETWORK" == "default" ]]; then
  printf 'Refusing to use GCP default VPC; select a dedicated custom VPC.\n' >&2
  exit 64
fi

PROJECT_ARGS=(--project "$M3_13_PROJECT_ID")

validate_firewall_rule() {
  local rule="$1" source_range="$2" port="$3" target_tag="$4"
  gcloud compute firewall-rules describe "$rule" "${PROJECT_ARGS[@]}" --format=json | \
    python3 -c '
import json, sys
rule, network, source, port, tag = sys.argv[1:]
d = json.load(sys.stdin)
allowed = d.get("allowed", [])
expected_sources = sorted(item.strip() for item in source.split(",") if item.strip())
ok = (
    d.get("network", "").rsplit("/", 1)[-1] == network
    and d.get("direction") == "INGRESS"
    and d.get("disabled") is False
    and sorted(d.get("sourceRanges", [])) == expected_sources
    and sorted(d.get("targetTags", [])) == [tag]
    and len(allowed) == 1
    and allowed[0].get("IPProtocol") == "tcp"
    and sorted(allowed[0].get("ports", [])) == [port]
)
if not ok:
    raise SystemExit(f"Firewall rule drift: {rule} is not the required narrow ingress rule")
' "$rule" "$M3_13_NETWORK" "$source_range" "$port" "$target_tag"
}

ensure_firewall_rule() {
  local rule="$1" source_range="$2" port="$3" target_tag="$4"
  if gcloud compute firewall-rules describe "$rule" "${PROJECT_ARGS[@]}" >/dev/null 2>&1; then
    validate_firewall_rule "$rule" "$source_range" "$port" "$target_tag"
    printf 'Validated firewall rule %s.\n' "$rule"
  else
    gcloud compute firewall-rules create "$rule" "${PROJECT_ARGS[@]}" \
      --network "$M3_13_NETWORK" --direction INGRESS --action ALLOW \
      --rules "tcp:$port" --source-ranges "$source_range" --target-tags "$target_tag" \
      --description "Mirror M3-13 Stage A managed ingress rule"
  fi
}

validate_effective_ingress() {
  gcloud compute firewall-rules list "${PROJECT_ARGS[@]}" \
    --filter="network:$M3_13_NETWORK AND direction=INGRESS AND disabled=false" --format=json | \
    python3 -c '
import json, sys
managed_rules = set(sys.argv[1:])
for rule in json.load(sys.stdin):
    name = rule.get("name", "<unnamed>")
    target_tags = set(rule.get("targetTags", []))
    if name not in managed_rules and rule.get("allowed") and (
        not target_tags or {"mirror-public", "mirror-iap-ssh"}.intersection(target_tags)
    ):
        raise SystemExit(
            f"Non-managed ALLOW ingress rule {name} could apply to the Stage A VM; refusing VPC reuse"
        )
' "$M3_13_HTTP_FIREWALL_RULE" "$M3_13_HTTPS_FIREWALL_RULE" "$M3_13_IAP_SSH_FIREWALL_RULE"
}

gcloud services enable compute.googleapis.com "${PROJECT_ARGS[@]}"

if gcloud compute networks describe "$M3_13_NETWORK" "${PROJECT_ARGS[@]}" >/dev/null 2>&1; then
  [[ "$(gcloud compute networks describe "$M3_13_NETWORK" "${PROJECT_ARGS[@]}" --format='value(autoCreateSubnetworks)')" == "False" ]] || fail_drift "Network"
  printf 'Validated custom VPC %s.\n' "$M3_13_NETWORK"
else
  gcloud compute networks create "$M3_13_NETWORK" "${PROJECT_ARGS[@]}" --subnet-mode custom
fi

if gcloud compute networks subnets describe "$M3_13_SUBNETWORK" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" >/dev/null 2>&1; then
  subnet_values="$(gcloud compute networks subnets describe "$M3_13_SUBNETWORK" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" --format='value(network,ipCidrRange,privateIpGoogleAccess)')"
  [[ "$subnet_values" == *"/$M3_13_NETWORK"* && "$subnet_values" == *"$M3_13_SUBNET_RANGE"* && "$subnet_values" == *"True"* ]] || fail_drift "Subnetwork"
  printf 'Validated subnetwork %s.\n' "$M3_13_SUBNETWORK"
else
  gcloud compute networks subnets create "$M3_13_SUBNETWORK" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" \
    --network "$M3_13_NETWORK" --range "$M3_13_SUBNET_RANGE" --enable-private-ip-google-access
fi

if gcloud compute addresses describe "$M3_13_ADDRESS_NAME" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" >/dev/null 2>&1; then
  [[ "$(gcloud compute addresses describe "$M3_13_ADDRESS_NAME" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" --format='value(addressType)')" == "EXTERNAL" ]] || fail_drift "Address"
  printf 'Validated static address %s.\n' "$M3_13_ADDRESS_NAME"
else
  gcloud compute addresses create "$M3_13_ADDRESS_NAME" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" \
    --description "Mirror M3-13 Stage A public HTTPS address"
fi

ensure_firewall_rule "$M3_13_HTTP_FIREWALL_RULE" "$M3_13_PUBLIC_SOURCE_RANGES" "80" "mirror-public"
ensure_firewall_rule "$M3_13_HTTPS_FIREWALL_RULE" "$M3_13_PUBLIC_SOURCE_RANGES" "443" "mirror-public"
ensure_firewall_rule "$M3_13_IAP_SSH_FIREWALL_RULE" "35.235.240.0/20" "22" "mirror-iap-ssh"
validate_effective_ingress

address="$(gcloud compute addresses describe "$M3_13_ADDRESS_NAME" --region "$M3_13_REGION" "${PROJECT_ARGS[@]}" --format='value(address)')"
if gcloud compute instances describe "$M3_13_VM_NAME" --zone "$M3_13_ZONE" "${PROJECT_ARGS[@]}" >/dev/null 2>&1; then
  gcloud compute instances describe "$M3_13_VM_NAME" --zone "$M3_13_ZONE" "${PROJECT_ARGS[@]}" --format=json | \
    python3 -c '
import json, sys
name, network, subnet, address, service_account, machine_type = sys.argv[1:]
d = json.load(sys.stdin)
nics = d.get("networkInterfaces", [])
metadata = {item.get("key"): item.get("value") for item in d.get("metadata", {}).get("items", [])}
accelerators = d.get("guestAccelerators", [])
scopes = d.get("serviceAccounts", [{}])[0].get("scopes", [])
ok = (
    len(nics) == 1
    and nics[0].get("network", "").rsplit("/", 1)[-1] == network
    and nics[0].get("subnetwork", "").rsplit("/", 1)[-1] == subnet
    and nics[0].get("accessConfigs", [{}])[0].get("natIP") == address
    and d.get("machineType", "").rsplit("/", 1)[-1] == machine_type
    and len(accelerators) == 1 and accelerators[0].get("acceleratorType", "").endswith("nvidia-tesla-t4") and accelerators[0].get("acceleratorCount") == 1
    and d.get("scheduling", {}).get("onHostMaintenance") == "TERMINATE"
    and d.get("scheduling", {}).get("automaticRestart") is False
    and d.get("serviceAccounts", [{}])[0].get("email") == service_account
    and scopes == ["https://www.googleapis.com/auth/cloud-platform"]
    and set(d.get("tags", {}).get("items", [])) == {"mirror-public", "mirror-iap-ssh"}
    and metadata.get("enable-oslogin") == "TRUE"
)
if not ok:
    raise SystemExit(f"VM drift: {name} does not match the required hardened Stage A configuration")
' "$M3_13_VM_NAME" "$M3_13_NETWORK" "$M3_13_SUBNETWORK" "$address" "$M3_13_SERVICE_ACCOUNT_EMAIL" "$M3_13_MACHINE_TYPE"
  printf 'Validated VM %s.\n' "$M3_13_VM_NAME"
else
  gcloud compute instances create "$M3_13_VM_NAME" --zone "$M3_13_ZONE" "${PROJECT_ARGS[@]}" \
    --machine-type "$M3_13_MACHINE_TYPE" --accelerator type=nvidia-tesla-t4,count=1 \
    --maintenance-policy=TERMINATE --boot-disk-size "$M3_13_BOOT_DISK_SIZE" \
    --image-family "$M3_13_IMAGE_FAMILY" --image-project "$M3_13_IMAGE_PROJECT" \
    --service-account "$M3_13_SERVICE_ACCOUNT_EMAIL" --scopes cloud-platform \
    --subnet "$M3_13_SUBNETWORK" --address "$M3_13_ADDRESS_NAME" \
    --tags mirror-public,mirror-iap-ssh --labels project=mirror,task=m3-13,environment=prod \
    --metadata enable-oslogin=TRUE --no-restart-on-failure
fi

gcloud compute instances describe "$M3_13_VM_NAME" --zone "$M3_13_ZONE" "${PROJECT_ARGS[@]}" \
  --format='yaml(name,zone,status,networkInterfaces,guestAccelerators,serviceAccounts,tags.items,labels)'

printf '\nStage A next steps:\n'
printf '1. Point your approved DNS A record at %s before starting Caddy.\n' "$address"
printf '2. Bootstrap through IAP:\n'
printf '   gcloud compute ssh %q --zone %q --project %q --tunnel-through-iap --command "bash -s" < infra/gcp/bootstrap-vm.sh\n' \
  "$M3_13_VM_NAME" "$M3_13_ZONE" "$M3_13_PROJECT_ID"
printf '3. Do not place secrets, model adapters, or credential files in Git.\n'
