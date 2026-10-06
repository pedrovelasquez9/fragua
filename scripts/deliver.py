"""Carpeta de trabajo al empezar, entrega limpia al terminar.

    python deliver.py start entrada.mp4          → imprime la carpeta de trabajo
    python deliver.py finish entrada-EDIT.mp4 --work CARPETA

Una edición genera decenas de archivos intermedios —cortes, transcripción,
plan, cards, clips de movimiento— que al usuario no le sirven de nada. Viven en
una carpeta del temporal del sistema, nunca junto a sus vídeos, y `finish` deja
junto al vídeo montado sólo lo que se publica y borra el resto:

    entrada-EDIT.mp4          el vídeo
    entrada-EDIT.srt          los subtítulos
    entrada-EDIT-copy.txt     el copy para cada red
    entrada-EDIT-portada.jpg  la portada (vídeo vertical)

En la carpeta de trabajo `finish` espera `subs.srt`, `copy.json` —que tiene que
pasar copy_check.py— y, si el vídeo es vertical, `portada.jpg` (cover.py).
"""
import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

from common import channel, probe_stream, read_json
from copy_check import check

WORK_ROOT = Path(tempfile.gettempdir()) / "fragua"


def start(video):
    """La carpeta de trabajo de este vídeo, vacía y fuera de la carpeta del usuario."""
    stem = re.sub(r"[^\w.-]+", "-", Path(video).stem).strip("-") or "video"
    work = WORK_ROOT / stem
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    return work


def render_copy(copy):
    """copy.json como texto para pegar en cada red."""
    out = []
    youtube = copy.get("youtube")
    if youtube:
        out.append("YOUTUBE (largo)")
        out.append("Títulos:")
        out += [f"  {i}) {t}  ({len(t)})" for i, t in enumerate(youtube.get("titles", []), 1)]
        out += ["", "Descripción:", youtube.get("description", "").strip()]
        if youtube.get("tags"):
            out += ["", "Tags: " + ", ".join(youtube["tags"])]
        out.append("")
    shorts = copy.get("shorts")
    if shorts:
        title = shorts.get("title", "")
        out += ["YOUTUBE SHORTS", f"Título: {title}  ({len(title)})"]
        if shorts.get("related"):
            out.append(f"Vídeo relacionado: {shorts['related']}")
        out += ["Descripción:", shorts.get("description", "").strip(), ""]
    for network in ("instagram", "tiktok"):
        if copy.get(network):
            out += [network.upper(), copy[network].strip(), ""]
    if copy.get("thumbnails"):
        out.append("MINIATURAS")
        out += [f"{i}) {t.strip()}\n" for i, t in enumerate(copy["thumbnails"], 1)]
    return "\n".join(out).rstrip() + "\n"


def finish(video, work):
    video, work = Path(video), Path(work).resolve()
    # Se borra una carpeta entera: sólo si es una de las que creó `start`.
    if WORK_ROOT.resolve() not in work.parents:
        sys.exit(f"{work} no es una carpeta de trabajo de fragua ({WORK_ROOT}): no la borro")
    if not video.exists():
        sys.exit(f"no existe {video}: renderiza antes de entregar")

    width, height, _ = probe_stream(video)
    needed = ["subs.srt", "copy.json"] + (["portada.jpg"] if height > width else [])
    missing = [name for name in needed if not (work / name).exists()]
    if missing:
        sys.exit(f"faltan en {work}: {', '.join(missing)}. Nada se ha borrado.")

    copy = read_json(work / "copy.json")
    problems = check(copy, channel().get("name"))
    if problems:
        sys.exit("copy.json no está listo:\n  " + "\n  ".join(problems))

    base = video.with_suffix("")
    delivered = [video]
    for source, target in (("subs.srt", f"{base}.srt"),
                           ("portada.jpg", f"{base}-portada.jpg")):
        if (work / source).exists():
            shutil.copyfile(work / source, target)
            delivered.append(Path(target))
    copy_txt = Path(f"{base}-copy.txt")
    copy_txt.write_text(render_copy(copy), encoding="utf-8")
    delivered.append(copy_txt)

    shutil.rmtree(work)
    return delivered


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start").add_argument("video")
    done = sub.add_parser("finish")
    done.add_argument("video", help="el vídeo montado")
    done.add_argument("--work", required=True)
    args = parser.parse_args()

    if args.command == "start":
        print(start(args.video))
        return
    for path in finish(args.video, args.work):
        print(path)


if __name__ == "__main__":
    main()
