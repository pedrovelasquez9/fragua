"""Render the final video: cuts + effects + grade + subtitles + audio, in one ffmpeg pass.

    python render.py input.mp4 --cuts cuts.json --preset tiktok -o out.mp4
                     [--subs subs.ass] [--plan plan.json] [--no-grade] [--print-cmd]

All plan.json timestamps are on the OUTPUT timeline (after silence removal),
which is what you see when you watch the rough cut.
"""
import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import (FONTS, ROOT, assets_dir, atempo_chain, ff_path, output_duration,
                    preset, probe_stream, read_json, resolve_asset)

# ponytail: one filtergraph per segment stops scaling somewhere past here, so we
# fall back to a cut pass + a style pass. Two encodes, but it finishes.
MAX_SEGMENTS_ONE_PASS = 300

# Titles and cards are drawn by libass from the .ass file, not by drawtext:
# that way they inherit the caption font, box and animations for free.

GRADE = (
    "curves=r='0/0.02 0.5/0.53 1/0.98':g='0/0.01 0.5/0.5 1/0.99':b='0/0.06 0.5/0.48 1/0.94',"
    "colorbalance=rs=-0.05:bs=0.06:rh=0.05:bh=-0.05,"
    "eq=contrast=1.10:saturation=1.06:gamma=0.98"
)
# hqdn3d's last two params are TEMPORAL. Anything above ~2 smears motion on a
# talking head, which reads as low framerate and mushy detail. Keep them low and
# never let a plan.json grade add a second hqdn3d on top.
DENOISE = "hqdn3d=2:1.5:2:2"

# cas sharpens whatever local contrast it finds. In a flat dark area — a black
# shirt, a dim background — the only local contrast is the source encoder's
# blocking, so it turns compression noise into crisp visible texture. Measured
# unmasked: +93% sharpness on the face but +118% artefact on the shirt, a losing
# trade at any strength. Gated by luma it is +44% / +19%.
SHARPEN = "cas=strength=0.5"
SHARPEN_FLOOR = 45      # luma below which nothing gets sharpened
SHARPEN_RAMP = 50       # width of the fade-in above that floor


def polish_graph(src, dst):
    """Denoise, then sharpen only where there is real detail to sharpen."""
    ramp = f"clip((val-{SHARPEN_FLOOR})*255/{SHARPEN_RAMP},0,255)"
    return [f"{src}{DENOISE},split=3[pbase][psharp][pmask]",
            f"[psharp]{SHARPEN}[psharpened]",
            f"[pmask]lutyuv=y='{ramp}':u=val:v=val[pkey]",
            f"[pbase][psharpened][pkey]maskedmerge{dst}"]

# Broadcast-style voice chain. Order matters: clean up before boosting, or the
# EQ lift amplifies the very noise the denoiser is meant to remove.
VOICE = (
    "highpass=f=85,"                             # rumble, handling noise, plosives
    "afftdn=nr=10:nf=-32,"                       # broadband room tone
    "equalizer=f=280:t=q:w=1.2:g=-2.5,"          # cut the boxy low-mid mud
    "equalizer=f=3200:t=q:w=1.4:g=3,"            # presence: where intelligibility lives
    "equalizer=f=8000:t=q:w=2:g=1.5,"            # air
    "deesser=i=0.35,"                            # tame the sibilance the presence boost adds
    "acompressor=threshold=-20dB:ratio=3.5:attack=6:release=140"
)

# Attenuate specular reflections (glasses, sweat, shiny surfaces) by pulling down
# pixels that are both bright AND near-neutral in chroma. The saturation gate is
# what keeps it off skin and off coloured lights, which are chromatic.
#
# ponytail: this DIMS a reflection, it cannot remove one. Where a lens reflection
# replaced what was behind it, there is nothing underneath to recover — push the
# strength too far and you trade a white patch for a grey one, which looks worse.
# Costs ~4x render time (geq is per-pixel), so it stays opt-in.
DEGLARE_DEFAULTS = {"threshold": 160, "feather": 30, "sat_max": 50,
                    "sat_feather": 20, "strength": 0.65}


def deglare_graph(cfg):
    if not cfg:
        return ""
    o = dict(DEGLARE_DEFAULTS, **(cfg if isinstance(cfg, dict) else {}))
    # yuv444p first: in 4:2:0 the chroma planes are half size, so cb(X,Y) inside
    # the luma expression would sample the wrong pixel.
    return (",format=yuv444p,geq="
            f"lum='st(0,lum(X,Y));"
            f"st(1,hypot(cb(X,Y)-128,cr(X,Y)-128));"
            f"st(2,clip((ld(0)-{o['threshold']})/{o['feather']},0,1)"
            f"*clip(({o['sat_max']}-ld(1))/{o['sat_feather']},0,1));"
            f"ld(0)-ld(2)*(ld(0)-{o['threshold']})*{o['strength']}'"
            ":cb='cb(X,Y)':cr='cr(X,Y)',format=yuv420p")


# Un efecto puntual acompaña, no compite: por encima de -3 dB empieza a tapar la
# voz, que va normalizada a -14 LUFS. El techo no es configurable a propósito.
SFX_DEFAULT_GAIN = -6
SFX_MAX_GAIN = -3

# Never end on a hard audio cut — it reads as a truncated sentence.
TAIL_FADE = 0.35

CARD_FADE = 0.28

# zoom_punch defaults: push in over SHOT_RAMP, stay SHOT_HOLD, pull back out.
SHOT_RAMP = 0.35
SHOT_HOLD = 2.0

# Effects that contribute to the zoom expression, and therefore cannot overlap.
ZOOMING = ("zoom_punch", "shake", "whip_pan")

# aq-mode=3 biases bit allocation toward dark areas — this footage is mostly shadow,
# and flat AQ is what leaves blocking in the background.
X264_PARAMS = "aq-mode=3:aq-strength=1.0"
FILM = "vignette=PI/5,noise=alls=5:allf=t+u"


def cut_graph(segments):
    """trim/concat every kept segment into [vc][ac]."""
    chunks, labels = [], []
    for i, s in enumerate(segments):
        speed = s.get("speed", 1.0)
        v = f"[0:v]trim=start={s['start']}:end={s['end']},setpts=PTS-STARTPTS"
        a = f"[0:a]atrim=start={s['start']}:end={s['end']},asetpts=PTS-STARTPTS"
        if speed != 1.0:
            v += f",setpts=PTS/{speed}"
            a += f",{atempo_chain(speed)}"
        chunks += [f"{v}[v{i}]", f"{a}[a{i}]"]
        labels.append(f"[v{i}][a{i}]")
    chunks.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[vc][ac]")
    return ";".join(chunks)


def bump(t0, dur, peak):
    """A smooth 0 -> peak -> 0 hump over [t0, t0+dur], as an ffmpeg expression."""
    return f"if(between(T,{t0},{t0 + dur}),{peak}*sin(PI*(T-{t0})/{dur}),0)"


def shot(t0, ramp, hold, peak):
    """Ease in, hold, ease out — a push to a tighter framing that stays there.

    A hump peaks and immediately retreats, which reads as a twitch. Holding the
    new framing for a couple of seconds reads as a cut to a second camera.
    """
    a, b = t0 + ramp, t0 + ramp + hold
    end = b + ramp
    rise = f"{peak}*(0.5-0.5*cos(PI*(T-{t0})/{ramp}))"
    fall = f"{peak}*(0.5+0.5*cos(PI*(T-{b})/{ramp}))"
    return (f"if(between(T,{t0},{a}),{rise},"
            f"if(between(T,{a},{b}),{peak},"
            f"if(between(T,{b},{end}),{fall},0)))")


def effect_span(e):
    """Wall-clock window an effect occupies, whatever its shape."""
    t0 = float(e["t"])
    if e["type"] == "zoom_punch":
        ramp = float(e.get("ramp", SHOT_RAMP))
        return t0, t0 + 2 * ramp + float(e.get("hold", SHOT_HOLD))
    return t0, t0 + float(e.get("dur", 0.5))


def check_overlaps(effects):
    """Zoom contributions are summed, so two overlapping ones double the zoom."""
    zooming = sorted((e for e in effects if e["type"] in ZOOMING),
                     key=lambda e: float(e["t"]))
    for first, second in zip(zooming, zooming[1:]):
        end = effect_span(first)[1]
        start = float(second["t"])
        if start < end:
            sys.exit(
                f"efectos de zoom solapados: {first['type']} en {first['t']}s acaba en "
                f"{end:.2f}s y {second['type']} empieza en {start}s.\n"
                f"Los zooms se suman: sepáralos o baja 'hold'.")


def motion_graph(effects, fps, width, height):
    """zoom punches, shakes and whip pans, all as one zoompan filter."""
    zoom, xoff, yoff = ["1"], ["0"], ["0"]
    for e in effects:
        t0, dur = float(e["t"]), float(e.get("dur", 0.5))
        if effect_span(e)[1] <= t0:   # zoom_punch is sized by ramp/hold, not dur
            continue
        kind = e["type"]
        if kind == "zoom_punch":
            zoom.append(shot(t0, float(e.get("ramp", SHOT_RAMP)),
                             float(e.get("hold", SHOT_HOLD)), e.get("amount", 0.15)))
        elif kind == "shake":
            amp = e.get("amount", 8)
            decay = f"(1-(T-{t0})/{dur})"
            xoff.append(f"if(between(T,{t0},{t0 + dur}),{amp}*sin(2*PI*14*(T-{t0}))*{decay},0)")
            yoff.append(f"if(between(T,{t0},{t0 + dur}),{amp}*cos(2*PI*11*(T-{t0}))*{decay},0)")
            zoom.append(bump(t0, dur, 0.06))  # headroom so the shake has somewhere to go
        elif kind == "whip_pan":
            zoom.append(bump(t0, dur, 0.30))
            xoff.append(f"if(between(T,{t0},{t0 + dur}),iw*0.22*sin(2*PI*(T-{t0})/{dur}),0)")

    if len(zoom) == 1 and len(xoff) == 1 and len(yoff) == 1:
        return ""

    time = f"(on/{fps})"
    z = "+".join(zoom).replace("T", time)
    x = f"(iw/2-(iw/zoom/2))+({'+'.join(xoff)})".replace("T", time)
    y = f"(ih/2-(ih/zoom/2))+({'+'.join(yoff)})".replace("T", time)
    # s= is mandatory: zoompan silently defaults to 1280x720 otherwise.
    return f",zoompan=z='{z}':x='{x}':y='{y}':d=1:fps={fps}:s={width}x{height}"


def flash_graph(effects):
    bumps = [bump(float(e["t"]), float(e.get("dur", 0.15)), e.get("amount", 0.45))
             for e in effects if e["type"] == "flash"]
    if not bumps:
        return ""
    return f",eq=brightness='{'+'.join(bumps).replace('T', 't')}':eval=frame"


def blur_graph(effects):
    windows = [f"between(t,{e['t']},{float(e['t']) + float(e.get('dur', 0.2))})"
               for e in effects if e["type"] == "whip_pan"]
    if not windows:
        return ""
    return f",gblur=sigma=12:enable='{'+'.join(windows)}'"


def letterbox_graph(effects, height):
    bars = []
    for e in effects:
        if e["type"] != "letterbox":
            continue
        end = float(e["t"]) + float(e.get("dur", 3))
        bar = int(height * e.get("amount", 0.12))
        window = f"between(t,{e['t']},{end})"
        bars.append(f",drawbox=x=0:y=0:w=iw:h={bar}:color=black@1:t=fill:enable='{window}'")
        bars.append(f",drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black@1:t=fill:enable='{window}'")
    return "".join(bars)


def sticker_graph(stickers, start_index, width, height):
    """Returns (extra_inputs, filter_chunks). Each sticker is its own overlay."""
    inputs, chunks, label = [], [], "[styled]"
    for i, s in enumerate(stickers):
        path = asset_path(s["file"], "sticker")
        idx = start_index + i
        inputs += ["-i", str(path)]
        t0, dur = float(s["t"]), float(s.get("dur", 2))
        w = int(width * s.get("scale", 0.2))
        nxt = f"[ov{i}]"
        chunks.append(f"[{idx}:v]scale={w}:-1[s{i}]")
        chunks.append(f"{label}[s{i}]overlay=x={s.get('x', f'W*0.7')}:y={s.get('y', f'H*0.15')}"
                      f":enable='between(t,{t0},{t0 + dur})'{nxt}")
        label = nxt
    return inputs, chunks, label


# B-roll: una imagen pequeña en una esquina cuando se menciona algo concreto.
# Nunca a pantalla completa y nunca sobre la persona, que en un plano vertical
# ocupa la franja central. Por eso sólo hay esquinas y el ancho está topado.
BROLL_SCALE = 0.28          # fracción del ancho por defecto
BROLL_MAX_SCALE = 0.40      # techo duro: por encima empieza a tapar al que habla
BROLL_MARGIN = 0.05         # separación al borde, en fracción del ancho
BROLL_FADE = 0.25

# El eje Y del pie evita la banda de subtítulos, que vive en margin_v.
BROLL_CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")


def broll_position(corner, width, height, image_width, caption_y):
    """(x, y) de la esquina pedida, en píxeles del fotograma de salida."""
    margin = int(width * BROLL_MARGIN)
    top = int(margin * 1.6)
    # Por abajo, apoyado sobre la banda de subtítulos para no invadirla.
    bottom = f"{caption_y}-h-{margin}"
    right = f"{width - margin}-w"
    return {
        "top-right":    (right, str(top)),
        "top-left":     (str(margin), str(top)),
        "bottom-right": (right, bottom),
        "bottom-left":  (str(margin), bottom),
    }[corner]


def broll_graph(items, paths, start_index, base_label, width, height, caption_y):
    """Superpone cada imagen de apoyo con entrada por fundido y deslizamiento."""
    inputs, chunks, label = [], [], base_label
    for i, (spec, path) in enumerate(zip(items, paths)):
        t0 = float(spec["t"])
        dur = float(spec.get("dur", 2.5))
        corner = spec.get("corner", "top-right")
        if corner not in BROLL_CORNERS:
            sys.exit(f"esquina desconocida para el b-roll: {corner}. "
                     f"Usa: {', '.join(BROLL_CORNERS)}")
        scale = min(float(spec.get("scale", BROLL_SCALE)), BROLL_MAX_SCALE)
        fade = min(BROLL_FADE, dur / 3)

        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
        chunks.append(
            f"[{start_index + i}:v]scale={int(width * scale)}:-1,format=rgba,"
            f"fade=t=in:st=0:d={fade:.2f}:alpha=1,"
            f"fade=t=out:st={dur - fade:.3f}:d={fade:.2f}:alpha=1,"
            f"setpts=PTS+{t0:.3f}/TB[b{i}]")

        x, y = broll_position(corner, width, height, int(width * scale), caption_y)
        # Entra deslizándose unos píxeles desde el borde más cercano.
        rise = int(height * 0.012)
        y_expr = f"{y}+{rise}*(1-min(1,(t-{t0})/{fade:.2f}))"
        nxt = f"[bv{i}]"
        chunks.append(f"{label}[b{i}]overlay=x='{x}':y='{y_expr}'"
                      f":enable='between(t,{t0},{t0 + dur})'{nxt}")
        label = nxt
    return inputs, chunks, label


def card_graph(cards, paths, start_index, base_label, height):
    """Overlay each pre-rendered card at its cue.

    A still PNG is looped into a short clip so `fade` has a timeline to work on;
    an animated .mov already has one. Either way `setpts` shifts it into place.
    """
    inputs, chunks, label = [], [], base_label
    for i, (spec, path) in enumerate(zip(cards, paths)):
        t0, dur = float(spec["t"]), float(spec.get("dur", 3))
        top = int(height * spec.get("y_frac", 0.60))
        if path.suffix == ".mov":
            # The clip already carries its entrance and exit, so adding a fade
            # and a slide here would animate the animation.
            inputs += ["-i", str(path)]
            chunks.append(f"[{start_index + i}:v]format=rgba,"
                          f"setpts=PTS-STARTPTS+{t0:.3f}/TB[c{i}]")
            y = str(top)
        else:
            rise = int(height * 0.018)
            fade = min(CARD_FADE, dur / 3)
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
            chunks.append(
                f"[{start_index + i}:v]format=rgba,"
                f"fade=t=in:st=0:d={fade:.2f}:alpha=1,"
                f"fade=t=out:st={dur - fade:.3f}:d={fade:.2f}:alpha=1,"
                f"setpts=PTS+{t0:.3f}/TB[c{i}]")
            y = f"{top}+{rise}*(1-min(1,(t-{t0})/{fade:.2f}))"
        nxt = f"[cv{i}]"
        chunks.append(f"{label}[c{i}]overlay=x=0:y='{y}':enable='between(t,{t0},{t0 + dur})'{nxt}")
        label = nxt
    return inputs, chunks, label


def asset_path(spec, label):
    """Resolve a plan.json file reference against the configured asset library."""
    path = resolve_asset(spec)
    if not path.exists():
        sys.exit(f"{label} no encontrado: {path}\n"
                 f"Revisa el catálogo con:  python scripts/assets.py")
    return path


def audio_graph(plan, first_index, duration, lufs):
    """Voice chain, plus optional background music and one-shot sound effects."""
    fade = TAIL_FADE if duration > TAIL_FADE * 2 else 0
    finish = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    if fade:
        finish += f",afade=t=out:st={duration - fade:.3f}:d={fade}"

    music = plan.get("music")
    sfx = plan.get("sfx", [])
    chunks, inputs, index = [], [], first_index

    if not music and not sfx:
        return [f"[ac]{VOICE},{finish}[aout]"], []

    # La voz se reparte: una copia va a la mezcla y otra hace de llave para el
    # ducking de cada capa que deba ceder ante ella.
    keys = ["voice_mix"] + (["key_music"] if music else []) + (["key_sfx"] if sfx else [])
    chunks.append(f"[ac]{VOICE}[voice]")
    chunks.append(f"[voice]asplit={len(keys)}" + "".join(f"[{k}]" for k in keys))

    layers = []

    if music:
        path = asset_path(music["file"], "música")
        inputs += ["-i", str(path)]
        gain = music.get("gain", -18)
        chunks.append(f"[{index}:a]volume={gain}dB,aloop=loop=-1:size=2000000000,"
                      f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[bed]")
        if music.get("duck", True):
            chunks.append("[bed][key_music]sidechaincompress=threshold=0.05:ratio=8"
                          ":attack=5:release=300[bed_ducked]")
            layers.append("[bed_ducked]")
        else:
            chunks.append("[key_music]anullsink")
            layers.append("[bed]")
        index += 1

    if sfx:
        # adelay coloca cada golpe; apad iguala la longitud de las ramas, porque
        # amix corta la mezcla en cuanto termina la más corta.
        branches = []
        for number, effect in enumerate(sfx):
            path = asset_path(effect["file"], "sfx")
            inputs += ["-i", str(path)]
            start_ms = int(float(effect["t"]) * 1000)
            gain = min(float(effect.get("gain", SFX_DEFAULT_GAIN)), SFX_MAX_GAIN)
            chunks.append(f"[{index}:a]volume={gain}dB,adelay={start_ms}:all=1,"
                          f"apad=whole_dur={duration:.3f}[sfx{number}]")
            branches.append(f"[sfx{number}]")
            index += 1

        if len(branches) > 1:
            chunks.append(f"{''.join(branches)}amix=inputs={len(branches)}:"
                          f"duration=first:normalize=0[sfxbus]")
        else:
            chunks.append(f"{branches[0]}anull[sfxbus]")

        # Bajar la ganancia NO basta: dos señales se suman, así que el pico de
        # voz+efecto siempre supera al de la voz sola por mucho que se atenúe.
        # La única forma de que el apoyo no pase por encima es que ceda ante ella.
        chunks.append("[sfxbus][key_sfx]sidechaincompress=threshold=0.02:ratio=6"
                      ":attack=3:release=180[sfx_ducked]")
        layers.append("[sfx_ducked]")

    chunks.append(f"[voice_mix]{''.join(layers)}"
                  f"amix=inputs={1 + len(layers)}:duration=first:normalize=0,{finish}[aout]")
    return chunks, inputs


def video_graph(args, platform, effects, plan):
    """Frame -> motion -> polish -> look -> subtitles, ending at [styled]."""
    width, height, fps = platform["width"], platform["height"], platform["fps"]

    # Polish is its own labelled sub-graph because the sharpening mask needs a split.
    framing = (f"fps={fps},"
               f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
               f"crop={width}:{height}")
    framing += deglare_graph(plan.get("deglare"))   # source fix: before grading it
    framing += motion_graph(effects, fps, width, height)

    chunks = [f"[vc]{framing}[prepolish]"]
    chunks += polish_graph("[prepolish]", "[polished]")

    look = ""
    if not args.no_grade:
        # The right look depends on the footage, not the platform, so plan.json
        # can replace it wholesale (dark material hates the default vignette).
        look += "," + plan.get("grade", f"{GRADE},{FILM}")
    look += flash_graph(effects) + blur_graph(effects) + letterbox_graph(effects, height)
    if args.subs:
        # fontsdir so libass finds the bundled fonts without installing them system-wide.
        # fontsdir apunta a las fuentes propias si existen, y si no a las de vendor:
        # libass sólo acepta un directorio, así que gana la biblioteca del usuario.
        user_fonts = assets_dir() / "fonts"
        fonts = user_fonts if user_fonts.is_dir() else FONTS
        look += f",subtitles=filename='{ff_path(args.subs)}':fontsdir='{ff_path(fonts)}'"
    chunks.append(f"[polished]{look.lstrip(',') or 'null'}[styled]")
    return chunks


def resolve_card_paths(cards_dir, count):
    """cardNN.mov (animated) or cardNN.png (still), in plan order.

    The .mov wins when both exist, so re-running cards.py --animated upgrades an
    edit without touching plan.json. The index is the contract with cards.py.
    """
    if not cards_dir or not count:
        return []
    paths = []
    for index in range(count):
        stem = Path(cards_dir) / f"card{index:02d}"
        clip, still = stem.with_suffix(".mov"), stem.with_suffix(".png")
        if clip.exists():
            paths.append(clip)
        elif still.exists():
            paths.append(still)
        else:
            sys.exit(f"falta la card {index}: {still} — ejecuta scripts/cards.py primero")
    return paths


def resolve_broll_paths(items):
    """Cada imagen de apoyo, resuelta contra la biblioteca de assets."""
    return [asset_path(item["file"], "b-roll") for item in items]


def encoder_flags(platform, output):
    """x264 settings shared by both render paths."""
    return ["-c:v", "libx264", "-preset", platform["preset"], "-crf", str(platform["crf"]),
            "-x264-params", X264_PARAMS,
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(platform["fps"]),
            "-c:a", "aac", "-b:a", platform["audio_bitrate"], "-ar", "48000",
            "-movflags", "+faststart", str(output)]


def build(args, platform, segments, plan, source):
    """The whole render as a single ffmpeg command."""
    effects = plan.get("effects", [])
    check_overlaps(effects)
    width, height = platform["width"], platform["height"]

    graph = [cut_graph(segments)]
    graph += video_graph(args, platform, effects, plan)

    # Overlay inputs are numbered after the source, in the order they are added.
    stickers, cards = plan.get("stickers", []), plan.get("cards", [])
    next_input = 1

    sticker_inputs, sticker_chunks, video_label = sticker_graph(
        stickers, next_input, width, height)
    graph += sticker_chunks
    next_input += len(stickers)

    card_inputs, card_chunks, video_label = card_graph(
        cards, resolve_card_paths(args.cards, len(cards)), next_input, video_label, height)
    graph += card_chunks
    next_input += len(cards)

    broll = plan.get("broll", [])
    caption_y = platform["height"] - platform["subtitle"]["margin_v"]
    broll_inputs, broll_chunks, video_label = broll_graph(
        broll, resolve_broll_paths(broll), next_input, video_label,
        width, height, caption_y)
    graph += broll_chunks
    next_input += len(broll)

    # Cada imagen de apoyo puede traer su propio golpe de sonido de entrada.
    plan_with_broll_sfx = dict(plan)
    plan_with_broll_sfx["sfx"] = list(plan.get("sfx", [])) + [
        {"t": item["t"], "file": item["sfx"], "gain": item.get("sfx_gain", SFX_DEFAULT_GAIN)}
        for item in broll if item.get("sfx")]

    audio_chunks, music_input = audio_graph(
        plan_with_broll_sfx, next_input, output_duration(segments), platform["lufs"])
    graph += audio_chunks

    return (["ffmpeg", "-y", "-hide_banner", "-i", str(source)]
            + sticker_inputs + card_inputs + broll_inputs + music_input
            + ["-filter_complex", ";".join(graph), "-map", video_label, "-map", "[aout]"]
            + encoder_flags(platform, args.output))


def cut_only(source, segments, fps, destination):
    """First of the two passes used when a cut has too many segments for one graph."""
    return ["ffmpeg", "-y", "-hide_banner", "-i", str(source),
            "-filter_complex", cut_graph(segments),
            "-map", "[vc]", "-map", "[ac]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "14", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "pcm_s16le", str(destination)]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input")
    parser.add_argument("--cuts", required=True, help="cuts.json from analyze.py")
    parser.add_argument("--preset", default="tiktok")
    parser.add_argument("--subs", default=None, help="subs.ass from subtitles.py")
    parser.add_argument("--plan", default=None, help="plan.json: grade, effects, cards, music")
    parser.add_argument("--cards", default=None, help="carpeta con los PNG de cards.py")
    parser.add_argument("-o", "--output", default="output.mp4")
    parser.add_argument("--no-grade", action="store_true", help="skip the cinematic look")
    parser.add_argument("--print-cmd", action="store_true",
                        help="print the ffmpeg command before running it")
    return parser.parse_args()


def run_render(command, print_command):
    if print_command:
        print(" ".join(command))
    subprocess.run(command, check=True)


def main():
    args = parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg no está en el PATH")

    platform = preset(args.preset)
    segments = read_json(args.cuts)["segments"]
    plan = read_json(args.plan) if args.plan else {}
    probe_stream(args.input)  # fails loudly if the input is unreadable
    duration = output_duration(segments)

    if len(segments) <= MAX_SEGMENTS_ONE_PASS:
        run_render(build(args, platform, segments, plan, args.input), args.print_cmd)
    else:
        print(f"{len(segments)} segmentos: paso de corte + paso de estilo")
        with tempfile.TemporaryDirectory() as workdir:
            rough = Path(workdir) / "rough.mkv"
            subprocess.run(cut_only(args.input, segments, platform["fps"], rough), check=True)
            # The rough cut is already trimmed, so the styling pass sees one segment.
            flat = [{"start": 0.0, "end": duration, "speed": 1.0}]
            run_render(build(args, platform, flat, plan, rough), args.print_cmd)

    print(f"listo -> {args.output} ({duration:.1f}s, {args.preset})")


if __name__ == "__main__":
    main()
