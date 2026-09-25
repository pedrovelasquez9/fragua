"""Convierte los stickers Lottie del plan en clips con transparencia.

    python lottie.py plan.json --preset tiktok

Un sticker cuyo `file` es un `.json` es una animación Lottie. render.py no puede
leerla —ffmpeg no sabe qué es—, así que antes de renderizar se pasa por Remotion
a un `.mov` ProRes 4444 con alfa, a su tamaño y duración exactos, y se deja en
`lottie/` junto al plan. render.py lo busca ahí, igual que las cards en `cards/`.

Necesita las dependencias de `remotion/`, como las cards animadas.

Las animaciones gratuitas de LottieFiles van bajo la Lottie Simple License: uso
comercial permitido, sin atribución. Lo que NO permite es recopilarlas para
montar un servicio parecido, así que este plugin no trae ninguna dentro: cada
usuario baja las suyas a su carpeta de assets, como la música.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, preset, read_json, resolve_asset, write_json  # noqa: E402

REMOTION = ROOT / "remotion"
CARPETA = "lottie"


def es_lottie(sticker):
    return str(sticker.get("file", "")).lower().endswith(".json")


def clip_de(plan_path, index):
    """Dónde vive el .mov de la Lottie `index` del plan. Es el contrato con render.py."""
    return Path(plan_path).resolve().parent / CARPETA / f"lottie{index:02d}.mov"


def medida(datos, ancho):
    """Alto que corresponde a `ancho` según la proporción del propio fichero."""
    w, h = float(datos.get("w") or 1), float(datos.get("h") or 1)
    alto = round(ancho * h / w)
    return ancho // 2 * 2, max(2, alto // 2 * 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("--preset", default="tiktok")
    args = parser.parse_args()

    stickers = read_json(args.plan).get("stickers", [])
    lotties = [(i, s) for i, s in enumerate(stickers) if es_lottie(s)]
    if not lotties:
        print("el plan no tiene stickers Lottie")
        return

    npx = shutil.which("npx")
    if not npx or not (REMOTION / "node_modules" / "@remotion" / "lottie").exists():
        sys.exit("las Lottie necesitan Node y las dependencias de remotion/:\n"
                 "ejecuta /fragua:setup, o  npm install  dentro de remotion/")

    ancho_video = preset(args.preset)["width"]
    salida = Path(args.plan).resolve().parent / CARPETA
    salida.mkdir(parents=True, exist_ok=True)

    bundled = subprocess.run([npx, "remotion", "bundle", "--log=error"], cwd=REMOTION,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    if bundled.returncode != 0:
        sys.exit(f"remotion bundle falló:\n{(bundled.stderr or bundled.stdout)[-2000:]}")

    for index, sticker in lotties:
        fuente = resolve_asset(sticker["file"])
        datos = json.loads(Path(fuente).read_text(encoding="utf-8"))
        ancho, alto = medida(datos, int(ancho_video * float(sticker.get("scale", 0.2))))
        dur = float(sticker.get("dur", 2))
        props = salida / f"lottie{index:02d}.props.json"
        write_json(props, {"animationData": datos, "dur": dur, "width": ancho,
                           "height": alto, "loop": bool(sticker.get("loop", True)),
                           "playbackRate": float(sticker.get("speed", 1.0))})
        clip = clip_de(args.plan, index)
        hecho = subprocess.run(
            # Codec, alfa y formato de fotograma los fija remotion.config.ts, el
            # mismo que usan las cards: una sola fuente de verdad para el alfa.
            [npx, "remotion", "render", "build", "LottieClip", str(clip.resolve()),
             f"--props={props.resolve()}", "--log=error"],
            cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if hecho.returncode != 0:
            sys.exit(f"Lottie {index} ({Path(fuente).name}) falló en remotion:\n"
                     f"{(hecho.stderr or hecho.stdout)[-2000:]}")
        props.unlink(missing_ok=True)
        print(f"  {Path(fuente).name:28} {ancho}x{alto}  {dur:.1f}s -> {clip.name}")

    print(f"{len(lotties)} Lottie -> {salida}")


if __name__ == "__main__":
    main()
