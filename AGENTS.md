# AGENTS.md

Guidance for AI coding agents working on **voxcpm-rocm**: the VoxCPM2 TTS WebUI in a Podman
container on AMD GPUs (ROCm). The user-facing guide is `README.md` (Indonesian, written for
beginners). Keep it in sync with any change you make here, in the same plain style.

## What lives where

| Path | What |
|---|---|
| `voxcpm-rocm/` (this repo) | `README.md`, `AGENTS.md`, `run.sh`, `build.sh` (machine-specific wrappers), `longform.sh` + `longform.py` (long text → one audio file) |
| `../build/` | clone of `github.com/varkir/VoxCPM`, branch **`docker-rocm`**: upstream VoxCPM + `docker/rocm/` |
| `../build/docker/rocm/Containerfile` | the image recipe |
| `../build/docker/rocm/launch.py` | entrypoint; runs upstream `app.py` **unchanged** and monkeypatches it |
| `../build/docker/rocm/run.sh`, `build.sh` | generic scripts (upstream PR OpenBMB/VoxCPM#444); the wrappers here only set env vars and `exec` them |
| `../models`, `../data`, `../lora`, `../output` | host volumes → `/app/models`, `/app/data`, `/app/lora`, `/app/output` |

The wrappers find everything relative to their own location (`BASE` = parent of this repo),
so this repo must sit next to `build/`. Default base on the owner's server: `/mnt/varkir/Podman/voxcpm`.

Image: **`ghcr.io/varkir/voxcpm:rocm`** (public; the only tag and version). The image's OCI source
points to this repo, but on GitHub the package stays linked to `varkir/VoxCPM` (GHCR keeps the first
repository a package was linked to; changing it means deleting and re-creating the package).
Pushing a new `:rocm` leaves the previous version untagged. Delete it to keep a single version:
`gh api /user/packages/container/voxcpm/versions` → `gh api -X DELETE .../versions/<id>` (needs `delete:packages`).

## Hard-won facts (do not "fix" these back)

- **GPU:** RX 6700 XT = gfx1031, not in the ROCm wheel arch list. Needs
  `HSA_OVERRIDE_GFX_VERSION=10.3.0`. Without it: `hipErrorInvalidDeviceFunction` mid-request.
  `run.sh` auto-detects it from `/sys/class/kfd/kfd/topology/nodes/*/properties`, where
  `gfx_target_version` is **6 digits** (`100301` = gfx1031). Do not bake the override into the
  image: it breaks other GPUs.
- **dtype:** fp16, not the checkpoint's bf16 (`VOXCPM_DTYPE=float16`). RDNA2 has no fast bf16 path:
  RTF 1.60 in fp16 vs 4.28 in bf16, same audio quality.
- **torch.compile:** keep `VOXCPM_OPTIMIZE=0`. `reduce-overhead` (HIP graphs) causes a GPU memory
  access fault during warm-up on gfx1031, and the default mode gives no speedup.
- **Rootless Podman:** never add `--userns=keep-id`. Container root already maps to the host user,
  and keep-id forces an ID-mapped copy of the 18 GB image on first run (minutes; it looks like a hang).
  `--group-add keep-groups` is required for `/dev/kfd`. `apparmor=unconfined` is needed on Debian.
- **HOME** is set to `/app/models/.home` in the image. modelscope fails if HOME is unwritable.
- **Packaging trap:** setuptools builds in-tree. The Containerfile deletes `/app/build` between the
  deps layer and the source layer; otherwise a stub `voxcpm/__init__.py` gets installed.
  The build asserts `import voxcpm; voxcpm.VoxCPM`.
- **GHCR linking:** podman inherits the base image's `org.opencontainers.image.source` *manifest
  annotation* (docker-library/python). `build.sh` sets the source as both `--label` and
  `--annotation`; without that the package doesn't link to the repo.
- **Torch pin:** `PIP_CONSTRAINT=/opt/torch-constraints.txt` keeps the ROCm torch. Any new pip
  dependency must install under that constraint, never replace torch.
- **ASR:** Whisper (`openai/whisper-large-v3-turbo`) replaces SenseVoice, which can't do Indonesian.
- **Indonesian numbers:** upstream normalizer is zh/en only. `TEXT_NUMBER_LANG=id` expands digits
  with `num2words` in `launch.py:expand_numbers` (handles `Rp`, `%`, `HH.MM`, `1.000.000`, `3,5`).
- **MIOpen find mode:** `MIOPEN_FIND_MODE=FAST` is baked into the image (Containerfile ENV). In the default mode MIOpen benchmarks
  convolution kernels for every new input shape, i.e. every new text/audio length, which made
  long-form chunks run at RTF 4–11 instead of about 2.3. The find-db lives in `models/.cache/miopen`.
- **Generation limits:** each step = 4 latent frames at 25 Hz = 0.16 s, and `max_len=4096` gives about 655 s
  (≈1,400–1,500 Indonesian words, about 2.3 words/s). The KV cache is 8192 tokens for text (≈2.5
  tokens/word) plus audio steps. Keep chunks around 50–200 words for stability.
- **WebUI auto-split (`launch.py:_generate_tts_audio`):** text over `AUTO_SPLIT_WORDS` (150) is split with
  `split_text`, generated chunk by chunk with one seed, and the voice is locked from chunk 1's first 12 s.
  Each chunk is decoded separately; decoding one huge latent used to OOM ("Tried to allocate 5.96 GiB").
  Results are also written to `/app/output/webui_<time>.wav/.mp3`. Unlike longform.sh it can't resume.
- **Voice presets (`launch.py`, `VOICES_DIR=/app/data/voices`):** a Dropdown is injected right before the reference
  `gr.Audio` (the only one with `sources=["upload","microphone"]`) by swapping `gr.Audio` during UI build. The
  checkbox and transcript box are found as the next two blocks in `interface.blocks`. Choosing a preset outputs
  (audio, True, transcript). Toggling Ultimate Cloning re-runs ASR on Gradio's *copy* of the file, so
  `prompt_wav_recognition` matches presets by size + sha1 and returns `<name>.txt` (written by Whisper once if
  missing). `Blocks.launch` is wrapped to add `VOICES_DIR` to `allowed_paths`.
- **OOM handling (`launch.py:gen_piece`):** a chunk that hits `torch.OutOfMemoryError` (usually in AudioVAE decode) is
  retried in halves split at sentence ends, up to 4 levels. The retry must run *outside* the `except` block, or the
  live traceback keeps the failed attempt's tensors and memory grows on every retry. Whisper is released from the GPU
  after each transcription (~1.5 GB). Ultimate Cloning chunks also decode the reference (~15 s), so OOM is likelier
  there; `AUTO_SPLIT_WORDS=80` keeps the decode around 1 GB.
- **Long-form (`longform.py`):** streamed into the running container with `podman exec -i voxcpm python -`
  and calls the WebUI `/generate` API, so the model isn't loaded twice. Its positional args are text,
  control_instruction, ref_wav, use_prompt_text, prompt_text_value, cfg_value, do_normalize, denoise,
  dit_steps and seed_value. Without `--ref`, chunk 1's first 12 s become the reference. Chunks are cached in
  `output/<name>_parts/` keyed by index and text hash; `settings.json` there blocks mixing voices.
- **VRAM:** VoxCPM2 peaks at about 5.8 GB, and Whisper adds about 1.5 GB once ASR has run. The owner also runs Ollama on the same 12 GB card;
  "HIP out of memory" usually means an Ollama model is loaded. Don't unload it without asking.

## Build, run, test

```bash
PUSH=0 ./build.sh                      # build ghcr.io/varkir/voxcpm:rocm locally
./build.sh                             # build + push (needs: podman login ghcr.io)
./run.sh                               # WebUI on :7770, network varkir, IP 10.20.0.11
NETWORK= IP= PORT=8808 ./run.sh        # without the custom network
ENGINE=echo ./run.sh                   # print the docker-style command without running (podman adds keep-groups)
./longform.sh buku.txt --dry-run        # long text: show the chunking
./longform.sh buku.txt --voice "..."   # long text -> output/buku.{wav,mp3} (WebUI must be running)
```

Smoke tests, in order of cost:

1. GPU visible in the container:
   `podman run --rm --device /dev/kfd --device /dev/dri --group-add keep-groups --security-opt label=disable --security-opt apparmor=unconfined -e HSA_OVERRIDE_GFX_VERSION=10.3.0 ghcr.io/varkir/voxcpm:rocm python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`
2. Startup check: the log shows `GPU: AMD Radeon RX 6700 XT (gfx1030)` and then `Running on local URL`.
3. End-to-end through the WebUI API, from inside the running container:
   `podman exec voxcpm python -c "from gradio_client import Client; print(Client('http://localhost:7770/').predict('Halo, ini tes.', '', None, api_name='/generate'))"`
   The `/generate` arguments are text, control_instruction and ref_wav. The first call takes 1–3 min; later calls a few seconds.

A first-run log line `/opt/amdgpu/share/libdrm/amdgpu.ids: No such file` would be a regression
(the image symlinks libdrm there).

## Conventions

- Shell: `set -euo pipefail`, env-var configuration with defaults, no hard-coded user paths in
  `build/docker/rocm/*`. Machine-specific values belong only in this repo's wrappers.
- Changes to `build/docker/rocm/` go on branch `docker-rocm` of `varkir/VoxCPM`; that branch backs
  the open upstream PR OpenBMB/VoxCPM#444, so keep it generic and English.
- `README.md` here is Indonesian and for non-technical users: one command per code block, explain
  every flag, no assumed knowledge.
- Git identity: `Varkir <44952586+varkir@users.noreply.github.com>`. Don't publish the owner's personal email.
- Ask before: pushing, publishing or deleting GHCR packages, stopping other containers (Ollama,
  ComfyUI), or deleting anything in `models/` (re-downloading costs about 6 GB).
