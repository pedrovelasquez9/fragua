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
CACHE_VERSION = 2

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
    """Para cruzar con el texto: quita todo lo que no es letra o número."""
    return re.sub(r"[^a-z0-9]", "", texto.lower())


# El nombre del fichero en Simple Icons no es el título sin símbolos: cambia cada
# símbolo por su nombre. Con la versión ingenua «C++» y «C» caían los dos en `c`
# —el segundo pisaba al primero— y «.NET» buscaba `net`.
SIMBOLOS = {"+": "plus", ".": "dot", "&": "and", "đ": "d", "ħ": "h", "ı": "i",
            "ĸ": "k", "ŀ": "l", "ł": "l", "ß": "ss", "ŧ": "t", "ø": "o"}


def slug_oficial(titulo):
    """El nombre que usa Simple Icons para el fichero de cada marca."""
    import unicodedata

    texto = "".join(SIMBOLOS.get(c, c) for c in titulo.lower())
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto)


def catalogo(refrescar=False):
    """El índice de Simple Icons, cacheado junto a la config de la biblioteca."""
    if CACHE.exists() and not refrescar:
        guardado = json.loads(CACHE.read_text(encoding="utf-8"))
        # Una caché de antes de 1.23 tiene los nombres mal hechos (C++ pisaba a
        # C): se rehace en vez de seguir sirviendo la tabla equivocada.
        if guardado.get("_version") == CACHE_VERSION:
            return guardado
    print("descargando el índice de Simple Icons…")
    with urllib.request.urlopen(INDICE, timeout=60) as respuesta:
        crudo = json.loads(respuesta.read().decode("utf-8"))
    iconos = crudo["icons"] if isinstance(crudo, dict) else crudo
    tabla = {}
    for icono in iconos:
        destino = {"slug": icono.get("slug") or slug_oficial(icono["title"]),
                   "hex": icono.get("hex", "FFFFFF"), "title": icono["title"]}
        # El nombre oficial manda y nunca se pisa; el ingenuo y los alias sólo
        # rellenan huecos, para que «nodejs» encuentre Node.js sin que «C++»
        # se quede con el sitio de «C».
        tabla[destino["slug"]] = destino
        tabla.setdefault(slugify(icono["title"]), destino)
        for alias in (icono.get("aliases") or {}).get("aka", []):
            tabla.setdefault(slugify(alias), destino)
    tabla["_version"] = CACHE_VERSION
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


def clave(palabra, tabla):
    """Qué entrada de la tabla es esta palabra: primero su nombre oficial.

    «c++» simplificada a lo bruto es «c», que es otra marca. Por su nombre
    oficial es «cplusplus», que es la buena.
    """
    for candidata in (slug_oficial(palabra), slugify(palabra)):
        if candidata in tabla:
            return candidata
    return slugify(palabra)


def palabras_del_texto(ruta, tabla):
    """Los nombres de la tabla que aparecen en el texto, sin repetir."""
    texto = Path(ruta).read_text(encoding="utf-8")
    vistas, salida = set(), []
    for bruto in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9.+#-]{3,}", texto):
        limpio = bruto.strip(".,").lower()
        encontrada = clave(limpio, tabla)
        if (len(slugify(limpio)) >= MINIMO and encontrada not in RUIDO
                and encontrada in tabla and encontrada not in vistas):
            vistas.add(encontrada)
            salida.append((limpio, encontrada))
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
        encontrados = [(w.lower(), clave(w, tabla)) for w in args.words]

    destino = Path(args.outdir) if args.outdir else assets_dir() / "images"
    destino.mkdir(parents=True, exist_ok=True)

    hechos, fallos = 0, []
    for palabra, nombre in encontrados:
        icono = tabla.get(nombre)
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
