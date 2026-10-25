"""
Long-form TTS: turn a long text file into one audio file with VoxCPM2.

Runs INSIDE the running WebUI container and talks to its API, so the model is
loaded only once (a second copy would not fit next to it in 12 GB VRAM).
Use it through longform.sh on the host; see README.md section "Teks panjang".

Steps:
  1. Split the text into chunks: paragraphs (blank-line separated), short ones
     merged up to --max-words, long ones split at sentence ends.
  2. Generate each chunk with the same seed and the same voice:
       --ref given  -> every chunk is cloned from that reference recording
       no --ref     -> chunk 1 is made from --voice (voice design), then
                       chunk 1's audio becomes the reference for the rest
  3. Save every chunk as it finishes (re-running resumes where it stopped).
  4. Join the chunks with a pause between paragraphs -> WAV and/or MP3.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

SENT_END = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")


def split_long(text: str, max_words: int) -> list[str]:
    """Split one paragraph at sentence ends (then commas, then words) to <= max_words."""
    if len(text.split()) <= max_words:
        return [text]
    pieces = [s for s in SENT_END.split(text) if s.strip()]
    out, cur = [], []
    for s in pieces:
        words = s.split()
        if len(words) > max_words:
            # one giant sentence: fall back to commas, then hard word cuts
            sub = re.split(r"(?<=[,;:])\s+", s)
            if any(len(x.split()) > max_words for x in sub):
                sub = [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]
        else:
            sub = [s]
        for x in sub:
            if cur and len(" ".join(cur + [x]).split()) > max_words:
                out.append(" ".join(cur))
                cur = []
            cur.append(x)
    if cur:
        out.append(" ".join(cur))
    return out


def make_chunks(raw: str, max_words: int) -> list[dict]:
    """Return [{'text': ..., 'para_end': bool}] — para_end marks a paragraph boundary."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw)]
    paras = [p for p in paras if p]
    chunks: list[dict] = []
    buf = ""
    for p in paras:
        if len(p.split()) > max_words:
            if buf:
                chunks.append({"text": buf, "para_end": True})
                buf = ""
            parts = split_long(p, max_words)
            for i, part in enumerate(parts):
                chunks.append({"text": part, "para_end": i == len(parts) - 1})
        elif buf and len((buf + " " + p).split()) > max_words:
            chunks.append({"text": buf, "para_end": True})
            buf = p
        else:
            # merging short paragraphs: keep them as separate sentences
            buf = f"{buf} {p}".strip() if buf else p
    if buf:
        chunks.append({"text": buf, "para_end": True})
    return chunks


def fmt_time(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser(description="Long text -> one audio file (VoxCPM2 WebUI API)")
    ap.add_argument("input", help="text file (UTF-8), path inside the container, e.g. /app/data/buku.txt")
    ap.add_argument("--out", help="output name without extension (default: input file name)")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--ref", help="reference recording for the voice (5-15 s, clean)")
    ap.add_argument("--prompt-text", help="exact transcript of --ref (Ultimate Cloning, most natural)")
    ap.add_argument("--voice", default="", help="voice description / style instruction")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cfg", type=float, default=2.0)
    ap.add_argument("--steps", type=int, default=10, help="diffusion steps (more = slower, slightly better)")
    ap.add_argument("--denoise", action="store_true", help="denoise the reference recording first")
    ap.add_argument("--max-words", type=int, default=150, help="max words per chunk")
    ap.add_argument("--pause", type=float, default=0.7, help="seconds of silence between paragraphs")
    ap.add_argument("--gap", type=float, default=0.25, help="seconds between chunks of one paragraph")
    ap.add_argument("--format", choices=["wav", "mp3", "both"], default="both")
    ap.add_argument("--url", default=f"http://localhost:{os.environ.get('PORT', '7770')}/")
    ap.add_argument("--dry-run", action="store_true", help="only show how the text is split")
    args = ap.parse_args()

    raw = open(args.input, encoding="utf-8").read()
    chunks = make_chunks(raw, args.max_words)
    words = sum(len(c["text"].split()) for c in chunks)
    name = args.out or os.path.splitext(os.path.basename(args.input))[0]
    parts_dir = os.path.join(args.outdir, f"{name}_parts")
    print(f"{len(chunks)} potongan, {words} kata (perkiraan audio ±{fmt_time(words / 2.3)})", flush=True)

    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print(f"\n[{i}] {len(c['text'].split())} kata{' ¶' if c['para_end'] else ''}\n{c['text']}")
        return

    from gradio_client import Client, handle_file

    os.makedirs(parts_dir, exist_ok=True)
    # Settings that change the voice: if they differ from a previous run,
    # don't mix old and new chunks.
    settings = {k: getattr(args, k) for k in ("ref", "prompt_text", "voice", "seed", "cfg", "steps", "denoise")}
    sfile = os.path.join(parts_dir, "settings.json")
    if os.path.exists(sfile) and json.load(open(sfile)) != settings:
        sys.exit(f"{parts_dir} was made with other settings. Delete that folder or use another --out.")
    json.dump(settings, open(sfile, "w"), indent=1)

    client = Client(args.url, verbose=False)
    ref = args.ref
    use_prompt = bool(args.ref and args.prompt_text)
    done_audio = 0.0
    t_start = time.time()
    t_work = 0.0
    n_new = 0

    for i, c in enumerate(chunks, 1):
        key = hashlib.sha1(c["text"].encode()).hexdigest()[:8]
        path = os.path.join(parts_dir, f"{i:04d}_{key}.wav")
        if os.path.exists(path):
            done_audio += sf.info(path).duration
            print(f"[{i}/{len(chunks)}] sudah ada, dilewati", flush=True)
        else:
            t = time.time()
            for attempt in range(3):
                try:
                    wav_path, _seed = client.predict(
                        c["text"],
                        args.voice,
                        handle_file(ref) if ref else None,
                        use_prompt,
                        args.prompt_text or "",
                        args.cfg,
                        False,  # do_normalize: off for Indonesian, numbers come from TEXT_NUMBER_LANG
                        args.denoise,
                        args.steps,
                        args.seed,
                        api_name="/generate",
                    )
                    break
                except Exception as e:  # WebUI busy/restarted: wait and retry
                    if attempt == 2:
                        raise
                    print(f"  gagal ({e}), coba lagi dalam 30 detik…", flush=True)
                    time.sleep(30)
            shutil.copy(wav_path, path)
            dt = time.time() - t
            dur = sf.info(path).duration
            done_audio += dur
            t_work += dt
            n_new += 1
            left = len(chunks) - i
            eta = t_work / n_new * left
            print(f"[{i}/{len(chunks)}] {dur:.1f} s audio dalam {dt:.0f} s"
                  f" | total {fmt_time(done_audio)} | sisa ±{fmt_time(eta)}", flush=True)
        if ref is None:
            # lock the voice: the first 12 s of chunk 1 become the reference for
            # all later chunks (references work best at 5-15 s)
            w, r = sf.read(path, dtype="float32")
            ref = os.path.join(parts_dir, "voice_ref.wav")
            sf.write(ref, w[: int(r * 12)], r)
            print(f"  suara dikunci dari potongan 1 -> {ref}", flush=True)

    # join
    pieces, sr = [], None
    for i, c in enumerate(chunks, 1):
        key = hashlib.sha1(c["text"].encode()).hexdigest()[:8]
        w, r = sf.read(os.path.join(parts_dir, f"{i:04d}_{key}.wav"), dtype="float32")
        sr = sr or r
        pieces.append(w)
        if i < len(chunks):
            pieces.append(np.zeros(int(sr * (args.pause if c["para_end"] else args.gap)), dtype="float32"))
    audio = np.concatenate(pieces)
    peak = float(np.abs(audio).max())
    if peak > 0.99:  # avoid clipping after concatenation
        audio = audio * (0.99 / peak)

    wav_out = os.path.join(args.outdir, f"{name}.wav")
    sf.write(wav_out, audio, sr)
    outs = [wav_out]
    if args.format in ("mp3", "both"):
        mp3_out = os.path.join(args.outdir, f"{name}.mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_out,
                        "-codec:a", "libmp3lame", "-q:a", "2", mp3_out], check=True)
        outs.append(mp3_out)
        if args.format == "mp3":
            os.remove(wav_out)
            outs.remove(wav_out)
    print(f"\nSelesai: {fmt_time(len(audio) / sr)} audio, {fmt_time(time.time() - t_start)} kerja")
    for o in outs:
        print(f"  {o}")
    print(f"Potongan disimpan di {parts_dir} (hapus kalau sudah tidak perlu)")


if __name__ == "__main__":
    main()
