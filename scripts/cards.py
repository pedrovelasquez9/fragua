"""Render annotation cards as transparent PNGs, one per card in plan.json.

    python cards.py plan.json --preset tiktok --outdir cards/

ASS can only put a rectangle behind a line of text, which is why cards drawn
that way look like slide titles. These are real graphics: rounded panels with a
divided header, bullet lists, connected flow diagrams and stat blocks.

Four kinds, chosen per card with "kind":

  panel    título + párrafo, separados por una banda de acento
  bullets  título + lista con viñetas
  flow     nodos conectados, tipo mapa mental
  stat     una cifra grande + su etiqueta
"""
import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import FONTS, ROOT, preset, read_json, write_json

RADIUS = 26
PAD = 34
SHADOW_BLUR = 18


def hex_rgba(value, alpha=255):
    """'#14161F' -> (20, 22, 31, alpha)."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


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


KINDS = {"panel": draw_panel, "bullets": draw_bullets, "flow": draw_flow,
         "title": draw_title,
         "stat": draw_stat, "chip": draw_chip}


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
    font = FONTS / "Roboto-Variable.ttf"
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
                           "theme": theme, "spec": spec})
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
