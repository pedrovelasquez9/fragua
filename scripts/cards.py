"""Render annotation cards as transparent PNGs, one per card in plan.json.

    python cards.py plan.json --preset tiktok --outdir cards/

ASS can only put a rectangle behind a line of text, which is why cards drawn
that way look like slide titles. These are real graphics: rounded panels with a
divided header, bullet lists, connected flow diagrams and stat blocks.

Kinds, chosen per card with "kind":

  panel      título + párrafo, separados por una banda de acento
  bullets    título + lista con viñetas
  flow       nodos conectados, tipo mapa mental
  stat       una cifra grande + su etiqueta
  chip       una pastilla con una frase
  title      texto grande sin panel, para la banda de un pullback
  compare    dos o tres columnas enfrentadas: X frente a Y
  checklist  lista con casillas, marcadas hasta `done`
  code       un comando o un fragmento, en monoespaciada
  section    etiqueta de sección arriba a la izquierda: «02 · TÍTULO»
  logos      fila de logos o iconos, con check o uno destacado
  stamp      sello rojo en diagonal con una palabra
"""
import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import FONTS, ROOT, preset, read_json, resolve_asset, write_json

RADIUS = 26

# Colores propios de estos tres tipos, fuera del tema del preset: el número de
# sección es naranja y el sello rojo en cualquier canal, igual que el verde de
# un check no depende del color de acento.
SECTION_NUMBER = (255, 138, 61, 255)
SECTION_TEXT = (240, 228, 205, 255)
STAMP_RED = (240, 52, 58, 255)
CHECK_GREEN = (52, 199, 89, 255)
PAD = 34
SHADOW_BLUR = 18


def hex_rgba(value, alpha=255):
    """'#14161F' -> (20, 22, 31, alpha)."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def load_mono(size, weight="Medium"):
    """JetBrains Mono para las cards de código; Roboto si no está instalada.

    Un comando en proporcional se lee como una frase, no como algo que se
    teclea: la monoespaciada es lo que dice «esto es código» antes de leerlo.
    """
    path = FONTS / "JetBrainsMono-Variable.ttf"
    if not path.exists():
        print("  aviso: falta JetBrainsMono-Variable.ttf — ejecuta el setup; "
              "la card de código sale en Roboto")
        return load_font(size, weight)
    font = ImageFont.truetype(str(path), size)
    try:
        font.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass
    return font


def load_font(size, weight="Black"):
    """Roboto is a variable font; pick the real weight instead of faking bold."""
    path = FONTS / "Roboto-Variable.ttf"
    if not path.exists():
        return ImageFont.load_default(size)
    font = ImageFont.truetype(str(path), size)
    try:
        font.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass  # not a variable build: whatever the default instance is
    return font


def text_size(draw, text, font):
    """(width, height) of the ink, not of the line box."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def panel(image, box, theme, radius=RADIUS):
    """Rounded panel with a soft shadow and a hairline border."""
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x0 + 4, y0 + 8, x1 + 4, y1 + 10), radius, fill=(0, 0, 0, 150))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR)))
    ImageDraw.Draw(image).rounded_rectangle(
        box, radius, fill=theme["bg"], outline=theme["line"], width=2)


def wrap(draw, text, font, max_width):
    """Greedy word wrap measured against the actual font."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if text_size(draw, candidate, font)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_panel(spec, theme, width, base):
    """Header band in the accent colour, body paragraph underneath."""
    title_font = load_font(int(base * 0.82))
    body_font = load_font(int(base * 0.72), "Medium")
    image = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    card_width = int(width * 0.80)
    inner_width = card_width - PAD * 2

    title = spec.get("title", "")
    body = wrap(draw, spec.get("body", "").replace("\n", " "), body_font, inner_width)
    title_height = text_size(draw, title, title_font)[1] if title else 0
    line_height = int(base * 1.02)
    header_height = title_height + PAD if title else 0
    card_height = header_height + len(body) * line_height + PAD

    left = (width - card_width) // 2
    panel(image, (left, 0, left + card_width, card_height), theme)

    if title:
        # Accent band, clipped to the panel's rounded top by erasing the corners.
        band = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(band).rounded_rectangle(
            (left, 0, left + card_width, header_height + RADIUS), RADIUS,
            fill=theme["accent_bg"])
        ImageDraw.Draw(band).rectangle(
            (left, header_height, left + card_width, header_height + RADIUS),
            fill=(0, 0, 0, 0))
        image.alpha_composite(band)
        title_width = text_size(draw, title, title_font)[0]
        draw.text(((width - title_width) // 2, PAD // 2 + 2), title,
                  font=title_font, fill=theme["accent"])
        draw.line((left + PAD, header_height, left + card_width - PAD, header_height),
                  fill=theme["line"], width=2)

    y = header_height + PAD // 2
    for line in body:
        line_width = text_size(draw, line, body_font)[0]
        draw.text(((width - line_width) // 2, y), line, font=body_font, fill=theme["fg"])
        y += line_height
    return image.crop((0, 0, width, card_height + 20))


def draw_bullets(spec, theme, width, base):
    """Header plus a list with accent markers."""
    title_font = load_font(int(base * 0.82))
    item_font = load_font(int(base * 0.76), "Medium")
    image = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    items = spec.get("items") or spec.get("body", "").split("\n")
    card_width = int(width * 0.80)
    left = (width - card_width) // 2

    title = spec.get("title", "")
    title_height = text_size(draw, title, title_font)[1] if title else 0
    line_height = int(base * 1.15)
    header_height = title_height + PAD if title else 0
    card_height = header_height + len(items) * line_height + PAD

    panel(image, (left, 0, left + card_width, card_height), theme)
    if title:
        draw.text((left + PAD, PAD // 2 + 2), title, font=title_font, fill=theme["accent"])
        draw.line((left + PAD, header_height, left + card_width - PAD, header_height),
                  fill=theme["line"], width=2)

    # anchor="lm" puts the text's vertical middle on cy, so the marker lines up
    # with the words instead of floating near the cap line like a superscript.
    # anchor="lm" puts the text's vertical middle on the marker's centre, so the
    # bullet lines up with the words instead of floating near the cap line.
    center_y = header_height + PAD // 2 + line_height // 2
    marker = max(10, base // 6)
    for item in items:
        draw.rounded_rectangle(
            (left + PAD, center_y - marker // 2, left + PAD + marker, center_y + marker // 2),
            marker // 3, fill=theme["accent"])
        draw.text((left + PAD + int(marker * 1.9), center_y), item,
                  font=item_font, fill=theme["fg"], anchor="lm")
        center_y += line_height
    return image.crop((0, 0, width, card_height + 20))


def draw_flow(spec, theme, width, base):
    """Root node with connectors down to its children — mind-map style.

    Org-chart layout: root pill top-left, one vertical spine, horizontal stubs
    into each node. Straight elbows read as structure; diagonals read as noise.
    """
    root_font = load_font(int(base * 0.80))
    node_font = load_font(int(base * 0.68), "Medium")
    image = Image.new("RGBA", (width, width * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    nodes = spec.get("nodes") or spec.get("body", "").split("\n")
    root = spec.get("root") or spec.get("title", "")

    padding, gap = int(PAD * 0.8), int(base * 0.46)
    margin = int(width * 0.10)
    spine_x = margin + int(base * 0.55)
    node_x = margin + int(base * 1.5)
    node_width = width - node_x - margin

    root_width, root_text_height = text_size(draw, root, root_font)
    root_height = root_text_height + padding * 2
    panel(image, (margin, 0, margin + root_width + padding * 2, root_height),
          theme, radius=root_height // 2)
    draw.text((margin + padding, root_height // 2), root, font=root_font,
              fill=theme["accent"], anchor="lm")

    rows, y = [], root_height + gap
    for node in nodes:
        height = text_size(draw, node, node_font)[1] + padding * 2
        rows.append((node, y, height))
        y += height + gap

    last_center_y = rows[-1][1] + rows[-1][2] // 2
    draw.line((spine_x, root_height, spine_x, last_center_y), fill=theme["line"], width=3)

    for node, top, height in rows:
        center_y = top + height // 2
        draw.line((spine_x, center_y, node_x, center_y), fill=theme["line"], width=3)
        panel(image, (node_x, top, node_x + node_width, top + height), theme,
              radius=height // 3)
        draw.ellipse((spine_x - 7, center_y - 7, spine_x + 7, center_y + 7),
                     fill=theme["accent"])
        draw.text((node_x + padding, center_y), node, font=node_font,
                  fill=theme["fg"], anchor="lm")
    return image.crop((0, 0, width, y - gap + 20))


def draw_stat(spec, theme, width, base):
    """One big figure with its caption underneath."""
    value_font = load_font(int(base * 2.1))
    label_font = load_font(int(base * 0.70), "Medium")
    image = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    value, label = str(spec.get("value", "")), spec.get("label", "")
    card_width = int(width * 0.72)
    left = (width - card_width) // 2

    value_width, value_height = text_size(draw, value, value_font)
    lines = wrap(draw, label, label_font, card_width - PAD * 2)
    line_height = int(base * 0.95)
    card_height = value_height + len(lines) * line_height + PAD * 2

    panel(image, (left, 0, left + card_width, card_height), theme)
    draw.text(((width - value_width) // 2, PAD // 2), value,
              font=value_font, fill=theme["accent"])
    y = value_height + PAD
    for line in lines:
        line_width = text_size(draw, line, label_font)[0]
        draw.text(((width - line_width) // 2, y), line, font=label_font, fill=theme["fg"])
        y += line_height
    return image.crop((0, 0, width, card_height + 20))


def draw_chip(spec, theme, width, base):
    """A single rounded pill. This is what a title looks like as a card."""
    font = load_font(int(base * 0.86))
    image = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    text = spec.get("title") or spec.get("content", "")
    text_width, text_height = text_size(draw, text, font)
    padding = int(PAD * 0.9)
    height = text_height + padding * 2
    left = (width - text_width) // 2 - padding
    panel(image, (left, 0, left + text_width + padding * 2, height),
          theme, radius=height // 2)
    draw.text((width // 2, height // 2), text, font=font,
              fill=theme["accent"], anchor="mm")
    return image.crop((0, 0, width, height + 20))


def draw_title(spec, theme, width, base):
    """Texto grande y suelto, sin panel detrás.

    Va en el hueco negro que abre un `pullback`. Ahí un panel oscuro sobre negro
    se ve como una caja flotando en la nada: lo que se lee es el texto solo.
    """
    font = load_font(int(base * 1.25))
    image = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines = wrap(draw, spec.get("title") or spec.get("body", ""), font, int(width * 0.86))
    line_height = int(base * 1.5)

    y = 0
    for line in lines:
        line_width = text_size(draw, line, font)[0]
        draw.text(((width - line_width) // 2, y), line, font=font, fill=theme["accent"])
        y += line_height
    return image.crop((0, 0, width, y + 16))


def draw_compare(spec, theme, width, base):
    """Columnas enfrentadas, cada una con su cabecera y sus puntos.

    Es la card de «X frente a Y», que es media explicación técnica: MCP frente a
    skill, antes frente a después. Una lista de viñetas lo cuenta en serie y
    obliga a recordar; dos columnas lo ponen lado a lado.
    """
    title_font = load_font(int(base * 0.82))
    head_font = load_font(int(base * 0.80))
    item_font = load_font(int(base * 0.66), "Medium")
    image = Image.new("RGBA", (width, width * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    columns = spec.get("columns") or []
    count = max(1, min(3, len(columns)))
    card_width = int(width * 0.86)
    left = (width - card_width) // 2
    col_width = (card_width - PAD * 2) // count

    title = spec.get("title", "")
    title_height = text_size(draw, title, title_font)[1] if title else 0
    header_height = title_height + PAD if title else 0
    head_height = int(base * 1.2)
    line_height = int(base * 0.98)

    wrapped = [[line for item in (col.get("items") or [])
                for line in wrap(draw, item, item_font, col_width - PAD)]
               for col in columns[:count]]
    rows = max((len(lines) for lines in wrapped), default=0)
    card_height = header_height + PAD // 2 + head_height + rows * line_height + PAD

    panel(image, (left, 0, left + card_width, card_height), theme)
    if title:
        title_width = text_size(draw, title, title_font)[0]
        draw.text(((width - title_width) // 2, PAD // 2 + 2), title,
                  font=title_font, fill=theme["fg"])
        draw.line((left + PAD, header_height, left + card_width - PAD, header_height),
                  fill=theme["line"], width=2)

    top = header_height + PAD // 2
    for index, (column, lines) in enumerate(zip(columns[:count], wrapped)):
        x0 = left + PAD + index * col_width
        center = x0 + col_width // 2
        if index:
            draw.line((x0, top + 6, x0, card_height - PAD // 2),
                      fill=theme["line"], width=2)
        draw.text((center, top + head_height // 2), column.get("title", ""),
                  font=head_font, fill=theme["accent"], anchor="mm")
        y = top + head_height
        for line in lines:
            draw.text((center, y + line_height // 2), line, font=item_font,
                      fill=theme["fg"], anchor="mm")
            y += line_height
    return image.crop((0, 0, width, card_height + 20))


def check_mark(draw, box, colour, width):
    """El trazo de la marca, en las mismas proporciones que dibuja la animada."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    draw.line([(x0 + w * 0.22, y0 + h * 0.52), (x0 + w * 0.42, y0 + h * 0.72),
               (x0 + w * 0.78, y0 + h * 0.30)], fill=colour, width=width, joint="curve")


def draw_checklist(spec, theme, width, base):
    """Casillas que se marcan hasta `done` (por defecto, todas).

    La versión animada las va marcando una a una, que es lo que hace que valga
    la pena: una lista de pasos que se van cumpliendo se sigue con la vista.
    """
    title_font = load_font(int(base * 0.82))
    item_font = load_font(int(base * 0.74), "Medium")
    image = Image.new("RGBA", (width, width * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    items = spec.get("items") or spec.get("body", "").split("\n")
    done = int(spec.get("done", len(items)))
    card_width = int(width * 0.80)
    left = (width - card_width) // 2

    title = spec.get("title", "")
    title_height = text_size(draw, title, title_font)[1] if title else 0
    header_height = title_height + PAD if title else 0
    line_height = int(base * 1.25)
    card_height = header_height + len(items) * line_height + PAD

    panel(image, (left, 0, left + card_width, card_height), theme)
    if title:
        draw.text((left + PAD, PAD // 2 + 2), title, font=title_font, fill=theme["accent"])
        draw.line((left + PAD, header_height, left + card_width - PAD, header_height),
                  fill=theme["line"], width=2)

    side = int(base * 0.72)
    stroke = max(3, side // 8)
    center_y = header_height + PAD // 2 + line_height // 2
    for index, item in enumerate(items):
        box = (left + PAD, center_y - side // 2, left + PAD + side, center_y + side // 2)
        ticked = index < done
        if ticked:
            draw.rounded_rectangle(box, side // 4, fill=theme["accent"])
            check_mark(draw, box, theme["bg"][:3] + (255,), stroke)
        else:
            draw.rounded_rectangle(box, side // 4, outline=theme["line"], width=stroke)
        colour = theme["fg"] if ticked else theme["fg"][:3] + (150,)
        draw.text((left + PAD + int(side * 1.55), center_y), item,
                  font=item_font, fill=colour, anchor="lm")
        center_y += line_height
    return image.crop((0, 0, width, card_height + 20))


def draw_code(spec, theme, width, base):
    """Una ventana de terminal con el comando dentro, en monoespaciada."""
    head_font = load_font(int(base * 0.56), "Medium")
    image = Image.new("RGBA", (width, width * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines = spec.get("lines") or spec.get("body", "").split("\n")
    prompt = spec.get("prompt", "$")
    card_width = int(width * 0.86)
    left = (width - card_width) // 2

    # Un comando no se parte: partido deja de poder copiarse de la pantalla y se
    # lee como dos órdenes. Se encoge la letra hasta que quepa la línea más larga.
    size = int(base * 0.66)
    while True:
        code_font = load_mono(size)
        widest = max(text_size(draw, f"{prompt} {line}" if prompt else line,
                               code_font)[0] for line in lines)
        if widest <= card_width - PAD * 2 or size <= int(base * 0.36):
            break
        size -= 2

    bar = int(base * 1.05)
    line_height = round(size * 1.48)     # sigue a la letra, no a base: se encoge con ella
    card_height = bar + PAD // 2 + len(lines) * line_height + PAD // 2 + PAD // 2

    panel(image, (left, 0, left + card_width, card_height), theme)
    # Barra de ventana: los tres puntos apagados dicen «terminal» sin robarle
    # protagonismo al comando, que es lo que se tiene que leer.
    draw.line((left, bar, left + card_width, bar), fill=theme["line"], width=2)
    dot = max(8, base // 7)
    for index, colour in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cx = left + PAD + index * int(dot * 2.4)
        draw.ellipse((cx, bar // 2 - dot // 2, cx + dot, bar // 2 + dot // 2),
                     fill=colour + (170,))
    title = spec.get("title", "")
    if title:
        draw.text((width // 2, bar // 2), title, font=head_font,
                  fill=theme["fg"][:3] + (160,), anchor="mm")

    y = bar + PAD // 2 + line_height // 2
    prompt_width = text_size(draw, prompt + " ", code_font)[0] if prompt else 0
    for line in lines:
        x = left + PAD
        if prompt:
            draw.text((x, y), prompt, font=code_font, fill=theme["accent"], anchor="lm")
            x += prompt_width
        draw.text((x, y), line, font=code_font, fill=theme["fg"], anchor="lm")
        y += line_height
    return image.crop((0, 0, width, card_height + 20))


def tracked(draw, xy, text, font, fill, tracking):
    """Texto con espaciado entre letras. Pillow no lo hace solo."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill, anchor="ls")
        x += draw.textlength(char, font=font) + tracking
    return x


def draw_section(spec, theme, width, base):
    """«02 · CLAUDE CODE, EL CONSTRUCTOR», arriba a la izquierda y sin panel.

    Se queda fija toda la sección. Estructura el vídeo sin interrumpirlo: quien
    llega a mitad sabe en qué parte está, y quien se queda ve que avanza.
    """
    number = str(spec.get("number", "")).zfill(2) if spec.get("number") is not None else ""
    title = str(spec.get("title", "")).upper()
    num_font = load_font(int(base * 0.62), "Black")
    title_font = load_font(int(base * 0.46), "Bold")
    height = int(base * 1.1)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    left, baseline = int(width * 0.065), int(base * 0.78)

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    x = left
    if number:
        x = tracked(sdraw, (x + 2, baseline + 2), number, num_font, (0, 0, 0, 200), 2)
        x += int(base * 0.28)
    tracked(sdraw, (x + 2, baseline + 2), title, title_font, (0, 0, 0, 200), int(base * 0.07))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))

    x = left
    if number:
        x = tracked(draw, (x, baseline), number, num_font, SECTION_NUMBER, 2)
        x += int(base * 0.28)
    tracked(draw, (x, baseline), title, title_font, SECTION_TEXT, int(base * 0.07))
    return image


def _logo_art(path, side):
    """El logo encajado en un cuadrado, sin deformarlo."""
    art = Image.open(resolve_asset(path)).convert("RGBA")
    art.thumbnail((side, side), Image.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(art, ((side - art.width) // 2, (side - art.height) // 2))
    return canvas


def draw_logos(spec, theme, width, base):
    """Una fila de logos en círculo —o iconos en cuadrado— con su nombre debajo.

    `check` en un elemento le pone el visto verde; `highlight` agranda uno y le
    da un anillo, para cuando la frase habla de ese y no de los demás.
    """
    items = spec.get("items") or []
    square = spec.get("shape") == "square"
    highlight = spec.get("highlight")
    label_font = load_font(int(base * 0.44), "Bold")
    title_font = load_font(int(base * 0.46), "Bold")
    count = max(1, len(items))
    side = min(int(base * 2.3), int(width * 0.82 / count) - int(base * 0.35))
    gap = int(base * 0.35)
    title = str(spec.get("title", "")).upper()
    top = int(base * 0.9) if title else int(base * 0.25)
    label_h = int(base * 0.75) if any(i.get("label") for i in items) else 0
    height = top + int(side * 1.2) + label_h + int(base * 0.2)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if title:
        title_w = text_size(draw, title, title_font)[0] + int(base * 0.07) * len(title)
        tracked(draw, ((width - title_w) // 2, int(base * 0.6)), title, title_font,
                SECTION_TEXT, int(base * 0.07))

    row = count * side + (count - 1) * gap
    x = (width - row) // 2
    for index, item in enumerate(items):
        big = index == highlight
        s = int(side * 1.14) if big else side
        cx, cy = x + side // 2, top + int(side * 0.6)
        box = (cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        ring = theme["accent"] if big else (0, 0, 0, 160)
        if square:
            gdraw.rounded_rectangle(box, s // 4, fill=ring)
        else:
            gdraw.ellipse(box, fill=ring)
        image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(int(base * 0.35))))
        inner = (box[0] + 4, box[1] + 4, box[2] - 4, box[3] - 4)
        if square:
            draw.rounded_rectangle(inner, s // 4, fill=(22, 24, 32, 240),
                                   outline=theme["accent"] if big else theme["line"], width=3)
        else:
            draw.ellipse(inner, fill=(22, 24, 32, 240),
                         outline=theme["accent"] if big else theme["line"], width=3)
        if item.get("file"):
            art = _logo_art(item["file"], int(s * 0.62))
            image.alpha_composite(art, (cx - art.width // 2, cy - art.height // 2))
        if item.get("check"):
            r = int(s * 0.17)
            bx, by = box[2] - r, box[1] + r
            draw.ellipse((bx - r, by - r, bx + r, by + r), fill=CHECK_GREEN,
                         outline=(12, 14, 20, 255), width=3)
            check_mark(draw, (bx - r, by - r, bx + r, by + r), (255, 255, 255, 255),
                       max(3, r // 3))
        if item.get("label"):
            draw.text((cx, top + int(side * 1.2) + int(base * 0.35)), item["label"],
                      font=label_font, fill=theme["fg"], anchor="mm")
        x += side + gap
    return image


def draw_stamp(spec, theme, width, base):
    """Un sello rojo en diagonal: EQUIVOCADA, NO SIRVE.

    Es puntuación, no información: marca un veredicto con el golpe que tiene la
    frase dicha. Por eso una palabra o dos, y poco tiempo en pantalla.
    """
    text = str(spec.get("title") or spec.get("text") or "").upper()
    font = load_font(int(base * 1.35), "Black")
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw, th = text_size(probe, text, font)
    pad_x, pad_y, stroke = int(base * 0.45), int(base * 0.3), max(6, base // 7)
    w, h = tw + pad_x * 2 + stroke * 2, th + pad_y * 2 + stroke * 2
    stamp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(stamp)
    sdraw.rounded_rectangle((stroke // 2, stroke // 2, w - stroke // 2, h - stroke // 2),
                            int(base * 0.25), outline=STAMP_RED, width=stroke)
    sdraw.text((w // 2, h // 2), text, font=font, fill=STAMP_RED, anchor="mm")
    angle = float(spec.get("angle", -8))
    stamp = stamp.rotate(-angle, resample=Image.BICUBIC, expand=True)
    image = Image.new("RGBA", (width, stamp.height + 20), (0, 0, 0, 0))
    image.alpha_composite(stamp, ((width - stamp.width) // 2, 10))
    return image


KINDS = {"panel": draw_panel, "bullets": draw_bullets, "flow": draw_flow,
         "title": draw_title, "stat": draw_stat, "chip": draw_chip,
         "compare": draw_compare, "checklist": draw_checklist, "code": draw_code,
         "section": draw_section, "logos": draw_logos, "stamp": draw_stamp}


def build_theme(card_settings):
    """One accent colour drives the text, the hairline border and the header band."""
    return {
        "bg": hex_rgba(card_settings["bg"], card_settings["bg_alpha"]),
        "fg": hex_rgba(card_settings["fg"]),
        "accent": hex_rgba(card_settings["accent"]),
        "accent_bg": hex_rgba(card_settings["accent"], 30),
        "line": hex_rgba(card_settings["accent"], 90),
    }


def render_all(cards, platform, output_dir):
    """Rasterise every card to output_dir/cardNN.png, in plan order.

    render.py finds them by that index, so the numbering is the contract between
    the two scripts: reorder plan.json and you must re-run this.
    """
    theme = build_theme(platform["card"])
    base_size = platform["card"]["base_size"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for index, spec in enumerate(cards):
        kind = spec.get("kind", "panel")
        if kind not in KINDS:
            raise SystemExit(f"card {index}: kind '{kind}' desconocido. Usa: {', '.join(KINDS)}")
        image = KINDS[kind](spec, theme, platform["width"], base_size)
        path = output_dir / f"card{index:02d}.png"
        image.save(path)
        paths.append(path)
        print(f"  {kind:8} {image.width}x{image.height}  {path.name}")
    return paths


REMOTION = ROOT / "remotion"


def remotion_ready():
    """Whether the animated renderer can run: Node on PATH and deps installed."""
    return bool(shutil.which("npx")) and (REMOTION / "node_modules").is_dir()


def with_inline_images(spec):
    """Los logos entran en las props como data URL: Remotion no ve el disco."""
    if spec.get("kind") != "logos":
        return spec
    import base64
    import mimetypes

    items = []
    for item in spec.get("items", []):
        item = dict(item)
        if item.get("file"):
            path = Path(resolve_asset(item["file"]))
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            item["src"] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
        items.append(item)
    return {**spec, "items": items}


def render_animated(cards, platform, output_dir):
    """Render each card as a ProRes 4444 clip with alpha, animation baked in.

    Same plan.json entries as the still renderer — the React components read the
    spec directly, so nothing has to be kept in sync between Python and TS.
    """
    if not remotion_ready():
        raise SystemExit(
            "las cards animadas necesitan Node y las dependencias de remotion/.\n"
            "Ejecuta /fragua:setup, o  npm install  dentro de remotion/.")

    # staticFile() sólo lee de public/, así que la fuente vive ahí mientras dure
    # el render. Es la misma que usa Pillow: una sola fuente de verdad.
    for name in ("Roboto-Variable.ttf", "JetBrainsMono-Variable.ttf"):
        font = FONTS / name
        if font.exists():
            (REMOTION / "public").mkdir(exist_ok=True)
            shutil.copyfile(font, REMOTION / "public" / font.name)

    # Un bundle por edición en vez de uno por card: son 3.7 s frente a ~10 s de
    # arranque en cada render. Se rehace siempre, que sale más barato que llevar
    # la cuenta de si el TSX ha cambiado desde la última vez.
    npx = shutil.which("npx")
    bundled = subprocess.run([npx, "remotion", "bundle", "--log=error"], cwd=REMOTION,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    if bundled.returncode != 0:
        raise SystemExit(f"remotion bundle falló:\n{(bundled.stderr or bundled.stdout)[-2000:]}")

    settings = platform["card"]
    theme = {"bg": settings["bg"], "bgAlpha": settings["bg_alpha"],
             "fg": settings["fg"], "accent": settings["accent"]}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for index, spec in enumerate(cards):
        kind = spec.get("kind", "panel")
        if kind not in KINDS:
            raise SystemExit(f"card {index}: kind '{kind}' desconocido. Usa: {', '.join(KINDS)}")
        path = output_dir / f"card{index:02d}.mov"
        props = output_dir / f"card{index:02d}.props.json"
        write_json(props, {"kind": kind, "dur": float(spec.get("dur", 3)),
                           "width": platform["width"], "base": settings["base_size"],
                           "theme": theme, "spec": with_inline_images(spec)})
        result = subprocess.run(
            [npx, "remotion", "render", "build", "Card",
             str(path.resolve()), f"--props={props.resolve()}", "--log=error"],
            cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise SystemExit(f"card {index} ({kind}) falló en remotion:\n"
                             f"{(result.stderr or result.stdout)[-2000:]}")
        props.unlink(missing_ok=True)
        paths.append(path)
        print(f"  {kind:8} animada  {path.name}")
    return paths


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("--preset", default="tiktok")
    parser.add_argument("--outdir", default="cards")
    parser.add_argument("--animated", action="store_true",
                        help="anima las cards con remotion en vez de rasterizarlas quietas")
    return parser.parse_args()


def main():
    args = parse_args()
    cards = read_json(args.plan).get("cards", [])
    if not cards:
        print("plan.json no tiene cards")
        return
    draw = render_animated if args.animated else render_all
    draw(cards, preset(args.preset), args.outdir)
    print(f"{len(cards)} cards -> {args.outdir}/")


if __name__ == "__main__":
    main()
