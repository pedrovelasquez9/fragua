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

# Sitio que se le deja al fundido de salida de render.py (TAIL_FADE, 0.35 s)
# para que caiga sobre silencio y no sobre la última palabra.
TAIL_ROOM = 0.45

# El corte se decide a --threshold, pero la cola de una consonante sigue sonando
# por debajo de ese nivel. Si el segmento acaba ahí, se oye «có—» en vez de
# «código». Se busca el silencio real a este otro umbral y se alarga hasta él.
TAIL_FLOOR_DB = -42
TAIL_REACH = 0.6


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
        # Casi toda grabación empieza en silencio: se le da a grabar y luego se
        # habla. Ahí silence_start es 0 y sin este guardia el pad_out fabrica un
        # segmento de silencio puro al principio del vídeo.
        if silence_start > cursor and end - cursor >= min_keep:
            keep.append({"start": round(cursor, 3), "end": round(end, 3), "speed": 1.0})
        cursor = max(cursor, silence_end - pad_in)
    if duration - cursor >= min_keep:
        keep.append({"start": round(cursor, 3), "end": round(duration, 3), "speed": 1.0})

    # El render cierra con un fundido de audio de 0.35 s. Si el último segmento
    # acaba justo donde acaba la voz, ese fundido se come la última palabra: se
    # oye «que tengas buen có—». Aquí se le deja silencio del original para que
    # el fundido tenga dónde caer, sin alargar nada que se oiga.
    if keep and keep[-1]["end"] < duration:
        keep[-1]["end"] = round(min(duration, keep[-1]["end"] + TAIL_ROOM), 3)
    return keep


def snap_ends(keep, quiet, duration):
    """Alarga el final de cada segmento hasta que el sonido ha parado de verdad.

    `quiet` son los silencios detectados a un umbral más bajo que el del corte.
    Si el final de un segmento cae antes de que empiece uno de esos silencios,
    es que la palabra todavía está sonando y se está cortando por la mitad.
    """
    for index, segment in enumerate(keep):
        ceiling = keep[index + 1]["start"] if index + 1 < len(keep) else duration
        for quiet_start, _ in quiet:
            if segment["end"] < quiet_start <= segment["end"] + TAIL_REACH:
                segment["end"] = round(min(quiet_start, ceiling), 3)
                break
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

    # Segunda pasada, más sensible: dice dónde para el sonido de verdad, no dónde
    # el detector de corte deja de considerarlo voz.
    quiet = detect_silences(args.input, TAIL_FLOOR_DB, 0.08)
    before = [s["end"] for s in segments]
    segments = snap_ends(segments, quiet, duration)
    rescued = sum(1 for old, s in zip(before, segments) if s["end"] > old + 0.005)
    if rescued:
        print(f"  {rescued} finales alargados hasta el silencio real "
              f"(la palabra seguía sonando)")

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
