"""Comprueba copy.json antes de entregarlo: lo que YouTube corta o esconde.

    python copy_check.py copy.json

El copy se escribe a mano y los fallos que cuestan visitas no se ven al leerlo:
un título de 74 caracteres sale cortado en el móvil, un año lo deja viejo en
enero, un hashtag con tilde se trocea en dos y una descripción sin 0:00 se queda
sin capítulos sin que YouTube avise. Y una URL que no dio el autor es una URL
inventada.

Las URLs que sí dio el autor van en `author_links` dentro de copy.json. El nombre
del canal, si está, sale del bloque `channel` de presets.json.
"""
import argparse
import re
import unicodedata

from chapters import MIN_CHAPTERS
from common import load_presets, read_json

MAX_LONG_TITLE = 70
MAX_SHORT_TITLE = 60
MAX_HASHTAGS = 5
MAX_TAGS = 5

YEAR = re.compile(r"\b(19|20)\d\d\b")
HASHTAG = re.compile(r"#\w+")
URL = re.compile(r"https?://[^\s)\]>\"']+")
TIMESTAMP = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s", re.M)
ACCENTED = set("ñÑáéíóúÁÉÍÓÚàèìòùüÜ")


def title_problems(title, limit, channel):
    problems = []
    if len(title) > limit:
        problems.append(f"{len(title)} caracteres, el máximo es {limit}")
    if channel and channel.lower() in title.lower():
        problems.append("lleva el nombre del canal")
    if title and unicodedata.category(title[0]) == "So":
        problems.append("empieza por emoji")
    if "#" in title:
        problems.append("lleva un hashtag")
    if YEAR.search(title):
        problems.append("lleva un año: lo deja viejo en enero")
    return [f"título «{title}»: {p}" for p in problems]


def hashtag_problems(network, text):
    tags = HASHTAG.findall(text or "")
    problems = []
    if len(tags) > MAX_HASHTAGS:
        problems.append(f"{network}: {len(tags)} hashtags, el máximo es {MAX_HASHTAGS}")
    for tag in tags:
        if ACCENTED & set(tag):
            problems.append(f"{network}: {tag} lleva ñ o tilde y se trocea")
    return problems


def chapter_problems(description):
    stamps = TIMESTAMP.findall(description or "")
    if len(stamps) < MIN_CHAPTERS:
        return [f"la descripción del largo no lleva los capítulos "
                f"({len(stamps)} tiempos, YouTube pide {MIN_CHAPTERS})"]
    if stamps[0] != "0:00":
        return [f"los capítulos empiezan en {stamps[0]}, no en 0:00: YouTube no los muestra"]
    return []


def strings(value):
    """Todo el texto de copy.json, para buscar URLs en cualquier campo."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def check(copy, channel=None):
    """Lista de problemas; vacía si el copy se puede entregar."""
    problems = []
    youtube, shorts = copy.get("youtube"), copy.get("shorts")
    if youtube:
        for title in youtube.get("titles", []):
            problems += title_problems(title, MAX_LONG_TITLE, channel)
        problems += chapter_problems(youtube.get("description", ""))
        problems += hashtag_problems("youtube", youtube.get("description", ""))
        if len(youtube.get("tags", [])) > MAX_TAGS:
            problems.append(f"youtube: {len(youtube['tags'])} tags, el máximo es {MAX_TAGS}")
    if shorts:
        problems += title_problems(shorts.get("title", ""), MAX_SHORT_TITLE, channel)
        problems += hashtag_problems("shorts", shorts.get("description", ""))
    for network in ("instagram", "tiktok"):
        problems += hashtag_problems(network, copy.get(network, ""))

    allowed = {link.rstrip("/.,") for link in copy.get("author_links", [])}
    extra = copy.copy()
    extra.pop("author_links", None)
    for text in strings(extra):
        for url in URL.findall(text):
            if url.rstrip("/.,") not in allowed:
                problems.append(f"{url} no viene del autor: quítala o pon [ENLACE: qué es]")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("copy")
    args = parser.parse_args()
    channel = load_presets().get("channel", {}).get("name")
    problems = check(read_json(args.copy), channel)
    if problems:
        raise SystemExit("copy.json no está listo:\n  " + "\n  ".join(problems))
    print("copy.json listo")


if __name__ == "__main__":
    main()
