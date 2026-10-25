#!/usr/bin/env bash
# Jalankan VoxCPM WebUI dengan pengaturan server ini (RX 6700 XT, network varkir).
#
#   ./run.sh                          -> WebUI di http://10.20.0.11:7770 / http://<ip-server>:7770
#   ./run.sh python lora_ft_webui.py  -> UI training LoRA
#
# Semua nilai di bawah bisa ditimpa dari luar, misalnya:
#   NETWORK= IP= PORT=8808 ./run.sh   (tanpa network khusus, port 8808)
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BASE="${BASE:-$(dirname "$HERE")}"          # folder induk: berisi build/ models/ data/ ...

export DATA_ROOT="${DATA_ROOT:-$BASE}"
export IMAGE="${IMAGE:-ghcr.io/varkir/voxcpm:rocm}"
export NETWORK="${NETWORK-varkir}" IP="${IP-10.20.0.11}" PORT="${PORT:-7770}"
export TEXT_NUMBER_LANG="${TEXT_NUMBER_LANG-id}"
export ASR_LANGUAGE="${ASR_LANGUAGE-id}"

exec "$BASE/build/docker/rocm/run.sh" "$@"
