"""Abre un corto con su frase gancho: la lleva al segundo 0 en cuts.json.

    python hook.py cuts.json --from 14.2 --to 17.9 --keep    # duplica: al inicio y en su sitio
    python hook.py cuts.json --from 14.2 --to 17.9           # la mueve: sólo al inicio

Los tiempos son de la línea de SALIDA (la izquierda de digest.txt, o words.json
del paso 2). Cada borde se pega al borde de segmento más cercano si está a menos
de SNAP segundos: esos bordes son silencios medidos, así el gancho no empieza ni
acaba a media palabra.

`--keep` es para un gancho del que depende lo que viene después: si se quita de
su sitio, el resto pierde el hilo. Sin `--keep` se mueve, que es lo correcto
cuando la frase se entiende sola y repetirla sería relleno.

Después hay que repetir transcribe.py --cuts: la línea de tiempo ha cambiado.
"""
import argparse

from common import output_duration, read_json, write_json

SNAP = 0.5  # s; más lejos que esto el borde se respeta tal cual


def snap(t, edges):
    nearest = min(edges, key=lambda edge: abs(edge - t))
    return nearest if abs(nearest - t) <= SNAP else t


def slice_output(segments, start, end):
    """Split the cut into (inside, outside) the output window [start, end]."""
    inside, outside, elapsed = [], [], 0.0
    for segment in segments:
        speed = segment.get("speed", 1.0)
        span = (segment["end"] - segment["start"]) / speed
        lo, hi = max(start, elapsed), min(end, elapsed + span)

        def piece(a, b):  # output offsets within this segment -> source segment
            return {**segment, "start": segment["start"] + (a - elapsed) * speed,
                    "end": segment["start"] + (b - elapsed) * speed}

        if hi <= lo:
            outside.append(segment)
        else:
            if lo > elapsed:
                outside.append(piece(elapsed, lo))
            inside.append(piece(lo, hi))
            if hi < elapsed + span:
                outside.append(piece(hi, elapsed + span))
        elapsed += span
    return inside, outside


def lead_with_hook(segments, start, end, keep):
    """Segments with [start, end] (output time) first; also left in place if keep."""
    edges, elapsed = [0.0], 0.0
    for segment in segments:
        elapsed += (segment["end"] - segment["start"]) / segment.get("speed", 1.0)
        edges.append(elapsed)
    start, end = snap(start, edges), snap(end, edges)
    if not 0 <= start < end <= elapsed:
        raise SystemExit(f"gancho fuera del corte: {start:.2f}-{end:.2f}s de {elapsed:.2f}s")
    if start == 0:
        raise SystemExit("el corto ya abre con ese gancho")
    inside, outside = slice_output(segments, start, end)
    return inside + (segments if keep else outside), start, end


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cuts")
    parser.add_argument("--from", dest="start", type=float, required=True,
                        help="inicio del gancho, en tiempo de salida (s)")
    parser.add_argument("--to", dest="end", type=float, required=True,
                        help="fin del gancho, en tiempo de salida (s)")
    parser.add_argument("--keep", action="store_true",
                        help="duplicar: el resto depende de la frase, se queda también en su sitio")
    args = parser.parse_args()

    data = read_json(args.cuts)
    data["segments"], start, end = lead_with_hook(data["segments"], args.start,
                                                  args.end, args.keep)
    write_json(args.cuts, data)
    print(f"gancho {start:.2f}-{end:.2f}s ({end - start:.2f}s) al inicio, "
          f"{'duplicado' if args.keep else 'movido'} · corte ahora "
          f"{output_duration(data['segments']):.1f}s · costura en {end - start:.2f}s")


if __name__ == "__main__":
    main()
