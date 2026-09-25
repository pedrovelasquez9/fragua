"""El movimiento de los elementos: entran con rebote, viven en pantalla y se van rápido.

Curvas medidas fotograma a fotograma en un showreel de motion graphics de
referencia (15 s, 30 fps), que es lo que se quería igualar:

- **Entrada**: el elemento llega a su pico en ~0.25 s (7-8 fotogramas), se pasa
  un ~8 % y se asienta en otros ~0.15 s. Nada entra con un fundido.
- **En pantalla**: sólo el 7 % de los fotogramas del vídeo están quietos. Lo que
  ya ha llegado sigue respirando o girando un poco; congelado se lee como una
  imagen pegada encima.
- **Salida**: se recoge en ~5 fotogramas (47 → 45 → 37 → 24 → 10 → 0 px de
  ancho). Un fundido lento al salir se lee como un vídeo que se ha colgado.

Las mismas constantes están en `remotion/src/Card.tsx` para las cards
animadas; una prueba comprueba que no se separan.
"""
import math
import subprocess
from pathlib import Path

# Resorte de la entrada. Con estos valores el pico cae a 0.25 s y se pasa un 8 %:
# amortiguamiento 0.63, que es lo que da un rebote que se nota sin temblar.
POP_STIFFNESS = 262.0
POP_DAMPING = 20.4
POP_MASS = 1.0

EXIT = 0.17            # s: la salida se recoge en 5 fotogramas
IDLE_PERIOD = 2.4      # s: una respiración completa
IDLE_SCALE = 0.025     # ±2.5 % de tamaño mientras está en pantalla
IDLE_TURN = 1.5        # ± grados de giro
FADE_IN = 0.08         # s: sólo para que el primer fotograma, diminuto, no parpadee
HEADROOM = 1.22        # lienzo del clip: rebote + respiración + giro sin recortar


def spring(t, stiffness=POP_STIFFNESS, damping=POP_DAMPING, mass=POP_MASS):
    """Posición de 0 a 1 de un resorte amortiguado, a los `t` segundos.

    La misma física que `spring()` de Remotion, para que un sticker de ffmpeg y
    una card de React entren igual.
    """
    if t <= 0:
        return 0.0
    w0 = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))
    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * w0 * t) * (math.cos(wd * t) + zeta * w0 / wd * math.sin(wd * t))
    return 1 - math.exp(-w0 * t) * (1 + w0 * t)


def exit_scale(remaining):
    """1 hasta los últimos EXIT segundos, y de ahí a 0 acelerando."""
    if remaining >= EXIT:
        return 1.0
    u = 1 - max(0.0, remaining) / EXIT
    return 1 - u * u


def pose(t, dur, animate=True):
    """(escala, giro en grados, opacidad) de un elemento en el instante `t`."""
    if not animate:
        # Quieto, pero sin aparecer ni desaparecer de golpe.
        fade = min(1.0, t / 0.2, max(0.0, dur - t) / 0.2)
        return 1.0, 0.0, fade
    enter = spring(t)
    phase = 2 * math.pi * t / IDLE_PERIOD
    breath = 1 + IDLE_SCALE * math.sin(phase)
    # El giro entra con el elemento: girar algo que aún no ha llegado se ve raro.
    turn = IDLE_TURN * math.sin(phase * 0.5) * min(1.0, enter)
    return enter * breath * exit_scale(dur - t), turn, min(1.0, t / FADE_IN)


def _even(value):
    return max(2, int(math.ceil(value / 2)) * 2)


def sticker_clip(src, width, dur, fps, out_path, animate=True):
    """El sticker animado, ya compuesto, en un clip con alfa.

    Devuelve (ancho, alto, dx, dy): el tamaño del clip y cuánto hay que mover su
    esquina para que el sticker quede donde el plan dice. Se dibuja con Pillow
    porque ffmpeg no sabe escalar por debajo de 1 con zoompan ni variar el tamaño
    de un overlay fotograma a fotograma; aquí la curva es exactamente la medida.
    """
    from PIL import Image

    art = Image.open(src).convert("RGBA")
    height = max(1, round(art.height * width / art.width))
    base = art.resize((round(width * HEADROOM), round(height * HEADROOM)), Image.LANCZOS)
    cw, ch = _even(width * HEADROOM * 1.05), _even(height * HEADROOM * 1.05)
    frames = max(1, round(dur * fps))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{cw}x{ch}", "-r", f"{fps:g}", "-i", "-",
         "-c:v", "png", "-pix_fmt", "rgba", str(out_path)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    empty = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for index in range(frames):
        scale, turn, opacity = pose(index / fps, dur, animate)
        frame = empty.copy()
        w, h = round(width * scale), round(height * scale)
        if w >= 2 and h >= 2 and opacity > 0:
            piece = base.resize((w, h), Image.BICUBIC)
            if turn:
                piece = piece.rotate(turn, resample=Image.BICUBIC, expand=True)
            if opacity < 1:
                alpha = piece.getchannel("A").point(lambda a: round(a * opacity))
                piece.putalpha(alpha)
            frame.alpha_composite(piece, ((cw - piece.width) // 2, (ch - piece.height) // 2))
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"no pude componer el sticker {src}:\n{proc.stderr.read().decode()[-1500:]}")
    return cw, ch, (cw - width) / 2, (ch - height) / 2


if __name__ == "__main__":
    # Comprobación rápida de la curva: pico, rebote y asentamiento.
    samples = [(t / 100, spring(t / 100)) for t in range(0, 80)]
    peak_t, peak = max(samples, key=lambda p: p[1])
    print(f"pico {peak:.3f} a {peak_t:.2f}s · a 0.5s {spring(0.5):.3f}")
