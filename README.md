# VoxCPM-ROCM

**Text-to-speech (TTS) VoxCPM2 di GPU AMD**, siap pakai dalam kontainer Podman,
lengkap dengan WebUI seperti [demo resmi di Hugging Face](https://huggingface.co/spaces/openbmb/VoxCPM-Demo):
ketik teks → jadi suara, desain suara dari deskripsi, kloning suara dari rekaman, dan training LoRA.

```bash
podman pull ghcr.io/varkir/voxcpm:rocm
```

- Model: [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2) (2B parameter, audio 48 kHz, 30 bahasa
  termasuk **Bahasa Indonesia**, Inggris, Melayu, Jepang, dan lainnya)
- Diuji di: **AMD Radeon RX 6700 XT (12 GB)**, Debian 13, Podman 5.4 rootless
- Kecepatan: ±1,6 detik kerja untuk 1 detik suara (setelah pemanasan), VRAM ±6 GB
- Sumber Containerfile: branch [`docker-rocm`](https://github.com/varkir/VoxCPM/tree/docker-rocm/docker/rocm)
  di fork `varkir/VoxCPM` (diajukan ke upstream lewat [OpenBMB/VoxCPM#444](https://github.com/OpenBMB/VoxCPM/pull/444))

---

## Daftar isi

1. [Yang dibutuhkan](#1-yang-dibutuhkan)
2. [Siapkan folder](#2-siapkan-folder)
3. [Ambil image](#3-ambil-image) — pull (cepat) atau build sendiri
4. [Unduh model (opsional)](#4-unduh-model-opsional)
5. [Jalankan](#5-jalankan) — cara mudah atau `podman run` manual
6. [Memakai WebUI](#6-memakai-webui)
7. [Menjalankan di background & otomatis saat boot](#7-menjalankan-di-background--otomatis-saat-boot)
8. [Training LoRA](#8-training-lora)
9. [Update, backup, dan pemulihan](#9-update-backup-dan-pemulihan)
10. [Pengaturan (environment variable)](#10-pengaturan-environment-variable)
11. [Masalah yang sering terjadi](#11-masalah-yang-sering-terjadi)

---

## 1. Yang dibutuhkan

| | |
|---|---|
| GPU | AMD Radeon RDNA2/RDNA3 dengan VRAM ≥ 8 GB (RX 6700 XT, 6800, 7800 XT, …) |
| OS | Linux dengan driver `amdgpu` (bawaan kernel). **ROCm tidak perlu dipasang di host** |
| Podman | versi 4 atau lebih baru (`podman --version`) |
| Disk | ±25 GB kosong: image 18 GB + model 5 GB |
| RAM | 16 GB |

**Cek GPU terbaca dan user-mu boleh memakainya:**

```bash
ls -l /dev/kfd /dev/dri/renderD128
```

```bash
id -nG
```

Output `id -nG` harus berisi `video` dan `render`. Kalau belum, tambahkan lalu **logout dan login lagi**:

```bash
sudo usermod -aG video,render $USER
```

---

## 2. Siapkan folder

Semua data (model, hasil suara, LoRA) disimpan di luar kontainer, jadi tidak hilang saat kontainer
atau image dihapus. Panduan ini memakai `/mnt/varkir/Podman/voxcpm`; ganti kalau mau di tempat lain.

```bash
sudo mkdir -p /mnt/varkir/Podman/voxcpm/{models,data,lora,output}
```

```bash
sudo chown -R $USER:$USER /mnt/varkir/Podman/voxcpm
```

Isi masing-masing folder:

```
/mnt/varkir/Podman/voxcpm/
├── voxcpm-rocm/   ← repo ini (README, run.sh, build.sh)
├── build/         ← kode VoxCPM + Containerfile (hanya kalau build sendiri)
├── models/        ← model yang diunduh (±5 GB) + cache
├── data/          ← audio referensi & data training
├── lora/          ← hasil training LoRA
└── output/        ← file suara hasil generate
```

Clone repo ini (berisi `run.sh` dan `build.sh`):

```bash
git clone https://github.com/varkir/voxcpm-rocm.git /mnt/varkir/Podman/voxcpm/voxcpm-rocm
```

---

## 3. Ambil image

Pilih **salah satu**.

### Cara A — pull dari GitHub (disarankan, ±7 GB download)

```bash
podman pull ghcr.io/varkir/voxcpm:rocm
```

Selesai, lanjut ke [langkah 4](#4-unduh-model-opsional).

### Cara B — build sendiri (±20–30 menit)

1. Clone kode VoxCPM dengan Containerfile ROCm ke folder `build`:

   ```bash
   git clone -b docker-rocm https://github.com/varkir/VoxCPM.git /mnt/varkir/Podman/voxcpm/build
   ```

2. Build image. Hasilnya bernama `ghcr.io/varkir/voxcpm:rocm` (sama seperti cara A).
   `PUSH=0` berarti tidak di-upload ke GitHub:

   ```bash
   PUSH=0 /mnt/varkir/Podman/voxcpm/voxcpm-rocm/build.sh
   ```

   Atau tanpa script, langsung dengan podman:

   ```bash
   cd /mnt/varkir/Podman/voxcpm/build && podman build -f docker/rocm/Containerfile -t ghcr.io/varkir/voxcpm:rocm .
   ```

3. Cek image sudah ada:

   ```bash
   podman images ghcr.io/varkir/voxcpm
   ```

> Pemilik repo: `./build.sh` tanpa `PUSH=0` sekaligus meng-upload ke `ghcr.io/varkir/voxcpm:rocm`.
> Login sekali dulu dengan `podman login ghcr.io` (token GitHub dengan izin `write:packages`).

---

## 4. Unduh model (opsional)

Model diunduh otomatis saat pertama kali generate. Tapi lebih nyaman diunduh dulu, supaya generate
pertama tidak menunggu lama. Cukup **sekali**; semuanya tersimpan di folder `models`.

```bash
podman run --rm -v /mnt/varkir/Podman/voxcpm/models:/app/models ghcr.io/varkir/voxcpm:rocm \
  sh -c 'hf download openbmb/VoxCPM2 && hf download openai/whisper-large-v3-turbo && modelscope download --model iic/speech_zipenhancer_ans_multiloss_16k_base'
```

| Model | Ukuran | Fungsi |
|---|---|---|
| `openbmb/VoxCPM2` | ±4,7 GB | model TTS utama |
| `openai/whisper-large-v3-turbo` | ±1,6 GB | mengubah audio referensi jadi teks (untuk kloning) |
| `iic/speech_zipenhancer_ans_multiloss_16k_base` | ±20 MB | membersihkan noise audio referensi |

---

## 5. Jalankan

### Cara mudah

```bash
/mnt/varkir/Podman/voxcpm/voxcpm-rocm/run.sh
```

Script ini mendeteksi GPU otomatis dan menjalankan perintah `podman run` di bawah.
Tekan `Ctrl+C` untuk berhenti.

### Cara manual (`podman run` lengkap)

```bash
podman run --rm -it \
  --name voxcpm \
  --network varkir \
  --ip 10.20.0.11 \
  -p 7770:7770 \
  --shm-size 4g \
  --device /dev/kfd \
  --device /dev/dri \
  --group-add keep-groups \
  --security-opt label=disable \
  --security-opt apparmor=unconfined \
  -e HSA_OVERRIDE_GFX_VERSION=10.3.0 \
  -e PORT=7770 \
  -e GRADIO_SERVER_PORT=7770 \
  -e TEXT_NUMBER_LANG=id \
  -e ASR_LANGUAGE=id \
  -v /mnt/varkir/Podman/voxcpm/models:/app/models \
  -v /mnt/varkir/Podman/voxcpm/data:/app/data \
  -v /mnt/varkir/Podman/voxcpm/lora:/app/lora \
  -v /mnt/varkir/Podman/voxcpm/output:/app/output \
  ghcr.io/varkir/voxcpm:rocm
```

Arti tiap baris:

| Baris | Artinya |
|---|---|
| `--rm -it` | hapus kontainer saat berhenti; tampilkan log di terminal, `Ctrl+C` untuk berhenti |
| `--name voxcpm` | nama kontainer, untuk `podman logs voxcpm` / `podman stop voxcpm` |
| `--network varkir --ip 10.20.0.11` | **opsional.** Network & IP tetap milik server ini. Hapus dua baris ini kalau tidak punya network `varkir` |
| `-p 7770:7770` | buka WebUI di port 7770 host |
| `--shm-size 4g` | memori bersama untuk PyTorch |
| `--device /dev/kfd --device /dev/dri` | **teruskan GPU AMD ke kontainer** |
| `--group-add keep-groups` | bawa grup `video`/`render` milikmu ke dalam kontainer, supaya GPU boleh dipakai |
| `--security-opt label=disable` | matikan label SELinux (aman diabaikan di Debian/Ubuntu) |
| `--security-opt apparmor=unconfined` | AppArmor (Debian/Ubuntu) bisa memblokir akses ke `/dev/kfd` |
| `-e HSA_OVERRIDE_GFX_VERSION=10.3.0` | **wajib untuk RX 6700/6750 XT (gfx1031)** dan RDNA2 lain selain RX 6800/6900. RX 7700/7800 XT: `11.0.0`. RX 6800/6900/7900: hapus baris ini |
| `-e PORT=7770 -e GRADIO_SERVER_PORT=7770` | WebUI mendengarkan di port 7770 (bawaan 8808) |
| `-e TEXT_NUMBER_LANG=id` | angka dibaca dalam Bahasa Indonesia: `2026` → "dua ribu dua puluh enam" |
| `-e ASR_LANGUAGE=id` | Whisper menganggap audio referensi berbahasa Indonesia |
| `-v …:/app/…` | sambungkan 4 folder dari langkah 2 ke dalam kontainer |
| `ghcr.io/varkir/voxcpm:rocm` | image yang dijalankan |

**Jangan** tambahkan `--userns=keep-id`. Di Podman rootless, root di dalam kontainer sudah sama dengan
user-mu di host (file hasil tetap milikmu), dan `keep-id` membuat Podman menyalin ulang image 18 GB.

Tanpa network khusus (paling sederhana), cukup hapus baris `--network` dan `--ip`.
Kalau ingin membuat network `varkir` seperti di server ini:

```bash
podman network create --subnet 10.20.0.0/24 varkir
```

Log yang menandakan sudah siap:

```
[INFO] GPU: AMD Radeon RX 6700 XT (gfx1030), 12.0 GB
* Running on local URL:  http://0.0.0.0:7770
```

---

## 6. Memakai WebUI

Buka di browser: **`http://<ip-server>:7770`** (dari server itu sendiri: `http://localhost:7770`).

> Generate **pertama** butuh 1–3 menit (memuat model + menyetel kernel GPU). Berikutnya hanya
> beberapa detik.

| Mode | Cara pakai |
|---|---|
| **TTS biasa** | isi *Target Text* saja → Generate |
| **Voice Design** | isi *Control Instruction* dengan deskripsi suara, mis. `Perempuan muda, suara lembut dan hangat, tempo santai` |
| **Controllable Cloning** | upload rekaman suara (5–15 detik) + boleh isi *Control Instruction* untuk mengatur emosi/tempo |
| **Ultimate Cloning** | upload rekaman + aktifkan *Ultimate Cloning Mode*. Transkrip diisi otomatis oleh Whisper; **periksa dan perbaiki** supaya persis sama dengan isi rekaman. Ini hasil paling natural |

**Tips supaya Bahasa Indonesia terdengar natural**

- Matikan **Text Normalization** di UI. Normalizer bawaan hanya untuk Mandarin/Inggris dan akan
  membaca angka dalam bahasa Inggris. Angka sudah diurus oleh `TEXT_NUMBER_LANG=id`:
  `Rp 25.000` → "dua puluh lima ribu rupiah", `09.30` → "sembilan tiga puluh", `75,5%` → "tujuh puluh lima koma lima persen".
- Rekaman referensi: jernih, satu pembicara, tanpa musik, 5–15 detik.
- Whisper menulis angka di transkrip sebagai digit (`2026`, `75,5%`). Untuk *Ultimate Cloning*, ubah
  menjadi kata seperti yang benar-benar diucapkan di rekaman ("dua ribu dua puluh enam").
- Tulis singkatan dalam bentuk ucapannya (`dll.` → "dan lain-lain").
- Untuk suara narator tetap, latih LoRA dengan 10–30 menit rekaman bersih ([langkah 8](#8-training-lora)).
- Bahasa lain (Inggris, Melayu, Jepang, …) tetap bisa dipakai. Untuk teks Inggris, kosongkan
  `TEXT_NUMBER_LANG` dan `ASR_LANGUAGE` supaya angka dan transkrip tidak dipaksa Bahasa Indonesia.

---

## 7. Menjalankan di background & otomatis saat boot

Ganti `--rm -it` di perintah manual dengan `-d --restart=always`, lalu:

```bash
podman logs -f voxcpm
```

```bash
podman stop voxcpm
```

```bash
podman start voxcpm
```

Supaya ikut menyala setelah server reboot (Podman rootless), aktifkan sekali:

```bash
loginctl enable-linger $USER
```

```bash
systemctl --user enable podman-restart.service
```

---

## 8. Training LoRA

Jalankan UI training (port sama, 7770) dengan menambahkan perintah setelah nama image:

```bash
/mnt/varkir/Podman/voxcpm/voxcpm-rocm/run.sh python lora_ft_webui.py
```

Atau di perintah manual: tambahkan `python lora_ft_webui.py` setelah `ghcr.io/varkir/voxcpm:rocm`.

Data training ditaruh di folder `data`, format JSONL per baris, path memakai lokasi di dalam kontainer:

```json
{"audio_path": "/app/data/audio/narator_001.wav", "text": "Selamat pagi, ini rekaman pertama.", "speaker": "narator"}
```

Hasil LoRA muncul di folder `lora/`. Training di ROCm belum diuji sepenuhnya.

---

## 9. Update, backup, dan pemulihan

**Update image** (data di folder host tidak tersentuh):

```bash
podman pull ghcr.io/varkir/voxcpm:rocm
```

**Image terhapus?** Cukup pull lagi (cara A) atau build lagi (cara B). Model tidak perlu diunduh
ulang karena ada di folder `models`.

**Backup image ke file** (pulih tanpa internet):

```bash
podman save ghcr.io/varkir/voxcpm:rocm | zstd -T0 -3 -o /mnt/varkir/BAK/voxcpm-rocm.tar.zst
```

```bash
zstd -dc /mnt/varkir/BAK/voxcpm-rocm.tar.zst | podman load
```

---

## 10. Pengaturan (environment variable)

Tambahkan dengan `-e NAMA=nilai` di `podman run`, atau di depan `run.sh` (`PORT=8808 ./run.sh`).

| Variabel | Bawaan image | Keterangan |
|---|---|---|
| `PORT` | `8808` | port WebUI (`run.sh` server ini: 7770) |
| `VOXCPM_MODEL` | `openbmb/VoxCPM2` | model, atau path lokal di `/app/models/...` |
| `VOXCPM_DTYPE` | `float16` | RDNA2 tidak punya jalur bf16 cepat; fp16 2,7× lebih cepat. Kosong = bf16 bawaan model |
| `VOXCPM_OPTIMIZE` | `0` | `torch.compile`; **biarkan 0**, di gfx1031 menyebabkan GPU crash |
| `ASR_BACKEND` | `whisper` | `sensevoice` = bawaan upstream (hanya zh/en/ja/ko/yue) |
| `ASR_MODEL` | `openai/whisper-large-v3-turbo` | model Whisper |
| `ASR_LANGUAGE` | kosong (deteksi otomatis) | `id` = paksa Bahasa Indonesia |
| `ASR_DEVICE` | GPU | `cpu` kalau VRAM sempit |
| `TEXT_NUMBER_LANG` | kosong (mati) | `id` = angka → kata Bahasa Indonesia |
| `HSA_OVERRIDE_GFX_VERSION` | — | lihat tabel di langkah 5; `run.sh` mengisinya otomatis |
| `HF_TOKEN` | — | token Hugging Face, hanya untuk model privat |

---

## 11. Masalah yang sering terjadi

| Gejala | Penyebab & solusi |
|---|---|
| `HIP error: invalid device function` / log `can't run the bundled ROCm kernels` | `HSA_OVERRIDE_GFX_VERSION` belum diisi. RX 6700 XT: `-e HSA_OVERRIDE_GFX_VERSION=10.3.0` |
| `HIP out of memory` padahal VRAM 12 GB | program lain memakai VRAM (mis. Ollama). Cek: `cat /sys/class/drm/card*/device/mem_info_vram_used`. Bebaskan: `podman exec ollama ollama stop <model>` |
| `No ROCm GPU visible … running on CPU` | `/dev/kfd` tidak diteruskan atau user tidak di grup `render`. Cek langkah 1 dan `--group-add keep-groups` |
| `Permission denied` di `/app/...` | jangan pakai `--userns=keep-id` atau `--user`; semua yang ditulis ada di folder volume |
| Generate pertama sangat lama | normal: memuat model + unduh denoiser + menyetel kernel. Unduh model dulu (langkah 4) |
| Angka dibaca dalam bahasa Inggris | matikan *Text Normalization* di UI, pastikan `TEXT_NUMBER_LANG=id` |
| Start kontainer pertama lama sekali | ada `--userns=keep-id`; hapus |
| Port sudah dipakai / nama `voxcpm` sudah ada | kontainer lama masih jalan: `podman stop voxcpm` |

---

## Lisensi

Apache-2.0, mengikuti [VoxCPM](https://github.com/OpenBMB/VoxCPM). Model VoxCPM2 memakai lisensinya sendiri,
lihat [halaman model](https://huggingface.co/openbmb/VoxCPM2).
