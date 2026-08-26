"""Miniatura terminada: fondo generado + tu cara real + rótulo.

    python thumbnail.py fondo.png --face fotograma.png --text "REPO QUE NO CONOCES"

Los generadores de imagen no pegan una cara: con una foto de referencia hacen
transferencia de identidad y devuelven a alguien *parecido*. En un canal personal
eso se nota y resta. Así que el fondo lo genera el modelo, la cara se recorta de
la grabación, y aquí se juntan — la cara es la de verdad porque es un píxel del
vídeo, no una interpretación.

El recorte necesita `rembg`, que no viene por defecto porque su modelo pesa un
giga. Si la imagen de la cara ya trae canal alfa, no hace falta.
"""
import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw, ImageEnhance, ImageFont  # noqa: E402

from common import FONTS  # noqa: E402

WIDTH, HEIGHT = 1280, 720

FACE_HEIGHT = 0.92      # del alto, para que la cara llene sin recortarse la coronilla
FACE_MARGIN = 0.02      # aire contra el borde
TEXT_WIDTH = 0.94       # el rótulo ocupa casi todo el ancho de su lado
TEXT_MAX_LINES = 3
TEXT_MAX_BLOCK = 0.62   # del alto: más que esto y compite con la cara
LINE_GAP = 0.04
STROKE = 0.06           # del alto de la fuente; el contorno es lo que lo hace legible
FACE_LIFT = 1.28        # la cara tiene que ser lo más luminoso del cuadro
FACE_CONTRAST = 1.12
BG_DIM = 0.72           # el fondo generado siempre sale más claro de lo que conviene
SCRIM = 0.62            # degradado lateral bajo el texto, no una caja

# El rótulo se elige sin tildes ni ñ para que el generador no lo destroce, pero
# aquí lo dibuja Pillow, así que da igual: se avisa por si el texto viaja al prompt.
ACCENTS = "áéíóúüñÁÉÍÓÚÜÑ"


def cover(image, width, height):
    """Escala y recorta al centro para llenar el marco sin deformar."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)),
                           Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def cutout(path):
    """La persona sin fondo. Si ya viene con alfa, se respeta."""
    image = Image.open(path)
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255:
        return image
    try:
        from rembg import remove
    except ImportError:
        sys.exit("para recortar la cara hace falta rembg: pip install rembg onnxruntime\n"
                 "(o pasa una imagen que ya venga con transparencia)")
    return remove(image.convert("RGB")).convert("RGBA")


def lift(image, amount, contrast):
    """Sube la cara sin tocar el alfa.

    El material de este flujo se graba oscuro a propósito (YAVG por debajo de
    50 es lo normal en una habitación con contraluz), y lo que en el vídeo es
    ambiente, en una miniatura de 168 px es una cara que no se distingue.
    """
    alpha = image.getchannel("A")
    rgb = ImageEnhance.Contrast(
        ImageEnhance.Brightness(image.convert("RGB")).enhance(amount)).enhance(contrast)
    rgb = rgb.convert("RGBA")
    rgb.putalpha(alpha)
    return rgb


def trim(image):
    """Recorta el alfa vacío: sin esto el sujeto queda flotando en su marco."""
    box = image.getchannel("A").getbbox()
    return image.crop(box) if box else image


def fit_text(draw, text, band, height, path):
    """Líneas y fuente que llenan el ancho disponible sin pasarse de alto.

    Un rótulo se lee a 168x94 px o no se lee: por eso se busca el tamaño más
    grande que quepa, partiendo en varias líneas si hace falta, en vez de meter
    la frase entera en una sola línea diminuta.
    """
    best = None
    for count in range(1, TEXT_MAX_LINES + 1):
        lines = textwrap.wrap(text, width=max(1, -(-len(text) // count))) or [text]
        size = 12
        while size < 400:
            probe = ImageFont.truetype(str(path), size + 4)
            widest = max(draw.textbbox((0, 0), line, font=probe)[2] for line in lines)
            block = (probe.size * (1 + LINE_GAP)) * len(lines)
            if widest > band or block > height * TEXT_MAX_BLOCK:
                break
            size += 4
        font = ImageFont.truetype(str(path), size)
        widest = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
        if best is None or widest * size > best[0]:
            best = (widest * size, lines, font)
    return best[1], best[2]


def side_scrim(canvas, side, band):
    """Degradado lateral para que el texto agarre sobre cualquier fondo.

    Una caja negra detrás del rótulo se ve como una caja negra. Un degradado que
    muere hacia el centro no se ve, y hace el mismo trabajo.
    """
    width, height = canvas.size
    mask = Image.new("L", (width, 1))
    for x in range(width):
        edge = x / width if side == "right" else 1 - x / width
        value = max(0.0, 1 - edge / 0.75) ** 1.6
        mask.putpixel((x, 0), round(255 * SCRIM * value))
    dark = Image.new("RGB", canvas.size, (0, 0, 0))
    canvas.paste(dark, (0, 0), mask.resize(canvas.size))


def font_file(name):
    hit = next(FONTS.glob(f"{name}*.ttf"), None)
    if not hit:
        sys.exit(f"no encuentro la fuente {name} en {FONTS}. Ejecuta scripts/setup.ps1")
    return hit


def compose(background, face, text, side, font_name, args_lift=FACE_LIFT):
    canvas = cover(Image.open(background).convert("RGB"), WIDTH, HEIGHT)
    # Un fondo generado casi siempre llega más claro de lo que le conviene a una
    # miniatura: la persona tiene que ser lo más luminoso del cuadro.
    canvas = Image.blend(Image.new("RGB", canvas.size, (0, 0, 0)), canvas, BG_DIM)

    person = lift(trim(cutout(face)), args_lift, FACE_CONTRAST)
    scale = HEIGHT * FACE_HEIGHT / person.height
    person = person.resize((round(person.width * scale), round(person.height * scale)),
                           Image.LANCZOS)
    margin = round(WIDTH * FACE_MARGIN)
    x = WIDTH - person.width - margin if side == "right" else margin
    canvas.paste(person, (x, HEIGHT - person.height), person)

    if not text:
        return canvas

    # El lado libre es el contrario al de la persona; ahí cabe el rótulo sin taparla.
    band = max(WIDTH - person.width - margin, WIDTH * 0.45) * TEXT_WIDTH
    side_scrim(canvas, side, band)

    draw = ImageDraw.Draw(canvas, "RGBA")
    lines, font = fit_text(draw, text, band, HEIGHT, font_file(font_name))
    step = round(font.size * (1 + LINE_GAP))
    block = step * len(lines)
    y = round((HEIGHT - block) / 2)
    stroke = max(2, round(font.size * STROKE))

    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        wide = box[2] - box[0]
        x = margin * 2 if side == "right" else WIDTH - wide - margin * 2
        draw.text((x, y - box[1]), line, font=font, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(8, 8, 12))
        y += step
    return canvas


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("background", help="imagen 16:9 generada, sin personas")
    parser.add_argument("--face", required=True, help="fotograma del vídeo con la persona")
    parser.add_argument("--text", default="", help="rótulo, en mayúsculas y corto")
    parser.add_argument("--side", choices=("left", "right"), default="right",
                        help="lado donde va la persona (el texto va al otro)")
    parser.add_argument("--font", default="Anton", help="fuente de vendor/fonts")
    parser.add_argument("--lift", type=float, default=FACE_LIFT,
                        help="brillo de la cara sobre el fondo (1.0 = sin tocar)")
    parser.add_argument("-o", "--output", default="miniatura.png")
    return parser.parse_args()


def main():
    args = parse_args()
    if any(c in args.text for c in ACCENTS):
        print("aviso: el rótulo lleva tilde o ñ. Aquí se dibuja bien, pero si ese "
              "mismo texto va dentro del prompt de imagen, el generador lo destrozará.")
    compose(args.background, args.face, args.text, args.side, args.font,
            args.lift).save(args.output)
    print(f"{WIDTH}x{HEIGHT} -> {args.output}")


if __name__ == "__main__":
    main()
