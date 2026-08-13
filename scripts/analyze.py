"""Detect silences and emit cuts.json — the segments of the source to keep.

    python analyze.py input.mp4 -o cuts.json [--threshold -30] [--min-silence 0.28]

This is the first stage of the pipeline. Everything downstream works from the
cut it produces, so it is also the file you hand-edit to drop bad takes.
"""
import argparse
import re
import subprocess

from common import probe_duration, write_json

SILENCE_PATTERN = re.compile(r"silence_(start|end): (-?[\d.]+)")


def detect_silences(video, threshold_db, min_silence):
    """Silent stretches as [(start, end), ...] in source time."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    silences, start = [], None
    for kind, value in SILENCE_PATTERN.findall(result.stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            silences.append((start, float(value)))
            start = None
    return silences


def invert(silences, duration, pad_in, pad_out, min_keep):
    """Turn silent stretches into the segments to keep, padded back out.

    The padding is asymmetric on purpose: consonant tails and word decay run past
    where the detector calls silence, so clipping the END of a segment is far more
    audible than clipping its start.
    """
    keep, cursor = [], 0.0
    for silence_start, silence_end in silences:
        end = min(duration, silence_start + pad_out)
        if end - cursor >= min_keep:
            keep.append({"start": round(cursor, 3), "end": round(end, 3), "speed": 1.0})
        cursor = max(cursor, silence_end - pad_in)
    if duration - cursor >= min_keep:
        keep.append({"start": round(cursor, 3), "end": round(duration, 3), "speed": 1.0})
    return keep


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input")
    parser.add_argument("-o", "--output", default="cuts.json")
    parser.add_argument("--threshold", type=float, default=-30,
                        help="dB below which audio counts as silent")
    parser.add_argument("--min-silence", type=float, default=0.35,
                        help="shortest silence worth cutting (s)")
    parser.add_argument("--pad-in", type=float, default=0.06,
                        help="air kept before speech starts (s)")
    parser.add_argument("--pad-out", type=float, default=0.22,
                        help="air kept after speech ends (s)")
    parser.add_argument("--min-keep", type=float, default=0.12,
                        help="drop kept segments shorter than this (s)")
    return parser.parse_args()


def main():
    args = parse_args()

    duration = probe_duration(args.input)
    silences = detect_silences(args.input, args.threshold, args.min_silence)
    segments = invert(silences, duration, args.pad_in, args.pad_out, args.min_keep)

    if not segments:
        raise SystemExit("todo el vídeo se detectó como silencio — baja --threshold (p.ej. -40)")

    kept = sum(segment["end"] - segment["start"] for segment in segments)
    write_json(args.output, {
        "source": str(args.input),
        "duration": round(duration, 3),
        "segments": segments,
    })
    print(f"{len(segments)} segmentos · {kept:.1f}s de {duration:.1f}s "
          f"({100 * kept / duration:.0f}% conservado) -> {args.output}")


if __name__ == "__main__":
    main()
