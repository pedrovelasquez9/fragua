"""Capítulos de YouTube a partir de plan.json, con los tiempos ya cortados.

    python chapters.py plan.json --cuts cuts.json

Los tiempos de `plan.json` viven en la línea de tiempo de SALIDA, la del vídeo
ya montado, igual que los efectos y las cards. Ese es el punto: si los capítulos
se escriben mirando la grabación original, todos quedan corridos por lo que haya
quitado el detector de silencios, y en un vídeo de veinte minutos el desfase
puede ser de varios minutos.

YouTube además exige tres cosas o directamente no muestra los capítulos, sin
avisar de nada: el primero en 0:00, un mínimo de tres, y ninguno de menos de
diez segundos. Aquí se comprueban antes de que las pegues en la descripción.
"""
import argparse

from common import output_duration, read_json

# Requisitos de YouTube. Si no se cumplen, la lista se ignora en silencio.
MIN_CHAPTERS = 3
MIN_LENGTH = 10.0


def timestamp(seconds):
    """0:00, 4:07, 1:02:33 — el formato que YouTube reconoce en la descripción."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def check(chapters, duration):
    """Todo lo que hace que YouTube descarte la lista sin decir por qué."""
    if len(chapters) < MIN_CHAPTERS:
        raise SystemExit(f"YouTube pide al menos {MIN_CHAPTERS} capítulos y hay "
                         f"{len(chapters)}: no mostrará ninguno.")

    ordered = sorted(chapters, key=lambda c: float(c["t"]))
    if [c["t"] for c in chapters] != [c["t"] for c in ordered]:
        raise SystemExit("los capítulos no están en orden de tiempo.")

    if float(ordered[0]["t"]) != 0.0:
        raise SystemExit(f"el primer capítulo tiene que empezar en 0:00 y empieza "
                         f"en {timestamp(ordered[0]['t'])}.")

    for current, following in zip(ordered, ordered[1:]):
        gap = float(following["t"]) - float(current["t"])
        if gap < MIN_LENGTH:
            raise SystemExit(
                f"«{current['title']}» dura {gap:.1f}s y YouTube exige {MIN_LENGTH:.0f}s "
                f"como mínimo: junta ese capítulo con el siguiente.")

    last = float(ordered[-1]["t"])
    if duration and last >= duration:
        raise SystemExit(f"«{ordered[-1]['title']}» empieza en {timestamp(last)} y el "
                         f"vídeo dura {timestamp(duration)}: ¿tiempos de la grabación "
                         f"sin cortar en vez de los del montaje?")
    return ordered


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("--cuts", default=None,
                        help="cuts.json, para comprobar que ninguno se sale del vídeo")
    return parser.parse_args()


def main():
    args = parse_args()
    chapters = read_json(args.plan).get("chapters", [])
    if not chapters:
        raise SystemExit(
            'plan.json no tiene "chapters". En vídeo largo son obligatorios:\n'
            '  "chapters": [{"t": 0.0, "title": "..."}, {"t": 80.9, "title": "..."}]\n'
            "Los tiempos van en la línea de salida, la del vídeo ya cortado.")

    duration = output_duration(read_json(args.cuts)["segments"]) if args.cuts else None
    for chapter in check(chapters, duration):
        print(f"{timestamp(chapter['t'])}  {chapter['title']}")


if __name__ == "__main__":
    main()
