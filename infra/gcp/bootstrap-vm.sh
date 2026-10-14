#!/usr/bin/env bash
# Run on an Ubuntu 22.04 GPU VM as a sudo-capable deploy operator.
# Installs only host runtime prerequisites; it never writes application secrets.
set -euo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

$SUDO apt-get update
$SUDO apt-get install -y ca-certificates curl gnupg lsb-release ubuntu-drivers-common

# A fresh Ubuntu 22.04 GPU image does not have a usable NVIDIA kernel module.
# Install Ubuntu's supported 535 series and deliberately stop for its reboot.
REBOOT_REQUIRED=0
if ! nvidia-smi >/dev/null 2>&1; then
  $SUDO apt-get install -y nvidia-driver-535
  REBOOT_REQUIRED=1
fi

$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
$SUDO chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null

$SUDO apt-get update
$SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  $SUDO gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

$SUDO apt-get update
$SUDO apt-get install -y nvidia-container-toolkit
$SUDO nvidia-ctk runtime configure --runtime=docker
$SUDO systemctl enable --now docker
$SUDO systemctl restart docker

if [[ -n "${SUDO_USER:-}" ]]; then
  $SUDO usermod -aG docker "$SUDO_USER"
fi

if [[ "$REBOOT_REQUIRED" -eq 1 ]] || ! nvidia-smi >/dev/null 2>&1; then
  printf '\nNVIDIA driver installation needs a reboot before GPU validation. Reboot, reconnect through IAP, and rerun this script.\n' >&2
  exit 75
fi

nvidia-smi
docker version --format '{{.Server.Version}}'
docker compose version
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

printf '\nGPU host bootstrap passed. Log out and back in before using Docker without sudo.\n'
