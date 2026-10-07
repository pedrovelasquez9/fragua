"""Elementos 3D (three.js dentro de Remotion): logos extruidos y fondo con profundidad.

Lo usan render.py (stickers de logo y el fondo del pullback) y cover.py (el
logo de la portada). Necesita Node y las dependencias de remotion/, como las
cards animadas; sin ellas todo cae a lo de antes —logo plano, fondo negro— y se
dice una vez, sin abortar: el 3D es un acabado, no un requisito.

Un logo es 3D cuando junto a su PNG hay un .svg con el mismo nombre, que es lo
que deja icons.py. Remotion no ve el disco, así que el SVG va como texto en las
props.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from common import ROOT, accent, write_json

REMOTION = ROOT / "remotion"
_bundled = False
_warned = False


def available():
    """¿Se puede renderizar 3D aquí? Node y @remotion/three instalados."""
    return bool(shutil.which("npx")) and (REMOTION / "node_modules" / "@remotion" / "three").is_dir()


def warn_once(what):
    global _warned
    if not _warned:
        print(f"aviso: {what} sale en plano: el 3D necesita las dependencias de remotion/ "
              f"(npm install dentro de remotion/, o /fragua:setup)", file=sys.stderr)
        _warned = True


def svg_for(path):
    """El SVG que acompaña a un logo PNG, o None si es una imagen normal."""
    svg = Path(path).with_suffix(".svg")
    return svg if svg.exists() else None


def _npx(*args):
    result = subprocess.run([shutil.which("npx"), "remotion", *args, "--log=error"],
                            cwd=REMOTION, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        sys.exit(f"remotion {args[0]} falló:\n{(result.stderr or result.stdout)[-2000:]}")


def _bundle():
    global _bundled
    if not _bundled:
        _npx("bundle")
        _bundled = True


def _render(command, composition, props, out, *extra):
    """`remotion render|still` con las props en un JSON al lado, que luego se borra."""
    _bundle()
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    props_file = out.with_suffix(".props.json")
    write_json(props_file, props)
    try:
        # angle usa la GPU; sin ella Chrome cae solo a software, más lento.
        _npx(command, "build", composition, str(out), f"--props={props_file}",
             "--gl=angle", *extra)
    finally:
        props_file.unlink(missing_ok=True)
    return out


def logo_clip(svg_path, size, dur, fps, out):
    """El logo girando en 3D, sin crecer: la entrada y la salida las pone motion.py."""
    size = max(2, int(size) // 2 * 2)
    svg = Path(svg_path).read_text(encoding="utf-8")
    return _render("render", "Logo3D",
                   {"svg": svg, "dur": dur, "size": size, "fps": fps, "pop": False}, out)


def logo_still(svg_path, size, out):
    """Un fotograma del logo 3D ya asentado, en PNG con alfa, para la portada."""
    size = max(2, int(size) // 2 * 2)
    svg = Path(svg_path).read_text(encoding="utf-8")
    # En el fotograma 36 (1.2 s) el giro de entrada ha terminado y queda el leve
    # escorzo del vaivén, que es lo que lo hace leerse como 3D en una foto.
    return _render("still", "Logo3D",
                   {"svg": svg, "dur": 2, "size": size, "fps": 30, "pop": False},
                   out, "--frame=36", "--image-format=png")


def backdrop_clip(width, height, dur, fps, out):
    """El fondo de luces desenfocadas para la banda de un pullback."""
    return _render("render", "Backdrop",
                   {"dur": dur, "width": width, "height": height, "fps": fps,
                    "accent": accent()}, out)
