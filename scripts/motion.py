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


# --- Trayectorias -------------------------------------------------------------
# Un elemento que llega viajando engancha más que uno que aparece en su sitio:
# el ojo lo sigue desde que entra. Tres formas de llegar, y todas dejan detrás
# una estela que se dibuja con el recorrido y se recoge al aterrizar.
TRAVEL = {"bounce": 0.95, "drop": 0.85, "slide": 0.5}   # s que dura el viaje
HOP = 0.11                  # altura del primer bote, en fracción del alto del cuadro
TRAIL = 0.34                # largo de la estela, en fracción del recorrido
TRAIL_OUT = 0.3             # s en recogerse la estela tras aterrizar
TRAIL_WIDTH = 0.16          # grosor máximo, en fracción del ancho del elemento
TRAIL_COLOUR = (255, 138, 61)
STYLES = ("pop", "bounce", "drop", "slide")


def _ease_out(u):
    return 1 - (1 - u) ** 3


def travel_point(style, u, start, target, frame_h):
    """(x, y, giro) del centro del elemento en la fracción `u` del viaje."""
    (sx, sy), (tx, ty) = start, target
    if style == "bounce":
        # Tres botes que menguan mientras cruza, y una vuelta entera rodando.
        x = sx + (tx - sx) * _ease_out(u)
        y = ty - HOP * frame_h * abs(math.sin(3 * math.pi * u)) * (1 - u) ** 1.6
        return x, y, 360 * _ease_out(u) * (1 if tx > sx else -1)
    if style == "drop":
        # Cae acelerando y rebota dos veces al tocar su sitio.
        if u < 0.45:
            return tx, sy + (ty - sy) * (u / 0.45) ** 2, 0.0
        v = (u - 0.45) / 0.55
        y = ty - HOP * 0.7 * frame_h * abs(math.sin(2 * math.pi * v)) * (1 - v) ** 1.5
        return tx, y, 8 * math.sin(2 * math.pi * v) * (1 - v)
    # slide: entra por el lado más cercano y se pasa un poco, con el resorte. Al
    # acabar el viaje el resorte aún no ha llegado a 1 del todo; se reparte la
    # diferencia para que aterrice exacto y no se quede unos píxeles corto.
    duracion = TRAVEL["slide"]
    avance = spring(u * duracion) + (1 - spring(duracion)) * u
    return sx + (tx - sx) * avance, ty, 0.0


def travel_start(style, target, size, frame_w):
    """De dónde sale: fuera de cuadro, por el lado que más recorrido le dé."""
    (tx, ty), (w, h) = target, size
    if style == "drop":
        return tx, -h
    if style == "slide":
        near_left = tx < frame_w / 2
        return (-w, ty) if near_left else (frame_w + w, ty)
    far_left = tx > frame_w / 2
    return (-w, ty) if far_left else (frame_w + w, ty)


def _draw_trail(layer, points, width, colour):
    """Estela que engorda hacia el elemento: fina donde empezó, gruesa donde está."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(layer)
    count = len(points)
    for k in range(1, count):
        weight = k / count
        draw.line([points[k - 1], points[k]], width=max(2, round(width * weight)),
                  fill=colour + (round(235 * weight),))


def _paste(frame, piece, x, y):
    """Pega recortando lo que cae fuera: el viaje empieza fuera de cuadro, y
    Pillow no acepta coordenadas negativas."""
    left, top = max(0, -x), max(0, -y)
    right = min(piece.width, frame.width - x)
    bottom = min(piece.height, frame.height - y)
    if right > left and bottom > top:
        frame.alpha_composite(piece.crop((left, top, right, bottom)), (x + left, y + top))


def path_clip(src, width, dur, fps, out_path, frame_size, target_xy, style="bounce",
              trail=True, trail_colour=TRAIL_COLOUR):
    """El sticker viajando hasta su sitio, a cuadro completo y con alfa.

    `target_xy` es la esquina superior izquierda del sticker, como en el plan.
    El clip ocupa todo el cuadro porque el viaje lo cruza; se superpone en 0:0.
    """
    from PIL import Image

    frame_w, frame_h = frame_size
    art = Image.open(src).convert("RGBA")
    height = max(1, round(art.height * width / art.width))
    base = art.resize((round(width * HEADROOM), round(height * HEADROOM)), Image.LANCZOS)
    target = (target_xy[0] + width / 2, target_xy[1] + height / 2)
    start = travel_start(style, target, (width, height), frame_w)
    travel = TRAVEL[style]
    frames = max(1, round(dur * fps))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{frame_w}x{frame_h}", "-r", f"{fps:g}", "-i", "-",
         "-c:v", "png", "-pix_fmt", "rgba", str(out_path)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    empty = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    for index in range(frames):
        t = index / fps
        u = min(1.0, t / travel)
        x, y, turn = travel_point(style, u, start, target, frame_h)
        frame = empty.copy()

        if trail:
            # La estela sigue el recorrido hecho; al aterrizar se va acortando.
            length = TRAIL * (1.0 if t <= travel else max(0.0, 1 - (t - travel) / TRAIL_OUT))
            if length > 0:
                # Siempre acaba donde está el elemento: al principio del viaje el
                # recorrido hecho es más corto que la estela, y si no se recorta
                # la estela asoma por delante, por donde aún no ha pasado.
                tail = max(0.0, u - length)
                points = [travel_point(style, tail + (u - tail) * k / 24,
                                       start, target, frame_h)[:2] for k in range(25)]
                layer = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
                _draw_trail(layer, points, max(4, width * TRAIL_WIDTH), trail_colour)
                frame.alpha_composite(layer)

        # Viaja a tamaño natural; al llegar respira y al final se recoge, igual
        # que los que entran con pop.
        settled = max(0.0, t - travel)
        phase = 2 * math.pi * settled / IDLE_PERIOD
        scale = (1 + IDLE_SCALE * math.sin(phase)) * exit_scale(dur - t)
        turn += IDLE_TURN * math.sin(phase * 0.5) * min(1.0, settled / 0.3)
        w, h = round(width * scale), round(height * scale)
        if w >= 2 and h >= 2:
            piece = base.resize((w, h), Image.BICUBIC)
            if turn:
                piece = piece.rotate(-turn, resample=Image.BICUBIC, expand=True)
            _paste(frame, piece, round(x - piece.width / 2), round(y - piece.height / 2))
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"no pude componer el sticker {src}:\n{proc.stderr.read().decode()[-1500:]}")


if __name__ == "__main__":
    # Comprobación rápida de la curva: pico, rebote y asentamiento.
    samples = [(t / 100, spring(t / 100)) for t in range(0, 80)]
    peak_t, peak = max(samples, key=lambda p: p[1])
    print(f"pico {peak:.3f} a {peak_t:.2f}s · a 0.5s {spring(0.5):.3f}")
