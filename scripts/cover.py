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
from pathlib import Path

import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

from common import FONTS, accent, hex_rgb, output_to_source, preset, read_json

INK = (8, 8, 12)
# Look de la portada: oscuro y con contraste, no «iluminado». Subir la luz a un
# fotograma grabado en penumbra lo deja lavado y con ruido, y se ve barato; en
# tema oscuro la cara sale de la sombra y el texto blanco es lo más brillante.
EXPOSURE = 0.27                 # brillo medio al que se lleva el fotograma
GAIN_RANGE = (0.6, 1.35)        # cuánto se puede bajar o subir para llegar
SATURATION = 0.86
VIGNETTE = 0.62                 # oscuridad de las esquinas (0 = nada)
FACE_Y = 0.36                   # centro de la viñeta: donde suele estar la cara
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


def _curve(shadows, highlights):
    """LUT de un canal: contraste en S, con las sombras y las altas desplazadas."""
    lut = []
    for i in range(256):
        u = i / 255
        s = 0.5 - 0.5 * math.cos(math.pi * u)          # S suave
        v = (0.55 * s + 0.45 * u) ** 1.12               # negros aplastados
        v += shadows * (1 - u) ** 3 + highlights * u ** 2
        lut.append(max(0, min(255, round(255 * v))))
    return lut


# Sombras frías y luces cálidas: casa con el contraluz azul del set y deja la
# piel en su sitio.
CURVES = (_curve(-0.010, 0.025), _curve(0.0, 0.0), _curve(0.035, -0.030))


def _vignette(size):
    """Máscara que oscurece hacia los bordes, centrada en la cara."""
    small = Image.new("L", (54, 96))
    for y in range(96):
        for x in range(54):
            dx, dy = (x / 53 - 0.5) / 0.62, (y / 95 - FACE_Y) / 0.78
            small.putpixel((x, y), round(255 * VIGNETTE * min(1.0, (dx * dx + dy * dy) ** 1.2)))
    return small.resize(size, Image.BICUBIC)


def grade(frame):
    """Exposición a tema oscuro, contraste, tono frío/cálido, viñeta y nitidez."""
    light = ImageStat.Stat(frame.convert("L")).mean[0] / 255
    low, high = GAIN_RANGE
    image = ImageEnhance.Brightness(frame).enhance(
        min(high, max(low, EXPOSURE / max(light, 0.05))))
    image = image.point(CURVES[0] + CURVES[1] + CURVES[2])
    image = ImageEnhance.Color(image).enhance(SATURATION)
    image = Image.composite(Image.new("RGB", image.size, INK), image, _vignette(image.size))
    # Afilado fino: a 1080 px se lee como «alta resolución», sin halo.
    return image.filter(ImageFilter.UnsharpMask(radius=2.0, percent=70, threshold=2))


def _shadow(size, draw_fn, blur):
    """Una sombra suave detrás del texto: lo separa del fondo sin caja."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(blur))


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


def logo_art(logo, size, workdir):
    """El logo de la herramienta para la portada: en 3D si se puede, si no plano.

    `logo` es un .svg o un .png de icons.py (que deja su .svg al lado).
    """
    import three_d

    logo = Path(logo)
    svg = logo if logo.suffix.lower() == ".svg" else three_d.svg_for(logo)
    if svg and three_d.available():
        return Image.open(three_d.logo_still(svg, size, Path(workdir) / "logo3d.png")).convert("RGBA")
    if svg:
        three_d.warn_once("el logo de la portada")
    if logo.suffix.lower() == ".png":
        art = Image.open(logo).convert("RGBA")
        return art.resize((size, round(art.height * size / art.width)), Image.LANCZOS)
    return None


def place_logo(image, art, side="left"):
    """Arriba, en una esquina y dentro del 4:5: ahí no tapa ni la cara ni el título."""
    width, height = image.size
    x = int(width * 0.06) if side == "left" else int(width * 0.94) - art.width
    y = int(height * 0.165)
    # Sombra de contacto: el logo se posa sobre la imagen en vez de flotar pegado.
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((x + art.width * 0.12, y + art.height * 0.80,
                                    x + art.width * 0.88, y + art.height * 0.98),
                                   fill=(0, 0, 0, 170))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(art.width * 0.06)))
    image.alpha_composite(art, (x, y))


def cover(frame, title, emphasis=None, cta=CTA, logo=None, logo_side="left"):
    width, height = frame.size
    image = grade(frame).convert("RGBA")
    if logo is not None:
        place_logo(image, logo, logo_side)

    # Degradado oscuro desde abajo: agarra el texto sin la caja que lo haría plantilla.
    shade = Image.new("L", (1, height))
    for y in range(height):
        shade.putpixel((0, y), int(248 * min(1.0, max(0.0, (y / height - 0.36) / 0.5)) ** 1.2))
    dark = Image.new("RGBA", (width, height), INK + (255,))
    dark.putalpha(shade.resize((width, height)))
    image.alpha_composite(dark)

    draw = ImageDraw.Draw(image)
    brand = hex_rgb(accent())      # la palabra clave y la pastilla, en el color del canal
    # Sobre un acento oscuro (el azul del canal) el texto de la pastilla va en
    # blanco; sobre uno claro (naranja, amarillo), en tinta.
    light = sum(c * w for c, w in zip(brand, (0.2126, 0.7152, 0.0722))) / 255
    pill_ink = (255, 255, 255) if light < 0.45 else INK
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
    top_y = y

    def title_ink(target, fill=None):
        yy = top_y
        for line in lines:
            x = (width - target.textlength(" ".join(line), font=face)) / 2
            target.text((x, yy), " ".join(line), font=face,
                        fill=fill, stroke_width=stroke, stroke_fill=fill)
            yy += line_h

    image.alpha_composite(_shadow(image.size, lambda d: title_ink(d, (0, 0, 0, 230)),
                                  face.size * 0.14))
    for line in lines:
        x = (width - draw.textlength(" ".join(line), font=face)) / 2
        for word in line:
            colour = brand if word.strip(".,¿?¡!") in marked else (255, 255, 255)
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
    image.alpha_composite(_shadow(image.size, lambda d: d.rounded_rectangle(
        (left, top + 10, left + pill_w, bottom + 10), radius=cta_h // 2, fill=(0, 0, 0, 200)), 18))
    draw.rounded_rectangle((left, top, left + pill_w, bottom), radius=cta_h // 2, fill=brand)
    cx, cy = left + 44, top + cta_h // 2
    draw.polygon([(cx, cy - icon // 2), (cx, cy + icon // 2), (cx + icon * 0.9, cy)], fill=pill_ink)
    draw.text((cx + icon + 30, cy), cta, font=cta_face, fill=pill_ink, anchor="lm")
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
    parser.add_argument("--logo", default=None,
                        help="el .svg o .png (de icons.py) de la herramienta del vídeo: sale en 3D")
    parser.add_argument("--logo-side", choices=("left", "right"), default="left",
                        help="esquina de arriba para el logo: la que no tape la cara")
    parser.add_argument("--preset", default="tiktok")
    parser.add_argument("-o", "--output", default="portada.jpg")
    args = parser.parse_args()

    platform = preset(args.preset)
    seconds = (output_to_source(args.at, read_json(args.cuts)["segments"])
               if args.cuts else args.at)
    frame = grab(args.video, seconds, platform["width"], platform["height"])
    logo = None
    if args.logo:
        logo = logo_art(args.logo, int(platform["width"] * 0.27), Path(args.output).resolve().parent)
    cover(frame, args.title, args.emphasis, args.cta, logo, args.logo_side).save(
        args.output, quality=95, subsampling=0)
    print(f"portada -> {args.output}")


if __name__ == "__main__":
    main()
