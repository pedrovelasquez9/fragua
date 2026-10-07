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

from common import FONTS, ROOT, accent, hex_rgb, preset, read_json, resolve_asset, write_json

RADIUS = 26

# Colores propios de estos tres tipos, fuera del tema del preset: el número de
# sección es naranja y el sello rojo en cualquier canal, igual que el verde de
# un check no depende del color de acento.
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


# «Problema → solución → código» es una cadena, no una frase: cada paso va en su
# propia pastilla y las flechas entre ellas. La animada los hace llegar de uno en
# uno; aquí se dibujan todos, con la misma forma.
NODE_ARROWS = ("→", "->")


def chip_nodes(text):
    """Los pasos de un chip con flechas, o [] si es un chip normal."""
    import re

    parts = [p for p in re.split(r"\s*(?:→|->)\s*", text) if p]
    return parts if len(parts) > 1 else []


def draw_node_chain(nodes, theme, width, base):
    """Una pastilla por nodo y una flecha entre cada dos, centradas."""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    padding, arrow_w = int(PAD * 0.7), int(base * 1.0)
    size = int(base * 0.86)
    # Se encoge la letra hasta que la cadena entera quepa en el ancho.
    while size > int(base * 0.4):
        font = load_font(size)
        widths = [text_size(probe, node, font)[0] + padding * 2 for node in nodes]
        total = sum(widths) + arrow_w * (len(nodes) - 1)
        if total <= width * 0.94:
            break
        size -= 2
    text_h = text_size(probe, "Ág", font)[1]
    height = text_h + padding * 2
    image = Image.new("RGBA", (width, height + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = (width - total) // 2
    for index, (node, w) in enumerate(zip(nodes, widths)):
        panel(image, (x, 0, x + w, height), theme, radius=height // 2)
        draw.text((x + w // 2, height // 2), node, font=font, fill=theme["accent"], anchor="mm")
        x += w
        if index < len(nodes) - 1:
            mid = height // 2
            head = max(8, arrow_w // 4)
            draw.line((x + 8, mid, x + arrow_w - 10, mid), fill=theme["accent"], width=4)
            draw.polygon([(x + arrow_w - 6, mid), (x + arrow_w - 6 - head, mid - head * 0.7),
                          (x + arrow_w - 6 - head, mid + head * 0.7)], fill=theme["accent"])
            x += arrow_w
    return image


def draw_chip(spec, theme, width, base):
    """A single rounded pill. This is what a title looks like as a card."""
    nodes = chip_nodes(str(spec.get("title") or spec.get("content", "")))
    if nodes:
        return draw_node_chain(nodes, theme, width, base)
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
        x = tracked(draw, (x, baseline), number, num_font, hex_rgb(accent()) + (255,), 2)
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


# --- diagrama ----------------------------------------------------------------
# Un mapa de piezas alrededor de un núcleo que se enciende pieza a pieza. La
# colocación se calcula aquí y viaja en las props: la versión fija y la animada
# dibujan exactamente los mismos nodos y las mismas curvas.

# Los grupos toman color en orden de aparición: el primero el del canal y el
# resto de la paleta neón de los iconos, en un orden sin vecinos parecidos.
DIAGRAM_NEON = ("#22E584", "#8B5CF6", "#FFD43B", "#FF5C9A", "#22D3EE", "#FF8A3D", "#A3E635")
SIDES = ("left", "right", "top", "bottom")
# Piezas por lado en horizontal; en vertical, dos columnas arriba y abajo.
SIDE_CAPACITY = {"left": 5, "right": 5, "top": 3, "bottom": 4}


def diagram_colors(nodes, brand):
    groups = []
    for node in nodes:
        if node.get("group", "") not in groups:
            groups.append(node.get("group", ""))
    palette = (brand, *DIAGRAM_NEON)
    return {g: palette[i % len(palette)] for i, g in enumerate(groups)}


def diagram_active(spec, nodes):
    """`active` admite el índice o el texto de la pieza."""
    active = spec.get("active")
    if isinstance(active, str):
        labels = [n.get("label", "") for n in nodes]
        if active not in labels:
            raise SystemExit(f"diagram: active '{active}' no es ninguna pieza ({', '.join(labels)})")
        return labels.index(active)
    return -1 if active is None else int(active)


def _curve_side(node, hub):
    """Del lateral del nodo al del núcleo, con tangentes horizontales."""
    left = node["x"] + node["w"] / 2 < hub["x"] + hub["w"] / 2
    sx = node["x"] + node["w"] if left else node["x"]
    ex = hub["x"] if left else hub["x"] + hub["w"]
    sy, ey = node["y"] + node["h"] / 2, hub["y"] + hub["h"] / 2
    mx = (sx + ex) / 2
    return f"M{sx:.0f},{sy:.0f} C{mx:.0f},{sy:.0f} {mx:.0f},{ey:.0f} {ex:.0f},{ey:.0f}", (sx, sy), (ex, ey)


def _curve_vertical(node, hub):
    """De arriba o abajo del nodo al borde del núcleo que le queda enfrente."""
    above = node["y"] < hub["y"]
    cx, hx = node["x"] + node["w"] / 2, hub["x"] + hub["w"] / 2
    sy = node["y"] + node["h"] if above else node["y"]
    ey = hub["y"] if above else hub["y"] + hub["h"]
    my = (sy + ey) / 2
    return f"M{cx:.0f},{sy:.0f} C{cx:.0f},{my:.0f} {hx:.0f},{my:.0f} {hx:.0f},{ey:.0f}", (cx, sy), (hx, ey)


def _curve_bus(node, hub, bus_x):
    """En vertical: del canto interior del nodo a un bus central que llega al
    núcleo. Una curva directa cruzaría los nodos de su propia columna."""
    left = node["x"] + node["w"] / 2 < bus_x
    sx = node["x"] + node["w"] if left else node["x"]
    sy = node["y"] + node["h"] / 2
    above = sy < hub["y"]
    ey = hub["y"] if above else hub["y"] + hub["h"]
    turn = min(28, abs(ey - sy) / 2) * (1 if above else -1)
    return (f"M{sx:.0f},{sy:.0f} Q{bus_x:.0f},{sy:.0f} {bus_x:.0f},{sy + turn:.0f} "
            f"L{bus_x:.0f},{ey:.0f}"), (sx, sy), (bus_x, ey)


def _take_side(free, order):
    side = next((s for s in order if free[s] > 0), None)
    if side is None:
        raise SystemExit(f"diagram: demasiadas piezas (máx. {sum(SIDE_CAPACITY.values())} "
                         "más el núcleo)")
    free[side] -= 1
    return side


def _assign_sides(groups):
    """Cada grupo entero al lado menos ocupado donde quepa (a igualdad:
    izquierda, derecha, arriba, abajo); si no cabe en ninguno, se reparte por
    donde quede hueco. Con un solo grupo las piezas se turnan los lados: en una
    columna dejaría el mapa vacío."""
    free = dict(SIDE_CAPACITY)
    sides = {s: [] for s in SIDES}
    for members in groups:
        fits = [s for s in SIDES if free[s] >= len(members)]
        side = min(fits, key=lambda s: len(sides[s])) if fits else None
        if side and len(groups) > 1:
            sides[side] += members
            free[side] -= len(members)
            continue
        for i, node in enumerate(members):
            order = SIDES[i % 4:] + SIDES[:i % 4] if len(groups) == 1 else SIDES
            sides[_take_side(free, order)].append(node)
    return sides


def diagram_layout(spec, width, height, brand):
    """Posición, tamaño, color y curva de cada pieza, en píxeles del fotograma."""
    nodes = [dict(n) if isinstance(n, dict) else {"label": str(n)} for n in spec.get("nodes", [])]
    if len(nodes) < 2:
        raise SystemExit("diagram: hacen falta al menos 2 piezas en 'nodes'")
    hub_i = int(spec.get("hub", 0))
    colors = diagram_colors(nodes, brand)
    for node in nodes:
        node["color"] = node.get("color") or colors[node.get("group", "")]
    others = [n for i, n in enumerate(nodes) if i != hub_i]

    if height > width:
        s = width / 1080
        hub = {"w": width * 0.66, "h": 160 * s}
        hub.update(x=(width - hub["w"]) / 2, y=height * 0.52 - hub["h"] / 2)
        nw, nh, gap, margin = width * 0.425, 140 * s, 34 * s, 44 * s
        col_x = (width * 0.05, width * 0.95 - nw)
        # Arriba deja sitio a la cabecera y abajo a la interfaz de la red.
        room = min(hub["y"] - margin - height * 0.20,
                   height * 0.86 - (hub["y"] + hub["h"] + margin))
        rows = -(-len(others) // 2)
        rows_top = -(-rows // 2)
        pitch = min(nh + gap, (room + gap) / max(rows_top, rows - rows_top))
        nh = pitch - gap
        upper, lower = others[:rows_top * 2], others[rows_top * 2:]
        for k, node in enumerate(upper):
            r, c = divmod(k, 2)
            node.update(x=col_x[c], w=nw, h=nh,
                        y=hub["y"] - margin - (rows_top - r) * pitch + gap)
        for k, node in enumerate(lower):
            r, c = divmod(k, 2)
            node.update(x=col_x[c], w=nw, h=nh, y=hub["y"] + hub["h"] + margin + r * pitch)
        for node in others:
            node["path"], node["a"], node["b"] = _curve_bus(node, hub, width / 2)
        header = {"x": width * 0.06, "y": height * 0.085, "scale": s}
    else:
        s = height / 1080
        hub = {"w": 440 * s, "h": 140 * s}
        hub.update(x=(width - hub["w"]) / 2, y=height * 0.52 - hub["h"] / 2)
        nw, nh = 320 * s, 84 * s
        # Las piezas de un grupo van juntas aunque el plan las intercale.
        groups = {}
        for node in others:
            groups.setdefault(node.get("group", ""), []).append(node)
        groups = list(groups.values())
        cy = hub["y"] + hub["h"] / 2
        for side, members in _assign_sides(groups).items():
            if side in ("left", "right"):
                pitch = 120 * s
                x = 90 * s if side == "left" else width - 90 * s - nw
                y0 = cy - (len(members) * pitch - (pitch - nh)) / 2
                for k, node in enumerate(members):
                    node.update(x=x, y=y0 + k * pitch, w=nw, h=nh)
            else:
                pitch = nw + 30 * s
                y = 240 * s if side == "top" else 860 * s
                x0 = (width - (len(members) * pitch - 30 * s)) / 2
                for k, node in enumerate(members):
                    node.update(x=x0 + k * pitch, y=y, w=nw, h=nh)
        for node in others:
            dx = abs(node["x"] + nw / 2 - width / 2)
            dy = abs(node["y"] + nh / 2 - cy)
            curve = _curve_side if dx > dy * 1.6 else _curve_vertical
            node["path"], node["a"], node["b"] = curve(node, hub)
        header = {"x": 96 * s, "y": 62 * s, "scale": s}

    nodes[hub_i].update(hub)
    nodes[hub_i]["path"] = ""
    active = diagram_active(spec, nodes)
    return {"nodes": nodes, "hub": hub_i, "header": header, "active": active,
            "mode": spec.get("mode") or ("piece" if active >= 0 else "overview")}


def draw_diagram(spec, theme, width, base):
    """La versión fija: el mapa con la pieza activa rellena y las anteriores con
    su color. Sin Node no hay luz ni datos viajando, pero sí la estructura."""
    height = int(spec.get("_height") or width * 9 / 16)
    layout = diagram_layout(spec, width, height, accent())
    image = Image.new("RGBA", (width, height), (8, 10, 18, 240))
    draw = ImageDraw.Draw(image)
    s = layout["header"]["scale"]
    hx, hy = layout["header"]["x"], layout["header"]["y"]
    draw.text((hx, hy), spec.get("heading", ""), font=load_font(int(26 * s), "Bold"),
              fill=hex_rgba(accent()))
    draw.text((hx, hy + 32 * s), spec.get("title", ""), font=load_font(int(58 * s)),
              fill=(244, 246, 251, 255))
    draw.text((hx, hy + 104 * s), spec.get("sub", ""), font=load_mono(int(25 * s)),
              fill=(154, 163, 181, 255))
    active, mode = layout["active"], layout["mode"]
    lit = [mode == "finale" or i == active for i in range(len(layout["nodes"]))]
    for i, node in enumerate(layout["nodes"]):
        if node["path"]:
            draw.line((*node["a"], *node["b"]), width=max(2, round((5 if lit[i] else 2.5) * s)),
                      fill=hex_rgba(node["color"], 255 if lit[i] else 90))
    for i, node in enumerate(layout["nodes"]):
        box = (node["x"], node["y"], node["x"] + node["w"], node["y"] + node["h"])
        draw.rounded_rectangle(box, int(node["h"] / 2 if i == layout["hub"] else 20 * s),
                               fill=hex_rgba(node["color"], 235) if lit[i] else (20, 23, 33, 235),
                               outline=hex_rgba(node["color"], 230 if lit[i] or i < active else 90),
                               width=max(2, round(2 * s)))
        draw.text((node["x"] + node["h"] * 0.35, node["y"] + node["h"] / 2), node.get("label", ""),
                  font=load_font(int(node["h"] * 0.32)), anchor="lm",
                  fill=(11, 13, 20, 255) if lit[i] else (238, 241, 247, 255))
    return image


def diagram_icon(name):
    """El SVG de una pieza: una ruta, o un concepto de stickers/iconos, o un logo
    de images/ (los que deja icons.py)."""
    if not name:
        return None
    candidates = ([name] if name.endswith(".svg")
                  else [f"stickers/iconos/{name}.svg", f"images/{name}.svg"])
    for candidate in candidates:
        path = Path(resolve_asset(candidate))
        if path.exists():
            return path.read_text(encoding="utf-8")
    print(f"  aviso: icono '{name}' no encontrado; la pieza sale sin icono")
    return None


KINDS = {"panel": draw_panel, "bullets": draw_bullets, "flow": draw_flow,
         "title": draw_title, "stat": draw_stat, "chip": draw_chip,
         "compare": draw_compare, "checklist": draw_checklist, "code": draw_code,
         "section": draw_section, "logos": draw_logos, "stamp": draw_stamp,
         "diagram": draw_diagram}


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
    # Mismo color que la animada: el del canal, no el acento del preset.
    theme = build_theme({**platform["card"], "accent": accent()})
    base_size = platform["card"]["base_size"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for index, spec in enumerate(cards):
        kind = spec.get("kind", "panel")
        if kind not in KINDS:
            raise SystemExit(f"card {index}: kind '{kind}' desconocido. Usa: {', '.join(KINDS)}")
        if kind == "diagram":
            # El diagrama ocupa el fotograma entero, no una franja.
            spec = {**spec, "_height": platform["height"]}
        image = KINDS[kind](spec, theme, platform["width"], base_size)
        path = output_dir / f"card{index:02d}.png"
        image.save(path)
        paths.append(path)
        print(f"  {kind:8} {image.width}x{image.height}  {path.name}")
    return paths


REMOTION = ROOT / "remotion"
CARD_HEIGHT = 760   # el lienzo de una card animada; el de Root.tsx por defecto


def remotion_ready():
    """Whether the animated renderer can run: Node on PATH and deps installed."""
    return bool(shutil.which("npx")) and (REMOTION / "node_modules").is_dir()


def three_d_ready():
    """El 3D necesita además @remotion/three, que llegó después que las cards."""
    return (REMOTION / "node_modules" / "@remotion" / "three").is_dir()


def with_diagram(spec, platform):
    """El diagrama viaja ya colocado y con sus iconos dentro."""
    layout = diagram_layout(spec, platform["width"], platform["height"], accent())
    for node in layout["nodes"]:
        node["svg"] = diagram_icon(node.get("icon"))
    return {**spec, "layout": layout}


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
            # Con el SVG que deja icons.py al lado, el logo sale en 3D dentro de
            # su plato. `"3d": false` en la card lo deja plano.
            svg = path.with_suffix(".svg")
            if svg.exists() and spec.get("3d") is not False and three_d_ready():
                item["svg"] = svg.read_text(encoding="utf-8")
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
             "fg": settings["fg"], "accent": settings["accent"],
             # El color del canal, para los números de sección y las estelas.
             "brand": accent()}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for index, spec in enumerate(cards):
        kind = spec.get("kind", "panel")
        if kind not in KINDS:
            raise SystemExit(f"card {index}: kind '{kind}' desconocido. Usa: {', '.join(KINDS)}")
        path = output_dir / f"card{index:02d}.mov"
        props = output_dir / f"card{index:02d}.props.json"
        diagram = kind == "diagram"
        write_json(props, {"kind": kind, "dur": float(spec.get("dur", 4.5 if diagram else 3)),
                           "width": platform["width"], "base": settings["base_size"],
                           # El diagrama ocupa el fotograma; el resto, una franja.
                           "height": platform["height"] if diagram else CARD_HEIGHT,
                           "theme": theme,
                           "spec": with_diagram(spec, platform) if diagram
                                   else with_inline_images(spec)})
        result = subprocess.run(
            [npx, "remotion", "render", "build", "Card",
             str(path.resolve()), f"--props={props.resolve()}", "--log=error",
             # GPU para los logos 3D de la fila de logos; Chrome cae solo a
             # software si no hay.
             "--gl=angle"],
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
