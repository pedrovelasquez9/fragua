"""Portada de un vídeo corto: un fotograma limpio, el gancho y una llamada a verlo.

    python cover.py entrada.mp4 --cuts cuts.json --at 3.2 \\
        --title "Deja de hacer ramas a lo loco" --emphasis ramas -o portada.jpg

El fotograma sale de la grabación ORIGINAL, no del vídeo montado: en el montado
casi siempre hay subtítulos o una card encima, y una portada con medio subtítulo
quemado se ve como un pantallazo. `--at` va en la línea de salida, como el plan;
con `--cuts` se lleva a la grabación.

Todo lo que se lee cae dentro del recorte 4:5 del centro, que es lo que enseña
la cuadrícula de Instagram, y por encima de la interfaz de TikTok.
"""
import argparse
import subprocess
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageStat

from common import FONTS, output_to_source, preset, read_json

ACCENT = (255, 138, 61)         # el naranja del barrido y los números de sección
INK = (8, 8, 12)
TARGET_LIGHT = 0.42             # brillo medio al que se sube un fotograma oscuro
MAX_LIFT = 1.8
CTA = "Mira el vídeo"


def grab(video, seconds, width, height):
    """El fotograma en `seconds`, encuadrado igual que render.py: llenar y centrar."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={width}:{height}",
         "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not raw:
        sys.exit(f"no pude sacar el fotograma {seconds:.2f}s de {video}")
    import io
    return Image.open(io.BytesIO(raw)).convert("RGB")


def lift(frame):
    """Este material se graba oscuro a propósito; en miniatura eso es una cara negra."""
    light = ImageStat.Stat(frame.convert("L")).mean[0] / 255
    if light >= TARGET_LIGHT:
        return frame
    return ImageEnhance.Brightness(frame).enhance(min(MAX_LIFT, TARGET_LIGHT / max(light, 0.05)))


def font(name, size):
    path = FONTS / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size)


def fit_lines(draw, words, max_width, max_lines=3, start=170, floor=80):
    """El tamaño más grande al que el título cabe en `max_lines` líneas llenas."""
    for size in range(start, floor - 1, -6):
        face = font("Anton-Regular.ttf", size)
        lines, current = [], []
        for word in words:
            trial = " ".join(current + [word])
            if current and draw.textlength(trial, font=face) > max_width:
                lines.append(current)
                current = [word]
            else:
                current.append(word)
        lines.append(current)
        if len(lines) <= max_lines and all(
                draw.textlength(" ".join(line), font=face) <= max_width for line in lines):
            return face, lines
    return face, lines


def cover(frame, title, emphasis=None, cta=CTA):
    width, height = frame.size
    image = lift(frame).convert("RGBA")

    # Degradado oscuro desde abajo: agarra el texto sin la caja que lo haría plantilla.
    shade = Image.new("L", (1, height))
    for y in range(height):
        shade.putpixel((0, y), int(235 * max(0.0, (y / height - 0.42) / 0.58) ** 1.3))
    dark = Image.new("RGBA", (width, height), INK + (255,))
    dark.putalpha(shade.resize((width, height)))
    image.alpha_composite(dark)

    draw = ImageDraw.Draw(image)
    words = title.upper().split()
    marked = {w.upper().strip(".,¿?¡!") for w in (emphasis or "").split()}
    face, lines = fit_lines(draw, words, width * 0.86)
    line_h = int(face.size * 1.08)
    stroke = max(4, int(face.size * 0.06))

    # El bloque acaba en el 78 % del alto: dentro del 4:5 de Instagram y por
    # encima de los botones y el pie de TikTok.
    cta_face = font("Poppins-ExtraBold.ttf", 54)
    cta_h = 100
    bottom = int(height * 0.78)
    y = bottom - cta_h - 36 - line_h * len(lines)
    for line in lines:
        x = (width - draw.textlength(" ".join(line), font=face)) / 2
        for word in line:
            colour = ACCENT if word.strip(".,¿?¡!") in marked else (255, 255, 255)
            draw.text((x, y), word, font=face, fill=colour,
                      stroke_width=stroke, stroke_fill=INK)
            x += draw.textlength(word + " ", font=face)
        y += line_h

    # La llamada: una pastilla con el triángulo de play, que es lo que se lee
    # como «esto se reproduce» antes de leer nada.
    label_w = draw.textlength(cta, font=cta_face)
    icon = 34
    pill_w = int(label_w + icon + 30 + 2 * 44)
    left, top = (width - pill_w) // 2, bottom - cta_h
    draw.rounded_rectangle((left, top, left + pill_w, bottom), radius=cta_h // 2, fill=ACCENT)
    cx, cy = left + 44, top + cta_h // 2
    draw.polygon([(cx, cy - icon // 2), (cx, cy + icon // 2), (cx + icon * 0.9, cy)], fill=INK)
    draw.text((cx + icon + 30, cy), cta, font=cta_face, fill=INK, anchor="lm")
    return image.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", help="la grabación original")
    parser.add_argument("--at", type=float, default=1.0,
                        help="segundo del vídeo montado (con --cuts) o de la grabación")
    parser.add_argument("--cuts", default=None)
    parser.add_argument("--title", required=True, help="el gancho, 3-7 palabras")
    parser.add_argument("--emphasis", default=None, help="la palabra que va en color")
    parser.add_argument("--cta", default=CTA)
    parser.add_argument("--preset", default="tiktok")
    parser.add_argument("-o", "--output", default="portada.jpg")
    args = parser.parse_args()

    platform = preset(args.preset)
    seconds = (output_to_source(args.at, read_json(args.cuts)["segments"])
               if args.cuts else args.at)
    frame = grab(args.video, seconds, platform["width"], platform["height"])
    cover(frame, args.title, args.emphasis, args.cta).save(args.output, quality=92)
    print(f"portada -> {args.output}")


if __name__ == "__main__":
    main()
