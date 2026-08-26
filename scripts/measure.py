"""Todas las medidas de un vídeo en una sola llamada, en un bloque legible.

    python measure.py entrada.mp4                      # formato, color y sonoridad  
    python measure.py entrada.mp4 --card 14.6 17.7     # lámina para colocar una card
    python measure.py entrada.mp4 --match clip1.mp4    # color de un plano de recurso

Antes esto eran quince llamadas sueltas a ffprobe y a ffmpeg, cada una con su
salida entera de vuelta. Miden lo mismo; lo que cambia es que la lectura cabe en
unas pocas líneas en vez de en varias pantallas de log.
"""
import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import probe_duration, probe_stream  # noqa: E402

# Por debajo de este brillo medio el color por defecto de render.py hunde el
# material: la curva y la viñeta se suman y la cara se va a las sombras.
DARK_YAVG = 60

LOUDNESS_WINDOW = 240

STATS = ("YAVG", "YHIGH", "YLOW", "SATAVG")


def timecode(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def signalstats(video, when):
    """YAVG/YHIGH/YLOW/SATAVG de un fotograma."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-ss", f"{when:.2f}",
         "-i", str(video), "-frames:v", "1", "-vf", "signalstats,metadata=print",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    found = {}
    for key, value in re.findall(r"lavfi\.signalstats\.(\w+)=([\d.]+)", result.stderr):
        if key in STATS:
            found[key] = float(value)
    return found


def loudness(video, duration):
    """(I, LRA, TP) de una ventana central.

    Integrar media hora entera para tres números cuesta más de un minuto, y en
    una charla a cámara la ventana central dice lo mismo.
    """
    start = max(0.0, duration / 2 - LOUDNESS_WINDOW / 2)
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-nostdin",
         "-ss", f"{start:.2f}", "-t", str(LOUDNESS_WINDOW), "-i", str(video),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = result.stderr[-1500:]
    def grab(label):
        hit = re.search(label + r":\s*(-?[\d.]+)", tail)
        return float(hit.group(1)) if hit else None
    return grab("I"), grab("LRA"), grab("Peak")


# Colocar una card se decide mirando, no midiendo. La detección automática de
# piel se probó y falla de forma que no se ve venir: una mano que sube al borde
# inferior cuenta como cara, y la barba —que es lo que de verdad no hay que
# tapar— no es piel para ningún umbral de color. Lo que sí funciona es dibujar
# las guías sobre fotogramas reales y mirar cuál libra la barbilla.
CARD_GUIDES = (0.56, 0.62, 0.68, 0.74, 0.80)
CARD_FRAMES = 6               # una cara quieta engaña; al hablar se gesticula
CARD_WIDTH = 320              # por fotograma en la lámina


def card_sheet(video, start, end, output):
    """Lámina con varios fotogramas de la ventana y las guías de y_frac encima."""
    from PIL import Image, ImageDraw

    span = max(end - start, 0.1)
    frames = []
    for index in range(CARD_FRAMES):
        when = start + span * index / max(CARD_FRAMES - 1, 1)
        raw = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
             "-ss", f"{when:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", f"scale={CARD_WIDTH}:-2", "-f", "image2pipe",
             "-vcodec", "png", "-"],
            capture_output=True).stdout
        if raw:
            frames.append((when, Image.open(io.BytesIO(raw)).convert("RGB")))
    if not frames:
        sys.exit("no he podido sacar fotogramas de esa ventana")

    width, height = frames[0][1].size
    columns = 3 if len(frames) > 2 else len(frames)
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (width * columns, height * rows), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)

    for index, (when, frame) in enumerate(frames):
        x = (index % columns) * width
        y = (index // columns) * height
        sheet.paste(frame, (x, y))
        for guide in CARD_GUIDES:
            line = y + int(height * guide)
            draw.line([(x, line), (x + width, line)], fill=(255, 60, 60), width=1)
            draw.text((x + 4, line + 2), f"{guide:.2f}", fill=(255, 200, 60))
        draw.text((x + 4, y + 4), f"{when:.1f}s", fill=(120, 255, 255))

    sheet.save(output)
    print(f"{len(frames)} fotogramas de {start:.1f}s a {end:.1f}s -> {output}")
    print("guías: " + "  ".join(f"{g:.2f}" for g in CARD_GUIDES))
    print("elige la primera que quede POR DEBAJO de la barbilla en los seis; "
          "por abajo no pases de 0.85, que ahí va la interfaz de la app")


def report_colour(video, times, label=""):
    for when in times:
        stats = signalstats(video, when)
        if not stats:
            continue
        print(f"  {label}{timecode(when):>6}  YAVG {stats.get('YAVG', 0):5.1f}"
              f"  YHIGH {stats.get('YHIGH', 0):5.1f}"
              f"  SATAVG {stats.get('SATAVG', 0):5.1f}")
    return stats


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input")
    parser.add_argument("--at", type=float, nargs="*", default=None,
                        help="momentos a medir (por defecto, tres repartidos)")
    parser.add_argument("--card", type=float, nargs=2, metavar=("INICIO", "FIN"),
                        help="ventana de una card: lámina con las guías de y_frac dibujadas")
    parser.add_argument("--sheet", default="card-check.png",
                        help="fichero de la lámina de --card")
    parser.add_argument("--match", nargs="*", default=(),
                        help="planos de recurso: mide su color junto al del vídeo")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.card:
        card_sheet(args.input, args.card[0], args.card[1], args.sheet)
        return

    duration = probe_duration(args.input)
    width, height, fps = probe_stream(args.input)

    print(f"{width}x{height}  {fps:g} fps  {duration:.1f}s ({timecode(duration)})")

    times = args.at if args.at else [duration * f for f in (0.25, 0.5, 0.75)]
    print("color")
    stats = report_colour(args.input, times)

    integrated, lra, peak = loudness(args.input, duration)
    if integrated is not None:
        print(f"sonoridad  I {integrated} LUFS   LRA {lra}   pico {peak} dBTP")

    if stats and stats.get("YAVG", 99) < DARK_YAVG:
        print(f"aviso: YAVG {stats['YAVG']:.0f} < {DARK_YAVG} — el color por defecto"
              " hundirá el material, levanta medios con curves en 'grade'")

    for clip in args.match:
        print(f"{Path(clip).name}")
        report_colour(clip, [min(2.0, probe_duration(clip) / 2)], label="")


if __name__ == "__main__":
    main()
