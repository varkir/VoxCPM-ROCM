#!/usr/bin/env bash
# Ubah file teks panjang jadi satu file audio, memakai WebUI VoxCPM yang sedang jalan.
#
#   ./longform.sh /mnt/varkir/Podman/voxcpm/data/buku.txt
#   ./longform.sh buku.txt --voice "Laki-laki dewasa, suara hangat, seperti pendongeng"
#   ./longform.sh buku.txt --ref data/narator.wav --prompt-text "Isi persis rekaman narator."
#   ./longform.sh buku.txt --dry-run        # lihat cara teks dipotong, tanpa generate
#
# Path file (teks dan --ref) boleh path host di dalam folder data/ atau output/,
# atau nama file saja (dicari di data/). Hasil: output/<nama>.wav dan .mp3.
# Semua opsi: ./longform.sh --help
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BASE="${BASE:-$(dirname "$HERE")}"
CONTAINER="${CONTAINER:-voxcpm}"

# host path -> path inside the container
to_container() {
  local p="$1" abs
  [ -e "$p" ] || [ -e "$BASE/data/$p" ] || [ -e "$BASE/$p" ] || { echo "$p"; return; }
  if [ -e "$p" ]; then abs="$(readlink -f "$p")"
  elif [ -e "$BASE/$p" ]; then abs="$(readlink -f "$BASE/$p")"
  else abs="$(readlink -f "$BASE/data/$p")"; fi
  case "$abs" in
    "$(readlink -f "$BASE")"/data/*)   echo "/app/data/${abs#"$(readlink -f "$BASE")"/data/}" ;;
    "$(readlink -f "$BASE")"/output/*) echo "/app/output/${abs#"$(readlink -f "$BASE")"/output/}" ;;
    *) echo "File harus ada di $BASE/data atau $BASE/output: $p" >&2; exit 1 ;;
  esac
}

if ! podman container exists "$CONTAINER" || [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER")" != true ]; then
  echo "Kontainer '$CONTAINER' tidak berjalan. Jalankan dulu WebUI: $HERE/run.sh" >&2
  exit 1
fi

args=()
expect_path=1   # first positional argument is the text file
for a in "$@"; do
  if [ "$expect_path" = 1 ] && [[ "$a" != -* ]]; then
    args+=("$(to_container "$a")"); expect_path=0
  elif [ "$expect_path" = ref ]; then
    args+=("$(to_container "$a")"); expect_path=0
  else
    args+=("$a")
    [ "$a" = --ref ] && expect_path=ref
  fi
done

# -i streams this script into the container's python (no -t: stdin is the file)
exec podman exec -i -e PYTHONUNBUFFERED=1 "$CONTAINER" python - "${args[@]}" < "$HERE/longform.py"
