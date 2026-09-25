"""Llena la biblioteca de iconos con lo que de verdad se dice en el vídeo.

    python icons.py --from digest.txt              # los que menciona el vídeo
    python icons.py --words docker postgres redis  # los que le pidas
    python icons.py --from digest.txt --color brand

Los saca de Simple Icons (3.300 logos de marca, CC0) y los deja en la carpeta de
imágenes de tu biblioteca con el nombre de la palabra. Ahí ya funciona el disparo
por palabra clave que existía: `docker.png` aparece cuando dices «docker», sin
configurar nada más.

Rasterizar SVG necesita `skia-python` (`pip install skia-python`), que no viene
por defecto. Es una rueda de pip, sin librerías nativas que buscar.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ASSETS_CONFIG, assets_dir  # noqa: E402

INDICE = "https://cdn.jsdelivr.net/npm/simple-icons@latest/_data/simple-icons.json"
ICONO = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
CACHE = ASSETS_CONFIG.parent / "simple-icons.json"

TAMANO = 512
PLATE_PAD = 0.22          # margen del plato alrededor del icono
PLATE_RADIO = 0.16        # esquinas, en fracción del lado
PLATE_COLOR = (14, 14, 20, 214)
CONTRASTE_MIN = 2.6       # WCAG contra el plato; por debajo el icono se pierde

# Palabras que no son marcas aunque se escriban igual que un slug. Sin esto,
# «go», «swift» o «arc» salen disparadas en cualquier frase.
RUIDO = {"go", "arc", "swift", "rust", "dart", "processing", "element", "gnu",
         "ruby", "expo", "hey", "lens", "max", "monica", "nano", "odin", "pop",
         "quest", "roots", "sky", "spark", "toml", "wire", "zap"}
MINIMO = 4                # longitud mínima de palabra para buscarla


def slugify(texto):
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def catalogo(refrescar=False):
    """El índice de Simple Icons, cacheado junto a la config de la biblioteca."""
    if CACHE.exists() and not refrescar:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    print("descargando el índice de Simple Icons…")
    with urllib.request.urlopen(INDICE, timeout=60) as respuesta:
        crudo = json.loads(respuesta.read().decode("utf-8"))
    iconos = crudo["icons"] if isinstance(crudo, dict) else crudo
    tabla = {}
    for icono in iconos:
        destino = {"slug": slugify(icono["title"]), "hex": icono.get("hex", "FFFFFF"),
                   "title": icono["title"]}
        tabla[destino["slug"]] = destino
        for alias in (icono.get("aliases") or {}).get("aka", []):
            tabla.setdefault(slugify(alias), destino)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(tabla, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(tabla)} nombres -> {CACHE}")
    return tabla


def _luminancia(rgb):
    """Luminancia relativa WCAG, para poder medir contraste de verdad."""
    canales = []
    for valor in rgb:
        v = valor / 255
        canales.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def _contraste(uno, otro):
    a, b = _luminancia(uno), _luminancia(otro)
    claro, oscuro = max(a, b), min(a, b)
    return (claro + 0.05) / (oscuro + 0.05)


def legible(hexa):
    """Aclara el color de marca hasta que se vea sobre el plato.

    Medido: GitHub es #181717 y sobre el plato da un contraste de 1.10 — el icono
    desaparece del todo. Se sube la luminosidad en HLS en vez de saltar a blanco,
    para no perder la marca en los que sólo van justos.
    """
    import colorsys

    rgb = tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
    # Una marca monocroma oscura —GitHub, Apple— no se arregla subiéndole la
    # luminosidad: sale un gris sucio. Va en blanco, que es lo que hacen sus
    # propias guías de marca sobre fondo oscuro.
    if s < 0.15 and l < 0.35:
        return "#FFFFFF"
    while _contraste(rgb, PLATE_COLOR[:3]) < CONTRASTE_MIN and l < 0.96:
        l = min(0.96, l + 0.05)
        rgb = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
    return "#%02X%02X%02X" % rgb


def pinta(svg, color):
    """Simple Icons no trae fill y Lucide usa currentColor: los dos se resuelven."""
    svg = svg.replace("currentColor", color)
    if "fill=" not in svg.split(">", 1)[0]:
        svg = svg.replace("<svg", f'<svg fill="{color}"', 1)
    return svg


def rasteriza(svg, lado, plato):
    """SVG -> PNG RGBA. El plato oscuro detrás es lo que lo hace legible.

    Un icono blanco sobre una grabación de pantalla clara desaparece, y sobre un
    plano oscuro un icono de marca oscuro también. El plato resuelve los dos
    casos y además hace que el elemento parezca puesto a propósito.
    """
    try:
        import skia
    except ImportError:
        sys.exit("rasterizar SVG necesita skia-python:  pip install skia-python")
    from PIL import Image, ImageDraw

    dentro = round(lado * (1 - 2 * PLATE_PAD)) if plato else lado
    flujo = skia.MemoryStream.MakeCopy(svg.encode("utf-8"))
    dom = skia.SVGDOM.MakeFromStream(flujo)
    if dom is None:
        return None
    dom.setContainerSize(skia.Size(dentro, dentro))
    superficie = skia.Surface(dentro, dentro)
    with superficie as lienzo:
        dom.render(lienzo)
    datos = superficie.makeImageSnapshot().encodeToData()
    from io import BytesIO
    arte = Image.open(BytesIO(bytes(datos))).convert("RGBA")
    if not plato:
        return arte

    fondo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(fondo).rounded_rectangle(
        [0, 0, lado - 1, lado - 1], radius=round(lado * PLATE_RADIO), fill=PLATE_COLOR)
    fondo.alpha_composite(arte, ((lado - dentro) // 2, (lado - dentro) // 2))
    return fondo


def palabras_del_texto(ruta, tabla):
    """Los nombres de la tabla que aparecen en el texto, sin repetir."""
    texto = Path(ruta).read_text(encoding="utf-8")
    vistas, salida = set(), []
    for bruto in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9.+#-]{3,}", texto):
        clave = slugify(bruto)
        if (len(clave) >= MINIMO and clave not in RUIDO
                and clave in tabla and clave not in vistas):
            vistas.add(clave)
            salida.append((bruto.strip(".,").lower(), clave))
    return salida


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--from", dest="texto", help="digest.txt: busca en lo que se dice")
    origen.add_argument("--words", nargs="+", help="nombres sueltos")
    parser.add_argument("--color", default="white",
                        help="'white', 'brand' o un #RRGGBB (por defecto: white)")
    parser.add_argument("--size", type=int, default=TAMANO)
    parser.add_argument("--no-plate", action="store_true",
                        help="sin el plato oscuro detrás del icono")
    parser.add_argument("--outdir", default=None,
                        help="por defecto, images/ de tu biblioteca")
    parser.add_argument("--refresh", action="store_true", help="rebaja el índice")
    return parser.parse_args()


def main():
    args = parse_args()
    tabla = catalogo(args.refresh)

    if args.texto:
        encontrados = palabras_del_texto(args.texto, tabla)
    else:
        encontrados = [(w.lower(), slugify(w)) for w in args.words]

    destino = Path(args.outdir) if args.outdir else assets_dir() / "images"
    destino.mkdir(parents=True, exist_ok=True)

    hechos, fallos = 0, []
    for palabra, clave in encontrados:
        icono = tabla.get(clave)
        if not icono:
            fallos.append(palabra)
            continue
        color = legible(icono["hex"]) if args.color == "brand" else args.color
        try:
            with urllib.request.urlopen(ICONO.format(slug=icono["slug"]), timeout=60) as r:
                svg = r.read().decode("utf-8")
        except Exception as fallo:                       # noqa: BLE001
            fallos.append(f"{palabra} ({fallo})")
            continue
        imagen = rasteriza(pinta(svg, color), args.size, not args.no_plate)
        if imagen is None:
            fallos.append(f"{palabra} (SVG ilegible)")
            continue
        salida = destino / f"{palabra}.png"
        imagen.save(salida)
        hechos += 1
        print(f"  {icono['title']:22} -> {salida.name}")

    print(f"{hechos} iconos en {destino}")
    if fallos:
        print("sin icono: " + ", ".join(fallos))
    if hechos:
        print("Simple Icons es CC0. Los logos siguen siendo marcas de sus dueños: "
              "úsalos para referirte al producto, no como si fuesen tuyos.")


if __name__ == "__main__":
    main()
