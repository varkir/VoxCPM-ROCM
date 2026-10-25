#!/usr/bin/env bash
# Build image VoxCPM ROCm lalu upload ke GitHub Packages.
#
#   ./build.sh             -> build + push ghcr.io/varkir/voxcpm:rocm
#   PUSH=0 ./build.sh      -> build saja, tanpa upload
#   ./build.sh --no-cache  -> argumen tambahan diteruskan ke "podman build"
#
# Upload butuh login sekali: podman login ghcr.io  (token dengan izin write:packages)
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BASE="${BASE:-$(dirname "$HERE")}"          # folder induk: berisi build/ (repo VoxCPM)

export REGISTRY="${REGISTRY:-ghcr.io/varkir}"
export IMAGE_NAME="${IMAGE_NAME:-voxcpm}" TAG="${TAG:-rocm}"
export SOURCE_URL="${SOURCE_URL:-https://github.com/varkir/VoxCPM-ROCM}"
export PUSH="${PUSH:-1}" SHA_TAG="${SHA_TAG:-0}" LOCAL_TAG="${LOCAL_TAG:-0}"

exec "$BASE/build/docker/rocm/build.sh" "$@"
