"""Self-check: synthesize a clip with a silent gap, run the pipeline, assert it survives.

    python test_pipeline.py

Skips transcription (that needs the whisper model); words.json is faked so the
subtitle timing and the cut-timeline remapping still get exercised.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import (output_duration, output_to_source, probe_duration,  # noqa: E402
                    source_to_output)


def sh(*cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{cmd[:4]}\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}"
    return r.stdout


def make_clip(path):
    """6s of video; tone for 0-2s and 4-6s, dead silence 2-4s."""
    sh("ffmpeg", "-y", "-v", "error",
       "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=6",
       "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
       "-filter_complex", "[1:a]volume='if(between(t,2,4),0,1)':eval=frame[a]",
       "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path))


def test_shot_shape():
    """El plano arranca de parado, deriva y frena sin tirones."""
    sys.path.insert(0, str(SCRIPTS))
    from render import (CUT_HOLD, SHOT_DRIFT, SHOT_HOLD, SHOT_OUT, SHOT_RAMP,
                        effect_span, hard_cut, shot)

    e = {"t": 10.0, "type": "zoom_punch", "amount": 0.12}
    span = effect_span(e)
    expected = 10 + SHOT_RAMP * (1 + SHOT_OUT) + SHOT_HOLD
    assert span[0] == 10.0 and abs(span[1] - expected) < 1e-9, f"ventana inesperada: {span}"

    import math
    NAMES = {"PI": math.pi, "cos": math.cos, "pow": pow,
             "between": lambda x, a, b: a <= x <= b,
             "iff": lambda c, a, b: a if c else b}

    def evaluate(expr):
        return lambda when: eval(expr.replace("if(", "iff("), dict(NAMES), {"T": when})

    peak, ramp = 0.12, SHOT_RAMP
    v = evaluate(shot(10.0, ramp, SHOT_HOLD, peak))
    assert v(9.9) == 0, "arranca antes de tiempo"
    assert abs(v(10 + ramp / 2) - peak / 2) < 1e-9, "la curva no es simétrica en la rampa"
    assert v(10 + SHOT_HOLD) > v(10 + ramp + 0.05), "el plano se congela: sin deriva se ve plano"
    assert v(expected + 0.01) == 0, "no vuelve al plano original"

    # Lo que de verdad se ve como brusco es un escalón de velocidad entre dos
    # fotogramas. Con una cúbica de salida el primero valía 7.78; medir el mayor
    # escalón es lo único que distingue "suave" de "corto".
    frames = [v(10.0 - 0.1 + i / 30) for i in range(int((expected - 9.9) * 30) + 1)]
    speed = [(b - a) * 30 / peak for a, b in zip(frames, frames[1:])]
    jerk = max(abs(b - a) for a, b in zip(speed, speed[1:]))
    assert jerk < 0.5, f"tirón de velocidad entre fotogramas: {jerk:.3f}"

    # el corte sí es instantáneo: para eso está, y no debe suavizarse nunca
    c = evaluate(hard_cut(20.0, CUT_HOLD, 0.14))
    assert c(19.99) == 0 and abs(c(20.01) - 0.14) < 0.002, "cut_in dejó de ser instantáneo"
    assert c(20.0 + CUT_HOLD - 0.01) > c(20.05), "el corte tampoco debe congelarse"
    assert c(20.0 + CUT_HOLD + 0.01) == 0, "el corte no vuelve"
    print(f"ok  plano fluido (mayor tirón {jerk:.3f}) y corte instantáneo")


def test_cutaways():
    """Un clip tapa la imagen, deja el audio y va por debajo de los subtítulos."""
    sys.path.insert(0, str(SCRIPTS))
    import common
    from render import check_cutaways, cutaway_graph

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        library = tmp / "lib"
        library.mkdir()
        clip = library / "plano.mp4"
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "testsrc=size=320x568:rate=30:duration=6", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip))

        original = common.ASSETS_CONFIG
        try:
            common.ASSETS_CONFIG = tmp / "assets.json"
            common.write_json(common.ASSETS_CONFIG, {"dir": library.as_posix()})

            items = [{"t": 4.0, "dur": 3.0, "file": "plano.mp4", "start": 1.0,
                      "grade": "eq=brightness=-0.05"}]
            inputs, chunks, label = cutaway_graph(items, 1, "[graded]", 1080, 1920, 30)
            graph = ";".join(chunks)

            assert "-ss" in inputs and "1.000" in inputs, f"no recorta el origen: {inputs}"
            assert "-t" in inputs and "3.000" in inputs, "no limita la duración"
            assert "overlay=0:0" in graph, "el clip no va a pantalla completa"
            assert "between(t,4.0,7.000)" in graph, f"ventana mal puesta: {graph}"
            assert "eq=brightness=-0.05" in graph, "ignora el igualado de color"
            assert "fade=t=in" in graph and "fade=t=out" in graph, "entra y sale de golpe"
            assert "alpha=1" in graph, "el fundido tiene que ir en alfa, no en brillo"

            # sin polish no se afila nada: se pidió la imagen original
            _, raw, _ = cutaway_graph(items, 1, "[graded]", 1080, 1920, 30, polish=False)
            assert "unsharp" not in ";".join(raw), "afila aunque se pidió sin filtros"
            assert "fade=t=in" in ";".join(raw), "el fundido no depende del afilado"
            assert "scale=1080:1920" in graph, "no se lleva al tamaño de salida"
            assert ":a]" not in graph and "amix" not in graph, \
                "el clip no debe aportar audio: el del vídeo original sigue corriendo"

            # pedir más metraje del que queda tiene que fallar, no salir en negro
            too_long = [{"t": 0.0, "dur": 9.0, "file": "plano.mp4", "start": 2.0}]
            failed = False
            try:
                cutaway_graph(too_long, 1, "[graded]", 1080, 1920, 30)
            except SystemExit as error:
                failed = "quedan" in str(error)
            assert failed, "acepta más duración de la que tiene el clip"
        finally:
            common.ASSETS_CONFIG = original

    # dos a la vez, o uno sobre un retroceso, es un lío que hay que rechazar
    for items, effects, motivo in (
        ([{"t": 1.0, "dur": 3.0, "file": "a"}, {"t": 3.0, "dur": 2.0, "file": "b"}],
         [], "solapados"),
        ([{"t": 10.5, "dur": 2.0, "file": "a"}],
         [{"t": 10.0, "type": "pullback", "dur": 3.0}], "sobre un pullback"),
    ):
        try:
            check_cutaways(items, effects)
            raise AssertionError(f"acepta cutaways {motivo}")
        except SystemExit:
            pass
    print("ok  planos de recurso (tapan la imagen, no el audio)")


def test_pullback_geometry():
    """El vídeo se encoge a lo pedido, y en reposo el encuadre es 1:1.

    zoompan no sabe alejarse por debajo de 1: el truco es rellenar antes y
    encuadrar dentro. Si en reposo z no cae justo en el factor de relleno, todo
    el vídeo pasa por un remuestreo que no necesitaba.
    """
    sys.path.insert(0, str(SCRIPTS))
    import math
    from render import PULLBACK_PAD, motion_graph

    graph = motion_graph([{"t": 10.0, "type": "pullback", "dur": 2.0,
                           "ramp": 0.5, "scale": 0.76}], 30, 1080, 1920)
    assert f"pad={int(1080 * PULLBACK_PAD)}:{int(1920 * PULLBACK_PAD)}" in graph, graph

    z = graph.split("z='")[1].split("'")[0]

    def at(second):
        return eval(z.replace("if(", "iff(").replace("on", repr(second * 30)),
                    {"PI": math.pi, "cos": math.cos,
                     "between": lambda x, a, b: a <= x <= b,
                     "iff": lambda c, a, b: a if c else b})

    assert abs(at(5.0) - PULLBACK_PAD) < 1e-9, f"en reposo debe ser 1:1, es {at(5.0)}"
    assert abs(at(11.5) - PULLBACK_PAD * 0.76) < 1e-9, f"no se encoge a 0.76: {at(11.5)}"
    assert abs(at(13.5) - PULLBACK_PAD) < 1e-6, "no vuelve al tamaño original"
    assert PULLBACK_PAD * 0.76 < at(10.25) < PULLBACK_PAD, "la entrada no es progresiva"

    # sin retroceso no se rellena nada: el resto de vídeos no paga por esto
    plain = motion_graph([{"t": 1.0, "type": "zoom_punch"}], 30, 1080, 1920)
    assert "pad=" not in plain, "rellena aunque no haya retroceso"

    # El suelo tiene que ser el que aguanta el relleno, no uno elegido a ojo: por
    # debajo, zoompan recorta el desplazamiento del hueco sin avisar.
    from render import PULLBACK_MIN, PULLBACK_PAD, PULLBACK_TOP
    # El hueco visible (alto/s) menos el desplazamiento hacia arriba tiene que
    # caber en el relleno:  s >= (1+2b) / (PAD+2b),  con b = TOP-0.5.
    b = PULLBACK_TOP - 0.5
    limite = (1 + 2 * b) / (PULLBACK_PAD + 2 * b)
    assert PULLBACK_MIN >= limite - 1e-9, (
        f"PULLBACK_MIN {PULLBACK_MIN} deja pasar escalas que el relleno no sostiene "
        f"(el mínimo real con PAD={PULLBACK_PAD} es {limite:.3f})")

    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, r'%s');"
                        "from render import motion_graph;"
                        "motion_graph([{'t':1,'type':'pullback','scale':0.72}],30,1080,1920)"
                        % SCRIPTS], capture_output=True, text=True)
    assert r.returncode != 0 and "scale" in r.stderr + r.stdout, "acepta un scale imposible"
    print("ok  retroceso de plano (1:1 en reposo, encoge a lo pedido)")


def test_chapters():
    """Los capitulos salen de la linea de salida, no de la grabacion original.

    Ese es el fallo que se paga caro: escribirlos mirando el vídeo sin cortar
    deja todos corridos por lo que quitó el detector de silencios. Y YouTube
    descarta la lista entera, sin avisar, si le falta alguno de sus requisitos.
    """
    sys.path.insert(0, str(SCRIPTS))
    from chapters import check, timestamp

    assert timestamp(0) == "0:00"
    assert timestamp(247) == "4:07"
    assert timestamp(3753) == "1:02:33", timestamp(3753)

    bien = [{"t": 0.0, "title": "Uno"}, {"t": 60.0, "title": "Dos"},
            {"t": 120.0, "title": "Tres"}]
    assert len(check(bien, 200.0)) == 3

    def falla(capitulos, duracion, porque):
        try:
            check(capitulos, duracion)
        except SystemExit:
            return
        raise AssertionError(f"acepta capitulos {porque}")

    falla(bien[:2], 200.0, "por debajo del minimo de YouTube")
    falla([{"t": 5.0, "title": "Uno"}] + bien[1:], 200.0, "que no arrancan en 0:00")
    falla([{"t": 0.0, "title": "Uno"}, {"t": 4.0, "title": "Dos"},
           {"t": 60.0, "title": "Tres"}], 200.0, "de menos de 10 s")
    falla([{"t": 0.0, "title": "Uno"}, {"t": 120.0, "title": "Dos"},
           {"t": 60.0, "title": "Tres"}], 200.0, "desordenados")
    # Y el que delata el error de verdad: tiempos de la grabacion sin cortar.
    falla(bien, 100.0, "que se salen del video montado")
    print("ok  capitulos de YouTube (tiempos del montaje, no de la grabacion)")


def test_srt_output():
    """El .srt para YouTube: tiempos con coma, bloques numerados, sin karaoke."""
    sys.path.insert(0, str(SCRIPTS))
    from subtitles import NEWLINE, srt_document, srt_time

    assert srt_time(3671.5) == "01:01:11,500", srt_time(3671.5)
    assert srt_time(0) == "00:00:00,000"

    doc = srt_document([
        [{"start": 1.0, "end": 1.4, "text": "Hola"},
         {"start": 1.4, "end": 2.2, "text": "mundo."}],
        [{"start": 3.0, "end": 3.9, "text": "Segunda."}],
    ])
    bloques = doc.strip().split(NEWLINE * 2)
    assert len(bloques) == 2, doc
    cabecera = bloques[0].splitlines()
    assert cabecera[0] == "1"
    assert cabecera[1] == "00:00:01,000 --> 00:00:02,200"
    assert cabecera[2] == "Hola mundo."
    # Un srt es texto plano: si se cuela una marca de karaoke, YouTube la pinta.
    assert "{" not in doc and chr(92) + "k" not in doc
    print("ok  subtitulos en .srt para subir a YouTube")


def test_transitions_keep_colour():
    """Un fundido tiene que llevarse el color con él, y el barrido no comérselo.

    Mover la luma sin tocar el croma deja píxeles casi negros con toda su
    amplitud de color: en vez de negro sale suciedad de color. Medido antes del
    arreglo: luma 59 -> 2 con la saturación clavada en 13.1.
    """
    sys.path.insert(0, str(SCRIPTS))
    from render import blur_graph, flash_graph

    graph = flash_graph([{"t": 10.0, "type": "dip", "dur": 0.22}])
    assert "saturation=" in graph, "el fundido no toca la saturación"

    import math
    brightness, saturation = [graph.split(f"{k}='")[1].split("'")[0]
                              for k in ("brightness", "saturation")]

    # `t` va como variable, no sustituyendo texto: reemplazarla en la cadena
    # también le entra a la "t" de between, clip y sin.
    NAMES = {"PI": math.pi, "sin": math.sin, "cos": math.cos, "abs": abs,
             "clip": lambda v, lo, hi: max(lo, min(hi, v)),
             "between": lambda x, a, b: a <= x <= b,
             "iff": lambda c, a, b: a if c else b}

    def at(expr, when):
        return eval(expr.replace("if(", "iff("), dict(NAMES), {"t": when})

    peak = 10.11   # mitad del dip
    assert at(brightness, peak) < -0.4, f"el fundido no baja: {at(brightness, peak)}"
    assert at(saturation, peak) < 0.1, f"el color no acompaña al fundido: {at(saturation, peak)}"
    assert abs(at(saturation, 9.5) - 1.0) < 1e-9, "fuera del fundido la saturación debe ser 1"

    # el barrido desenfoca sólo la luma, sólo en horizontal y sólo en el tramo rápido
    whip = blur_graph([{"t": 20.0, "type": "whip_pan", "dur": 0.2}])
    assert "planes=1" in whip, "desenfocar el croma promedia los colores hacia el gris"
    assert "sizeY=1" in whip, "un barrido lateral se emborrona en horizontal, no en redondo"
    assert "between(t,20.044,20.156)" in whip, f"debe cubrir sólo el centro: {whip}"
    print("ok  transiciones (el fundido se lleva el color, el barrido no)")


def test_overlap_guard():
    """Overlapping zooms sum, so render.py must refuse them."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cuts, plan = tmp / "c.json", tmp / "p.json"
        cuts.write_text(json.dumps({"segments": [{"start": 0, "end": 9, "speed": 1.0}]}),
                        encoding="utf-8")
        plan.write_text(json.dumps({"effects": [
            {"t": 1.0, "type": "zoom_punch"}, {"t": 2.0, "type": "zoom_punch"}]}),
            encoding="utf-8")
        clip = tmp / "in.mp4"
        make_clip(clip)
        r = subprocess.run([sys.executable, str(SCRIPTS / "render.py"), str(clip),
                            "--cuts", str(cuts), "--plan", str(plan), "-o", str(tmp / "o.mp4")],
                           capture_output=True, text=True)
        assert r.returncode != 0, "aceptó dos zooms solapados"
        assert "solapad" in (r.stdout + r.stderr), "el error no explica el solape"
    print("ok  rechaza zooms solapados")


def test_deglare():
    """Only bright, near-neutral pixels get pulled down; skin and colour stay put."""
    sys.path.insert(0, str(SCRIPTS))
    from render import DEGLARE_DEFAULTS, deglare_graph

    assert deglare_graph(None) == "", "sin config no debe tocar la cadena"
    g = deglare_graph(True)
    assert "geq=" in g and "yuv444p" in g, "falta el paso a 4:4:4 antes de geq"
    assert str(DEGLARE_DEFAULTS["threshold"]) in g
    assert "0.9" in deglare_graph({"strength": 0.9}), "no aplicó el override"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src, out = tmp / "src.png", tmp / "out.png"
        # tres bandas: blanco especular, piel (naranja) y azul saturado
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "color=c=0xF0F0F0:s=60x20", "-f", "lavfi", "-i", "color=c=0xC08050:s=60x20",
           "-f", "lavfi", "-i", "color=c=0x3050F0:s=60x20",
           "-filter_complex", "[0:v][1:v][2:v]vstack=inputs=3", "-frames:v", "1", str(src))
        sh("ffmpeg", "-y", "-v", "error", "-i", str(src),
           "-vf", deglare_graph(True).lstrip(","), "-frames:v", "1", str(out))

        from PIL import Image
        a, b = Image.open(src).convert("RGB").load(), Image.open(out).convert("RGB").load()
        lum = lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
        blanco, piel, azul = [(lum(a[30, y]), lum(b[30, y])) for y in (10, 30, 50)]
        assert blanco[1] < blanco[0] - 15, f"no atenuó el especular: {blanco}"
        assert abs(piel[1] - piel[0]) < 4, f"tocó la piel: {piel}"
        assert abs(azul[1] - azul[0]) < 4, f"tocó un color saturado: {azul}"
    print("ok  deglare (baja el especular, respeta piel y color)")


SFX_LIMIT = 6.0


def test_assets_library():
    """The catalogue classifies by content, and the render finds what it lists."""
    sys.path.insert(0, str(SCRIPTS))
    import assets as assets_module
    import common
    from render import audio_graph

    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "biblioteca"
        for sub in ("music", "sfx", "stickers", "fonts"):
            (library / sub).mkdir(parents=True)

        # 8 s de tono = música de fondo; 0.4 s = efecto puntual
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "sine=frequency=200:duration=8", str(library / "music" / "bed.wav"))
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "sine=frequency=900:duration=0.4", str(library / "sfx" / "pop.wav"))
        # PNG con alpha = sticker; JPG opaco = imagen
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "color=c=red@0.5:s=64x64,format=rgba", "-frames:v", "1",
           str(library / "stickers" / "dot.png"))
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(library / "fondo.jpg"))

        catalogue = assets_module.index_directory(library)
        assert len(catalogue["music"]) == 1, f"música mal clasificada: {catalogue['music']}"
        assert len(catalogue["sfx"]) == 1, f"sfx mal clasificado: {catalogue['sfx']}"
        assert catalogue["stickers"] and catalogue["stickers"][0]["alpha"], "sticker sin alpha"
        assert catalogue["images"], "la imagen opaca debería ir a images"
        assert catalogue["music"][0]["seconds"] > SFX_LIMIT, "no se midió la duración"

        # render.py resuelve rutas relativas contra la biblioteca configurada
        original = common.ASSETS_CONFIG
        try:
            common.ASSETS_CONFIG = Path(tmp) / "assets.json"
            common.write_json(common.ASSETS_CONFIG, {"dir": library.as_posix()})
            plan = {"music": {"file": "music/bed.wav"},
                    "sfx": [{"t": 1.0, "file": "sfx/pop.wav"},
                            {"t": 2.5, "file": "sfx/pop.wav"}]}
            chunks, inputs = audio_graph(plan, 1, 10.0, -14)
            graph = ";".join(chunks)
            assert "adelay=1000" in graph and "adelay=2500" in graph, "sfx sin colocar"
            # Los efectos se juntan en un bus y ese bus cede ante la voz, así que
            # la mezcla final son tres capas: voz, música y efectos.
            assert "[sfxbus]" in graph, "los efectos no se agrupan en un bus"
            assert "[sfxbus][key_sfx]sidechaincompress" in graph, "el sfx no cede ante la voz"
            assert "amix=inputs=3" in graph, f"la mezcla no cuenta las capas: {graph[-140:]}"
            assert inputs.count("-i") == 3, "faltan entradas de audio"
        finally:
            common.ASSETS_CONFIG = original
    from assets import keyword_from
    assert keyword_from(Path("Youtube_logo.png")) == "youtube"
    assert keyword_from(Path("claude-code.png")) == "claude code"
    assert keyword_from(Path("logo.png")) == "logo", "sin palabra útil, mejor la mala que ninguna"
    print("ok  biblioteca de assets (clasifica, resuelve y mezcla sfx)")


def test_assets_autorefresh():
    """--auto recoge lo añadido desde el último indexado, y no rompe si no hay
    biblioteca: una edición no puede fallar porque falten assets opcionales."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        library = tmp / "lib" / "images"
        library.mkdir(parents=True)
        config = tmp / "assets.json"
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "color=c=red:s=64x64", "-frames:v", "1", str(library / "github.png"))

        env = dict(os.environ, FRAGUA_CONFIG=str(config))
        def run_assets(*extra):
            return subprocess.run(
                [sys.executable, str(SCRIPTS / "assets.py"), *extra],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)

        first = run_assets("--set", str(tmp / "lib"))
        assert first.returncode == 0, first.stderr
        assert "github" in first.stdout, "no indexó la primera imagen"

        # El usuario añade otra y NO reindexa a mano.
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(library / "youtube.png"))
        auto = run_assets("--auto")
        assert auto.returncode == 0, auto.stderr
        assert "youtube" in auto.stdout, "--auto no recogió la imagen nueva"

        # Sin biblioteca configurada, --auto avisa pero no falla.
        missing = dict(env, FRAGUA_CONFIG=str(tmp / "no-existe.json"))
        blank = subprocess.run(
            [sys.executable, str(SCRIPTS / "assets.py"), "--auto"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=missing)
        assert blank.returncode == 0, "una edición no debe fallar por falta de assets"
    print("ok  reindexado automático antes de editar")


def edge_energy(path, box):
    """Local contrast in a region. On a flat area this is noise, not detail."""
    from PIL import Image
    im = Image.open(path).convert("L").crop(box)
    px, (w, h) = im.load(), im.size
    e = sum(abs(px[x, y] * 4 - px[x - 1, y] - px[x + 1, y] - px[x, y - 1] - px[x, y + 1])
            for y in range(1, h - 1) for x in range(1, w - 1))
    return e / ((w - 2) * (h - 2))


def test_polish_spares_shadows():
    """Sharpening must not amplify noise in flat dark areas — that reads as
    pixelation on a black shirt, which is what unmasked cas used to do."""
    sys.path.insert(0, str(SCRIPTS))
    from render import polish_graph

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src, out = tmp / "s.png", tmp / "o.png"
        # arriba: gris oscuro con ruido leve (la camiseta). abajo: patrón con detalle real.
        sh("ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", "color=c=0x1C1C1C:s=200x120",
           "-f", "lavfi", "-i", "testsrc2=s=200x120",
           "-filter_complex", "[0:v]noise=alls=6:allf=t+u[a];[a][1:v]vstack=inputs=2",
           "-frames:v", "1", str(src))
        graph = ";".join(polish_graph("[0:v]", "[out]"))
        sh("ffmpeg", "-y", "-v", "error", "-i", str(src),
           "-filter_complex", graph, "-map", "[out]", "-frames:v", "1", str(out))

        oscuro = (10, 10, 190, 110)
        detalle = (10, 130, 190, 230)
        d0, d1 = edge_energy(src, oscuro), edge_energy(out, oscuro)
        b0, b1 = edge_energy(src, detalle), edge_energy(out, detalle)
        assert d1 <= d0 * 1.15, f"afiló la sombra plana: {d0:.2f} -> {d1:.2f}"
        assert b1 > b0 * 1.02, f"no afiló donde hay detalle: {b0:.2f} -> {b1:.2f}"
    print(f"ok  polish respeta sombras ({d0:.1f}->{d1:.1f}) y afila detalle ({b0:.1f}->{b1:.1f})")



def test_broll_stays_in_a_corner():
    """La imagen de apoyo nunca puede ocupar la pantalla ni centrarse sobre la
    persona, y su golpe de sonido nunca puede pasar por encima de la voz."""
    sys.path.insert(0, str(SCRIPTS))
    from render import (BROLL_MAX_SCALE, SFX_MAX_GAIN, audio_graph, broll_graph,
                        broll_position)

    width, height, caption_y = 1080, 1920, 1490

    # El tamaño está topado aunque el plan pida una barbaridad.
    items = [{"t": 5.0, "dur": 2.0, "scale": 0.95, "corner": "top-right"}]
    _, chunks, _ = broll_graph(items, ["x.png"], 1, "[in]", width, height, caption_y)
    graph = ";".join(chunks)
    cap = int(width * BROLL_MAX_SCALE)
    assert f"scale={cap}:" in graph, f"no aplicó el techo de tamaño: {graph[:120]}"

    # Las cuatro esquinas caen fuera de la franja central, donde está la cara.
    for corner in ("top-right", "top-left", "bottom-right", "bottom-left"):
        x, _ = broll_position(corner, width, height, cap, caption_y)
        assert "w" in x or int(x) < width * 0.25, f"{corner} se va al centro: x={x}"

    # El sfx del b-roll no puede superar el techo, pida lo que pida el plan.
    with tempfile.TemporaryDirectory() as tmp:
        hit = Path(tmp) / "pop.wav"
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "sine=frequency=900:duration=0.3", str(hit))
        plan = {"sfx": [{"t": 1.0, "file": str(hit), "gain": 12}]}
        chunks, _ = audio_graph(plan, 1, 10.0, -14)
        assert f"volume={SFX_MAX_GAIN}dB" in ";".join(chunks), "el sfx superó el techo"
    print("ok  b-roll (esquina, tamaño topado, sfx bajo la voz)")


def test_silence_at_the_head():
    """Una grabación que empieza en silencio no debe producir un segmento mudo."""
    sys.path.insert(0, str(SCRIPTS))
    from analyze import invert

    # se da a grabar, se habla a los 3.9 s, se calla a los 8
    keep = invert([(0.0, 3.87), (7.94, 8.69)], 10.0, 0.06, 0.22, 0.12)
    assert keep[0]["start"] > 3.0, f"segmento de silencio al principio: {keep[0]}"
    assert len(keep) == 2, keep

    # y con audio desde el primer fotograma no se pierde nada
    assert invert([(5.0, 6.0)], 10.0, 0.06, 0.22, 0.12)[0]["start"] == 0.0

    # El fundido de salida del render dura 0.35 s. Si el último segmento acaba
    # donde acaba la voz, se come la última palabra: hay que dejarle silencio.
    from render import TAIL_FADE
    cola = invert([(0.0, 3.87), (7.94, 9.5)], 10.0, 0.06, 0.22, 0.12)
    holgura = cola[-1]["end"] - (7.94 + 0.22)
    assert holgura >= TAIL_FADE, f"el fundido se comerá la última palabra: {holgura:.2f}s"
    assert cola[-1]["end"] <= 10.0, "se sale del vídeo"

    # Si la palabra sigue sonando por debajo del umbral de corte, el final se
    # alarga hasta el silencio de verdad — pero nunca hasta pisar el siguiente.
    from analyze import snap_ends
    trozos = [{"start": 0.0, "end": 2.0, "speed": 1.0},
              {"start": 5.0, "end": 8.0, "speed": 1.0}]
    snap_ends(trozos, [(2.3, 4.9), (8.4, 9.9)], 10.0)
    assert trozos[0]["end"] == 2.3, f"no rescató la cola: {trozos[0]}"
    assert trozos[1]["end"] == 8.4, f"no rescató la última: {trozos[1]}"
    assert trozos[0]["end"] <= trozos[1]["start"], "se solapa con el siguiente"

    # y un final que ya cae en silencio se queda donde está
    quieto = [{"start": 0.0, "end": 3.0, "speed": 1.0}]
    snap_ends(quieto, [(2.5, 4.0)], 10.0)
    assert quieto[0]["end"] == 3.0, "alarga un final que ya estaba bien"
    print("ok  silencio inicial (no fabrica un segmento mudo)")


def test_animated_cards_wiring():
    """El .mov gana al .png y no se le vuelve a animar encima.

    No se renderiza nada con remotion aquí: eso necesita Node y 230 MB de
    dependencias. Lo que se comprueba es el cableado, que es lo que se rompe.
    """
    sys.path.insert(0, str(SCRIPTS))
    from render import card_graph, resolve_card_paths

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "card00.png").write_bytes(b"x")
        paths = resolve_card_paths(tmp, 1)
        assert paths[0].suffix == ".png", paths

        (tmp / "card00.mov").write_bytes(b"x")
        paths = resolve_card_paths(tmp, 1)
        assert paths[0].suffix == ".mov", "el clip animado debe ganar al PNG"

        spec = [{"t": 4.0, "dur": 5.0, "y_frac": 0.5}]
        inputs, chunks, _ = card_graph(spec, paths, 1, "[v]", 1920)
        graph = ";".join(chunks)
        assert "fade=" not in graph, "el clip ya trae su entrada: no se le añade fundido"
        assert "-loop" not in inputs, "un .mov no se repite como si fuera una imagen"
        assert "y='960'" in graph, f"la card debe quedarse quieta en su sitio: {graph}"

        # y el PNG sigue con su fundido y su subida de siempre
        (tmp / "card00.mov").unlink()
        _, still, _ = card_graph(spec, resolve_card_paths(tmp, 1), 1, "[v]", 1920)
        assert "fade=" in ";".join(still), "la card estática perdió el fundido"
    print("ok  cards animadas (el clip gana al PNG, sin animar dos veces)")


def test_timeline_mapping():
    segments = [{"start": 0, "end": 2, "speed": 1.0}, {"start": 4, "end": 6, "speed": 1.0}]
    assert output_duration(segments) == 4.0
    assert source_to_output(1.0, segments) == 1.0
    assert source_to_output(4.5, segments) == 2.5      # gap collapsed
    assert source_to_output(3.0, segments) is None     # inside the cut
    assert source_to_output(2.0, [{"start": 0, "end": 4, "speed": 2.0}]) == 1.0
    print("ok  mapeo de timeline")


def test_version_is_consistent():
    """La versión vive en tres sitios y se desincroniza sola si nadie mira:
    los dos manifiestos y la entrada más reciente del changelog."""
    root = Path(__file__).parent
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    version = plugin["version"]

    assert market["plugins"][0]["version"] == version, (
        f"marketplace.json dice {market['plugins'][0]['version']}, plugin.json dice {version}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = next(line for line in changelog.splitlines() if line.startswith("## "))
    assert latest.split()[1] == version, f"el changelog empieza en {latest!r}, no en {version}"
    print(f"ok  versión {version} coherente (manifiestos y changelog)")


def test_digest():
    """El digest agrupa por frases y lleva los dos tiempos, ida y vuelta."""
    from transcribe import digest

    segments = [{"start": 2.0, "end": 5.0}, {"start": 9.0, "end": 12.0}]
    # Dos frases en el primer segmento y una en el segundo, en tiempo de salida.
    words = ([{"start": 0.0, "end": 0.4, "text": "hola"},
              {"start": 0.4, "end": 0.9, "text": "qué"},
              {"start": 0.9, "end": 1.3, "text": "tal."}]
             + [{"start": 2.5, "end": 2.9, "text": "segunda"}]
             + [{"start": 4.0, "end": 4.4, "text": "tercera"}])
    lines = digest(words, segments)
    assert len(lines) == 3, f"esperaba 3 frases, salieron {len(lines)}: {lines}"
    assert lines[0].endswith("hola qué tal."), lines[0]

    # 0.0 de salida es 2.0 del original; 4.0 de salida cae ya en el segundo
    # segmento, en 9.0 + (4.0 - 3.0) = 10.0.
    assert lines[0].startswith("[0:00 | 0:02]"), lines[0]
    assert lines[2].startswith("[0:04 | 0:10]"), lines[2]

    for when in (0.0, 1.5, 3.0, 4.9):
        back = source_to_output(output_to_source(when, segments), segments)
        assert abs(back - when) < 1e-6, f"ida y vuelta rompe en {when}: {back}"
    print(f"ok  digest ({len(lines)} frases, los dos tiempos)")


def test_measure(clip):
    """measure.py mide de una vez, y --card deja una lámina con las guías."""
    out = sh(sys.executable, SCRIPTS / "measure.py", clip)
    assert "640x360" in out, out
    assert "YAVG" in out and "sonoridad" in out, out

    with tempfile.TemporaryDirectory() as tmp:
        sheet = Path(tmp) / "card.png"
        sh(sys.executable, SCRIPTS / "measure.py", clip,
           "--card", "1.0", "2.0", "--sheet", sheet)
        from PIL import Image
        width, height = Image.open(sheet).size
        # Seis fotogramas de 320 px en tres columnas y dos filas.
        assert width == 320 * 3, f"lámina de {width} px de ancho"
        assert height > 300, f"lámina de {height} px de alto"
    print(f"ok  measure.py (formato, color, sonoridad y lámina de {width}px)")


def test_subtitle_font_resolves():
    """La fuente que pide el preset tiene que ser la que dibuja libass.

    Esto salió a la luz mirando el log de un render: `Roboto Black` caía a
    ArialMT. Roboto se vendoriza como fuente variable y libass no saca de ahí la
    instancia Black —tampoco con bold=1—, así que todos los subtítulos salían en
    Arial sin que nada avisara. Se comprueba el nombre, no el fichero, porque el
    fallback es silencioso por diseño.
    """
    from common import FONTS, ff_path, load_presets

    template = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
                "[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, Encoding\n"
                "Style: K,{name},80,&H00FFFFFF,{bold},2,1\n\n"
                "[Events]\nFormat: Layer, Start, End, Style, Text\n"
                "Dialogue: 0,0:00:00.00,0:00:01.00,K,,Prueba\n")

    presets = load_presets()
    names = {p["subtitle"]["fontname"]: p["subtitle"].get("bold", 0)
             for p in presets.values()
             if isinstance(p, dict) and "subtitle" in p}

    with tempfile.TemporaryDirectory() as tmp:
        ass = Path(tmp) / "t.ass"
        for name, bold in names.items():
            ass.write_text(template.format(name=name, bold=bold), encoding="utf-8")
            result = subprocess.run(
                ["ffmpeg", "-v", "verbose", "-nostdin", "-f", "lavfi",
                 "-i", "color=black:s=1080x1920:d=0.2",
                 "-vf", f"subtitles=filename='{ff_path(ass)}':fontsdir='{ff_path(FONTS)}'",
                 "-frames:v", "1", "-f", "null", "-"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            hit = re.search(r"fontselect: \(([^,]+),[^)]*\) -> ([^,]+)", result.stderr)
            assert hit, f"libass no dijo qué fuente eligió para {name!r}"
            asked, got = hit.group(1).strip(), hit.group(2).strip()
            assert got.lower().replace("-", " ").startswith(asked.split()[0].lower()), \
                f"el preset pide {asked!r} y libass dibuja {got!r}"
    print(f"ok  la fuente de subtítulos existe ({', '.join(names)})")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clip, cuts, words, subs, out = (tmp / n for n in
                                        ("in.mp4", "cuts.json", "words.json", "subs.ass", "out.mp4"))

        test_version_is_consistent()
        test_subtitle_font_resolves()
        test_digest()
        test_cutaways()
        test_pullback_geometry()
        test_chapters()
        test_srt_output()
        test_transitions_keep_colour()
        test_animated_cards_wiring()
        test_silence_at_the_head()
        test_timeline_mapping()
        test_shot_shape()
        test_overlap_guard()
        test_deglare()
        test_polish_spares_shadows()
        test_assets_library()
        test_assets_autorefresh()
        test_broll_stays_in_a_corner()

        make_clip(clip)
        assert abs(probe_duration(clip) - 6) < 0.3
        test_measure(clip)

        sh(sys.executable, SCRIPTS / "analyze.py", clip, "-o", cuts, "--threshold", "-40")
        segments = json.loads(cuts.read_text(encoding="utf-8"))["segments"]
        assert len(segments) == 2, f"esperaba 2 segmentos, salieron {len(segments)}: {segments}"
        assert output_duration(segments) < 5.0, "el silencio no se recortó"
        print(f"ok  corte de silencios ({len(segments)} segmentos, {output_duration(segments):.1f}s)")

        # Post-cut transcription: timestamps are already on the output timeline.
        payload = {"timeline": "output", "words": [
            {"start": 0.2, "end": 0.7, "text": "esto"},
            {"start": 0.8, "end": 1.4, "text": "funciona."},
            {"start": 2.3, "end": 2.3, "text": "instante"},  # whisper.cpp zero-length token
            {"start": 2.4, "end": 3.0, "text": "sigue"},
        ]}
        words.write_text(json.dumps(payload), encoding="utf-8")

        sh(sys.executable, SCRIPTS / "subtitles.py", words, "-o", subs, "--preset", "tiktok")
        ass = subs.read_text(encoding="utf-8-sig")
        # Case follows the preset, so assert the mechanism rather than a fixed style.
        from common import preset
        upper = preset("tiktok")["subtitle"].get("uppercase", False)
        cased = (lambda s: s.upper() if upper else s)

        assert "\\k" in ass, "falta el karaoke"
        assert cased("funciona") in ass, f"uppercase={upper} no se respetó"
        assert cased("instante") in ass, "se perdió una palabra de duración cero"

        # Every card kind must rasterise, and cards must silence the captions
        # underneath them while leaving the rest alone.
        cardplan = tmp / "cardplan.json"
        cardplan.write_text(json.dumps({
            "cards": [
                {"t": 2.2, "dur": 1.0, "kind": "bullets", "title": "Dato", "items": ["uno", "dos"]},
                {"t": 9.0, "dur": 1.0, "kind": "panel", "title": "P", "body": "cuerpo"},
                {"t": 9.0, "dur": 1.0, "kind": "flow", "root": "R", "nodes": ["a", "b"]},
                {"t": 9.0, "dur": 1.0, "kind": "stat", "value": "42", "label": "cosas"},
                {"t": 0.0, "dur": 1.0, "kind": "chip", "title": "Titular"},
            ],
        }), encoding="utf-8")

        cdir = tmp / "cards"
        sh(sys.executable, SCRIPTS / "cards.py", cardplan, "--preset", "tiktok", "--outdir", cdir)
        pngs = sorted(cdir.glob("card*.png"))
        assert len(pngs) == 5, f"esperaba 5 PNG, salieron {len(pngs)}"
        for png in pngs:
            assert png.stat().st_size > 2000, f"{png.name} salió vacío"
        print(f"ok  cards rasterizadas ({len(pngs)} tipos)")

        subs2 = tmp / "subs2.ass"
        sh(sys.executable, SCRIPTS / "subtitles.py", words, "-o", subs2,
           "--preset", "tiktok", "--plan", cardplan)
        ass2 = subs2.read_text(encoding="utf-8-sig")
        assert "Style: Title," not in ass2 and "Style: Card," not in ass2, \
            "títulos y cards son PNG, no estilos ASS"
        assert cased("instante") not in ass2, "la card no silenció el subtítulo que tapa"
        assert cased("funciona") in ass2, \
            "silenció subtítulos fuera de una card, o el chip del segundo 0 silenció"

        # The old ASS-title key must fail loudly instead of being silently ignored.
        oldplan = tmp / "old.json"
        oldplan.write_text(json.dumps({"text": [{"t": 0, "dur": 1, "content": "x"}]}),
                           encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "subtitles.py"), str(words),
                            "-o", str(tmp / "y.ass"), "--plan", str(oldplan)],
                           capture_output=True, text=True)
        assert r.returncode != 0, "aceptó la clave 'text' ya retirada"
        print("ok  supresión bajo card y rechazo de 'text'")

        # Feeding it a source-timeline transcript must fail loudly, not drift silently.
        stale = tmp / "stale.json"
        stale.write_text(json.dumps({"timeline": "source", "words": payload["words"]}), encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "subtitles.py"), str(stale),
                            "-o", str(tmp / "x.ass")], capture_output=True, text=True)
        assert r.returncode != 0, "aceptó una transcripción sin cortar"

        # Field counts must line up, or values spill into Text and get drawn on screen.
        fmt = next(l for l in ass.splitlines() if l.startswith("Format:") and "Text" in l)
        n = len(fmt.split(":", 1)[1].split(","))
        for line in (l for l in ass.splitlines() if l.startswith("Dialogue:")):
            text = line.split(":", 1)[1].split(",", n - 1)[-1]
            assert text.startswith("{"), f"campos desalineados, Text empieza por {text[:12]!r}"
        print("ok  subtítulos karaoke")

        plan = tmp / "plan.json"
        # Short ramp/hold: the test clip is only ~4s and zooms may not overlap.
        plan.write_text(json.dumps({"effects": [
            {"t": 0.3, "type": "zoom_punch", "ramp": 0.2, "hold": 0.4},
            {"t": 1.4, "type": "shake", "dur": 0.3},
            {"t": 2.2, "type": "flash", "dur": 0.15},
            {"t": 2.6, "type": "whip_pan", "dur": 0.2},
            {"t": 0.0, "type": "letterbox", "dur": 1.0},
        ], "cards": [{"t": 0, "dur": 1.5, "kind": "chip", "title": "No te vayas"}]}),
            encoding="utf-8")

        sh(sys.executable, SCRIPTS / "render.py", clip, "--cuts", cuts, "--subs", subs,
           "--plan", plan, "--preset", "tiktok", "-o", out)
        assert out.exists() and out.stat().st_size > 10_000, "el render salió vacío"
        rendered = probe_duration(out)
        assert abs(rendered - output_duration(segments)) < 0.5, \
            f"duración {rendered:.2f}s != corte {output_duration(segments):.2f}s"
        print(f"ok  render completo ({rendered:.1f}s, {out.stat().st_size // 1024} KB)")

    print("\ntodo verde")


if __name__ == "__main__":
    main()
