"""Transcribe with whisper.cpp and emit words.json (word-level timestamps, source time).

    python transcribe.py input.mp4 -o words.json [--lang es] [--model <path>]

Run setup.ps1 first to fetch the binary and model.
"""
import argparse
import json
import tempfile
from pathlib import Path

from common import VENDOR, audio_cut_graph, read_json, run, write_json


def find_binary():
    for name in ("whisper-cli.exe", "main.exe", "whisper-cli", "main"):
        hit = next(VENDOR.rglob(name), None)
        if hit:
            return hit
    raise SystemExit(f"whisper.cpp no encontrado en {VENDOR}. Ejecuta scripts/setup.ps1")


def find_model(explicit):
    if explicit:
        return Path(explicit)
    hit = next((VENDOR / "models").glob("ggml-*.bin"), None)
    if not hit:
        raise SystemExit(f"no hay modelo en {VENDOR / 'models'}. Ejecuta scripts/setup.ps1")
    return hit


def extract_audio(video, wav, cuts=None):
    """Mono 16k for whisper. With cuts, the silences are removed first so the
    timestamps land directly on the output timeline — no remapping, no drift."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video)]
    if cuts:
        cmd += ["-filter_complex", audio_cut_graph(read_json(cuts)["segments"]), "-map", "[ac]"]
    else:
        cmd += ["-vn"]
    run(cmd + ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])


def tokens_to_words(payload):
    """whisper.cpp emits sub-word tokens; a leading space starts a new word."""
    words = []
    for seg in payload.get("transcription", []):
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if text.startswith("[") or not text.strip():
                continue  # special tokens like [_BEG_]
            start = tok["offsets"]["from"] / 1000.0
            end = tok["offsets"]["to"] / 1000.0
            if text.startswith(" ") or not words:
                words.append({"start": start, "end": end, "text": text.strip()})
            else:
                words[-1]["text"] += text
                words[-1]["end"] = end
    return [w for w in words if w["text"]]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input")
    parser.add_argument("-o", "--output", default="words.json")
    parser.add_argument("--lang", default="es")
    parser.add_argument("--model", default=None, help="path to a ggml-*.bin (default: any in vendor)")
    parser.add_argument("--threads", type=int, default=0, help="0 = whisper.cpp default")
    parser.add_argument("--cuts", default=None,
                        help="cuts.json: transcribe the cut audio, so timestamps are already "
                             "on the output timeline (use this for the subtitle pass)")
    return parser.parse_args()


def main():
    args = parse_args()
    binary, model = find_binary(), find_model(args.model)

    with tempfile.TemporaryDirectory() as workdir:
        wav = Path(workdir) / "audio.wav"
        stem = Path(workdir) / "out"
        extract_audio(args.input, wav, args.cuts)

        command = [str(binary), "-m", str(model), "-f", str(wav), "-l", args.lang,
                   "--output-json", "--output-json-full", "-of", str(stem), "-np"]
        if args.threads:
            command += ["-t", str(args.threads)]
        run(command)

        payload = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))

    words = tokens_to_words(payload)
    if not words:
        raise SystemExit("la transcripción salió vacía — ¿tiene voz el audio?")

    write_json(args.output, {"source": str(args.input), "lang": args.lang,
                             "timeline": "output" if args.cuts else "source",
                             "words": words})
    print(f"{len(words)} palabras ({'ya cortado' if args.cuts else 'original'}) -> {args.output}")


if __name__ == "__main__":
    main()
