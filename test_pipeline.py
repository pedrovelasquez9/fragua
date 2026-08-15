"""Self-check: synthesize a clip with a silent gap, run the pipeline, assert it survives.

    python test_pipeline.py

Skips transcription (that needs the whisper model); words.json is faked so the
subtitle timing and the cut-timeline remapping still get exercised.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import output_duration, probe_duration, source_to_output  # noqa: E402


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
    """zoom_punch must ease in, hold flat, then ease out."""
    sys.path.insert(0, str(SCRIPTS))
    from render import SHOT_HOLD, SHOT_RAMP, effect_span, shot

    e = {"t": 10.0, "type": "zoom_punch", "amount": 0.12}
    start, end = effect_span(e)
    assert start == 10.0 and abs(end - (10 + 2 * SHOT_RAMP + SHOT_HOLD)) < 1e-9, \
        f"ventana inesperada: {start}-{end}"

    expr = shot(10.0, 0.4, 2.0, 0.12)
    import math

    def value(t):  # evaluate the ffmpeg expression the same way ffmpeg would
        return eval(expr.replace("T", repr(t)).replace("PI", "math.pi")
                    .replace("if(", "iff(").replace("between(", "btw("),
                    {"iff": lambda c, a, b: a if c else b,
                     "btw": lambda t, a, b: a <= t <= b, "math": math, "cos": math.cos})

    assert value(9.9) == 0, "arranca antes de tiempo"
    assert value(10.2) < 0.12, "la entrada no es progresiva"
    assert abs(value(11.0) - 0.12) < 1e-9, "no mantiene el plano"
    assert abs(value(12.2) - 0.12) < 1e-9, "no mantiene el plano hasta el final"
    assert 0 < value(12.6) < 0.12, "la salida no es progresiva"
    assert value(12.9) == 0, "no vuelve al plano original"
    print("ok  plano sostenido (entra, mantiene 2s, sale)")


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
    print("ok  biblioteca de assets (clasifica, resuelve y mezcla sfx)")


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


def test_timeline_mapping():
    segments = [{"start": 0, "end": 2, "speed": 1.0}, {"start": 4, "end": 6, "speed": 1.0}]
    assert output_duration(segments) == 4.0
    assert source_to_output(1.0, segments) == 1.0
    assert source_to_output(4.5, segments) == 2.5      # gap collapsed
    assert source_to_output(3.0, segments) is None     # inside the cut
    assert source_to_output(2.0, [{"start": 0, "end": 4, "speed": 2.0}]) == 1.0
    print("ok  mapeo de timeline")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clip, cuts, words, subs, out = (tmp / n for n in
                                        ("in.mp4", "cuts.json", "words.json", "subs.ass", "out.mp4"))

        test_timeline_mapping()
        test_shot_shape()
        test_overlap_guard()
        test_deglare()
        test_polish_spares_shadows()
        test_assets_library()
        test_broll_stays_in_a_corner()

        make_clip(clip)
        assert abs(probe_duration(clip) - 6) < 0.3

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
