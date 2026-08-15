"""Configure and index the asset library the edit pulls from.

    python assets.py --set D:/mis-assets     apunta a tu carpeta
    python assets.py                          reindexa y muestra qué hay
    python assets.py --show                   sólo dice dónde está apuntando

Escribe `~/.fragua/assets.json`: el catálogo que el agente lee para saber qué
música, efectos, imágenes y fuentes tiene disponibles antes de escribir
`plan.json`. Sin catálogo, el agente no sabe que existen.

Vive fuera de la skill a propósito. Claude Code instala cada versión del plugin
en su propia carpeta, así que guardarlo dentro haría perder la configuración en
cada actualización.

Estructura recomendada de la carpeta, aunque también funciona plana porque la
clasificación es por extensión:

    music/     pistas largas de fondo
    sfx/       golpes cortos: whoosh, pop, riser
    stickers/  PNG con transparencia
    images/    capturas, logos, fondos
    fonts/     .ttf/.otf propios
"""
import argparse
import struct
import subprocess
from pathlib import Path

from common import ASSETS_CONFIG, ROOT, read_json, write_json

CONFIG = ASSETS_CONFIG
DEFAULT_DIR = ROOT / "assets"

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
FONT_EXT = {".ttf", ".otf", ".ttc"}

# Un audio por debajo de esto es un efecto puntual; por encima, música de fondo.
SFX_MAX_SECONDS = 6.0


def probe_seconds(path):
    """Duration via ffprobe, or None if it is not readable as media."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30)
        return round(float(result.stdout.strip()), 2)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def image_info(path):
    """(width, height, has_alpha) without keeping the file open."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
            return image.width, image.height, alpha
    except Exception:
        return None, None, False


def font_family(path):
    """Family name from the font's name table — that is what libass matches on."""
    try:
        data = Path(path).read_bytes()
        table_count = struct.unpack(">H", data[4:6])[0]
        for index in range(table_count):
            offset = 12 + 16 * index
            if data[offset:offset + 4] != b"name":
                continue
            table = struct.unpack(">I", data[offset + 8:offset + 12])[0]
            count, storage = struct.unpack(">HH", data[table + 2:table + 6])
            for record in range(count):
                base = table + 6 + 12 * record
                platform, _, _, name_id, length, string_offset = struct.unpack(
                    ">HHHHHH", data[base:base + 12])
                if name_id == 1 and platform == 3:
                    start = table + storage + string_offset
                    return data[start:start + length].decode("utf-16-be")
    except Exception:
        pass
    return None


# Nadie dice «el logo de youtube» al hablar, dice «youtube». Los archivos, en
# cambio, se descargan llamándose youtube_logo.png, así que la palabra que
# dispararía la imagen no se pronuncia nunca.
GENERIC_WORDS = {"logo", "logotipo", "icon", "icono", "img", "image", "imagen"}


def keyword_from(path):
    """Palabra que dispara la imagen, sacada del nombre del archivo.

    `youtube.png` -> "youtube".  `claude-code.png` -> "claude code".
    `Youtube_logo.png` -> "youtube".
    Así el agente puede buscarla en la transcripción sin más configuración.
    """
    stem = path.stem.lower().strip()
    for separator in ("-", "_"):
        stem = stem.replace(separator, " ")
    words = [w for w in stem.split() if w not in GENERIC_WORDS]
    # Si sólo se llamaba "logo.png" no queda nada; mejor la palabra mala que ninguna.
    return " ".join(words or stem.split())


def classify(path, root):
    """Bucket a file, using its folder as a hint and its content as the tiebreak."""
    suffix = path.suffix.lower()
    folder = path.relative_to(root).parts[0].lower() if path.parent != root else ""

    if suffix in AUDIO_EXT:
        seconds = probe_seconds(path)
        if folder in ("sfx", "efectos"):
            kind = "sfx"
        elif folder in ("music", "musica", "música"):
            kind = "music"
        else:
            kind = "sfx" if seconds is not None and seconds <= SFX_MAX_SECONDS else "music"
        return kind, {"seconds": seconds}

    if suffix in IMAGE_EXT:
        width, height, alpha = image_info(path)
        # A sticker is an overlay: it needs transparency to sit over the video.
        kind = "stickers" if alpha else "images"
        if folder in ("stickers", "images", "imagenes", "imágenes"):
            kind = "stickers" if folder.startswith("sticker") else "images"
        # El nombre del archivo es la palabra a buscar en la transcripción:
        # youtube.png se muestra cuando el vídeo dice "youtube".
        return kind, {"width": width, "height": height, "alpha": alpha,
                      "keyword": keyword_from(path)}

    if suffix in FONT_EXT:
        return "fonts", {"family": font_family(path)}

    return None, {}


def index_directory(root):
    """Walk the library and describe everything usable in it."""
    catalogue = {"music": [], "sfx": [], "stickers": [], "images": [], "fonts": []}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        kind, meta = classify(path, root)
        if kind:
            catalogue[kind].append(dict(file=path.relative_to(root).as_posix(), **meta))
    return catalogue


def load_config():
    return read_json(CONFIG) if CONFIG.exists() else {}


def assets_root():
    """Configured library, or the bundled assets/ folder if none is set."""
    configured = load_config().get("dir")
    return Path(configured) if configured else DEFAULT_DIR


def summarise(catalogue, root):
    total = sum(len(v) for v in catalogue.values())
    print(f"{root}")
    if not total:
        print("  vacío — mete música, sfx, stickers, imágenes o fuentes y reindexa")
        return
    for kind, entries in catalogue.items():
        if not entries:
            continue
        print(f"  {kind:9} {len(entries)}")
        for entry in entries[:4]:
            detail = ""
            if "seconds" in entry and entry["seconds"]:
                detail = f"{entry['seconds']}s"
            elif entry.get("width"):
                detail = f"{entry['width']}x{entry['height']}"
                detail += " con alpha" if entry.get("alpha") else ""
                if entry.get("keyword"):
                    detail += f"  · palabra: «{entry['keyword']}»"
            elif entry.get("family"):
                detail = entry["family"]
            print(f"      {entry['file']:<44} {detail}")
        if len(entries) > 4:
            print(f"      … y {len(entries) - 4} más")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="new_dir", default=None,
                        help="carpeta de assets a usar a partir de ahora")
    parser.add_argument("--show", action="store_true", help="sólo mostrar la ruta configurada")
    parser.add_argument("--auto", action="store_true",
                        help="reindexado previo a una edición: no falla si aún no hay biblioteca")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    if args.new_dir:
        root = Path(args.new_dir).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"no existe la carpeta: {root}")
        config["dir"] = root.as_posix()

    root = Path(config.get("dir", DEFAULT_DIR))
    if args.show:
        print(root)
        return

    if not root.is_dir():
        # En modo automático esto no es un error: simplemente aún no hay
        # biblioteca, y la edición debe continuar sin música ni imágenes.
        if args.auto:
            print(f"sin biblioteca de assets ({root}); la edición sigue sin ella")
            return
        raise SystemExit(f"no existe la carpeta de assets: {root}\n"
                         f"Configúrala con:  python scripts/assets.py --set <ruta>")

    # ponytail: indexado completo cada vez. Son ~0.8 s con 50 archivos, así que
    # no compensa una caché por mtime mientras la biblioteca no crezca mucho.
    catalogue = index_directory(root)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    write_json(CONFIG, dict(config, dir=root.as_posix(), **catalogue))
    summarise(catalogue, root)
    print(f"\ncatálogo -> {CONFIG.name}")


if __name__ == "__main__":
    main()
