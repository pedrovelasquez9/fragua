"""Build the .ass subtitle overlay: karaoke captions burned in by render.py.

    python subtitles.py words.json -o subs.ass --preset tiktok [--plan plan.json]

Expects words.json produced by `transcribe.py --cuts cuts.json`, i.e. transcribed
from the ALREADY CUT audio. Timestamps then land straight on the output timeline
with nothing to remap, which is the only way the sync stays exact.

Cards are PNGs drawn by cards.py, not text in this file. plan.json is read only
to know when one is on screen: while it is, the captions step aside — two
competing blocks of text is what makes an edit look cluttered.
"""
import argparse

from common import preset, read_json

HEADER = """[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {w}
PlayResY: {h}
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

STYLE = ("Style: {name},{fontname},{fontsize},{primary},{secondary},{box},&H00000000,"
         "{bold},0,0,0,100,100,{spacing},0,{border_style},{outline},{shadow},"
         "{alignment},{margin_h},{margin_h},{margin_v},1")

# Sentence enders force a line break so captions track the speech rhythm.
SENTENCE_ENDERS = ".!?…"

# Floor for words whisper.cpp timestamps as instantaneous.
MIN_WORD = 0.08


def ass_time(seconds):
    """Seconds as the H:MM:SS.cc that ASS expects."""
    seconds = max(0.0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def escape(text):
    """Escape the characters ASS treats as override-block syntax."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def with_minimum_duration(words):
    """Give zero-length whisper tokens a beat so they still get drawn."""
    return [{"start": word["start"],
             "end": word["end"] if word["end"] > word["start"] else word["start"] + MIN_WORD,
             "text": word["text"]} for word in words]


def group_into_lines(words, max_chars, blocked, max_gap=0.6):
    """Split the word stream into caption lines, dropping anything a card covers."""
    lines, current = [], []

    def flush():
        nonlocal current
        if current:
            lines.append(current)
            current = []

    for word in words:
        if any(start <= word["start"] < end for start, end in blocked):
            flush()
            continue
        width = sum(len(w["text"]) + 1 for w in current) + len(word["text"])
        too_long = current and width > max_chars
        long_pause = current and word["start"] - current[-1]["end"] > max_gap
        if too_long or long_pause:
            flush()
        current.append(word)
        if word["text"][-1] in SENTENCE_ENDERS:
            flush()
    flush()
    return lines


def entrance(style, x, y, rise):
    """Slide up into place while fading and popping — the 'dynamic' part."""
    blur = f"\\blur{style['blur']}" if style.get("blur") else ""
    return (f"\\an{style['alignment']}\\move({x},{y + rise},{x},{y},0,160)"
            f"\\fad(90,70){blur}\\fscx92\\fscy92\\t(0,150,1,\\fscx100\\fscy100)")


def caption_event(line, style, geometry):
    """One Dialogue line with a karaoke sweep across its words."""
    start, end = line[0]["start"], line[-1]["end"]
    parts = [f"{{{entrance(style, geometry['center_x'], geometry['caption_y'], 26)}}}"]
    cursor = start
    for index, word in enumerate(line):
        # Fold each pause into the following word rather than emitting an empty
        # \k tag — the sweep never parks on dead air, and libass stays happy.
        centiseconds = max(1, round((word["end"] - cursor) * 100))
        text = word["text"].upper() if style.get("uppercase") else word["text"]
        space = "" if index == len(line) - 1 else " "
        parts.append(f"{{\\k{centiseconds}}}{escape(text)}{space}")
        cursor = word["end"]
    return f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{''.join(parts)}"


def build_styles(platform):
    """Only captions live here. Titles are cards of kind 'chip', drawn by cards.py:
    a title set as ASS text over the frame is what reads as a slide heading."""
    return STYLE.format(name="Caption", **platform["subtitle"])


ALONGSIDE_CAPTIONS = ("chip", "title")


def blocked_windows(cards):
    """Time ranges where a card replaces the captions.

    A chip is a small label, not a block of message, so it coexists with them.
    A title lives in the black band a `pullback` opens above the shrunk video,
    so it never lands on top of the captions either. Every other kind takes over
    the screen while it is up.
    """
    return [(float(card["t"]), float(card["t"]) + float(card.get("dur", 3)))
            for card in cards if card.get("kind", "panel") not in ALONGSIDE_CAPTIONS]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("words")
    parser.add_argument("-o", "--output", default="subs.ass")
    parser.add_argument("--preset", default="tiktok")
    parser.add_argument("--plan", default=None, help="plan.json, to know when cards hide captions")
    parser.add_argument("--max-chars", type=int, default=None,
                        help="override the preset's line length")
    parser.add_argument("--fontsize", type=int, default=None,
                        help="tamaño del subtítulo en px. Bájalo en grabaciones de "
                             "pantalla: un subtítulo grande sobre una interfaz tapa "
                             "justo lo que se está enseñando")
    parser.add_argument("--margin-v", type=int, default=None,
                        help="altura del subtítulo sobre el borde inferior, en px. "
                             "Bájalo en grabaciones de pantalla: el sitio por defecto "
                             "cae encima del contenido que se está enseñando")
    return parser.parse_args()


def main():
    args = parse_args()
    platform = preset(args.preset)
    style = platform["subtitle"]
    transcript = read_json(args.words)
    plan = read_json(args.plan) if args.plan else {}

    if transcript.get("timeline") != "output":
        raise SystemExit(
            "words.json viene del vídeo sin cortar, los subtítulos irían desincronizados.\n"
            "Regenéralo con:  python transcribe.py <vídeo> --cuts cuts.json -o words.json")

    if plan.get("text"):
        raise SystemExit(
            "plan.json usa 'text', que ya no existe: los títulos son cards.\n"
            "Conviértelo a  {\"kind\": \"chip\", \"title\": \"...\", \"t\": .., \"dur\": ..}  en \"cards\".")

    if args.margin_v is not None:
        style["margin_v"] = args.margin_v
    if args.fontsize is not None:
        style["fontsize"] = args.fontsize
        # El contorno se dimensiona con la fuente; si no, un texto pequeño queda
        # con un borde desproporcionado que ocupa más que las letras.
        style["outline"] = max(4, round(style["outline"] * args.fontsize / 56))
    geometry = {"center_x": platform["width"] // 2,
                "caption_y": platform["height"] - style["margin_v"]}

    cards = plan.get("cards", [])
    words = with_minimum_duration(transcript["words"])
    lines = group_into_lines(words, args.max_chars or style["max_chars"], blocked_windows(cards))
    if not lines:
        raise SystemExit("no quedó ninguna palabra visible — ¿las cards cubren todo el vídeo?")

    events = [caption_event(line, style, geometry) for line in lines]
    header = HEADER.format(w=platform["width"], h=platform["height"],
                           styles=build_styles(platform))
    with open(args.output, "w", encoding="utf-8-sig") as handle:
        handle.write(header)
        handle.write("\n".join(events) + "\n")

    blocking = len(blocked_windows(cards))
    print(f"{len(lines)} subtítulos · {len(cards)} cards, {blocking} los ocultan -> {args.output}")


if __name__ == "__main__":
    main()
