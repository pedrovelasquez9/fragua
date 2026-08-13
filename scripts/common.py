"""Shared helpers: paths, JSON I/O, ffmpeg invocation and cut-timeline mapping.

Every script in this skill imports from here. Nothing in the pipeline talks to a
network service, so there are no credentials to configure anywhere.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "presets.json"
VENDOR = ROOT / "vendor"
FONTS = VENDOR / "fonts"


# --- JSON -------------------------------------------------------------------

def read_json(path):
    # utf-8-sig: Windows editors like to prepend a BOM to hand-edited JSON.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_presets():
    return read_json(PRESETS)


# --- asset library ----------------------------------------------------------

ASSETS_CONFIG = ROOT / "assets.json"


def assets_dir():
    """Where the user's music, sfx, stickers and fonts live.

    Set with `python scripts/assets.py --set <path>`. Falls back to the bundled
    assets/ folder, so everything works before anyone configures anything.
    """
    if ASSETS_CONFIG.exists():
        configured = read_json(ASSETS_CONFIG).get("dir")
        if configured:
            return Path(configured)
    return ROOT / "assets"


def resolve_asset(path):
    """Absolute path, or one relative to the asset library, or to the skill root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    for base in (assets_dir(), ROOT):
        if (base / candidate).exists():
            return base / candidate
    return assets_dir() / candidate


def preset(name):
    """One platform preset. Keys starting with '_' are documentation, not presets."""
    presets = {k: v for k, v in load_presets().items() if not k.startswith("_")}
    if name not in presets:
        sys.exit(f"preset desconocido: {name}. Disponibles: {', '.join(presets)}")
    return presets[name]


# --- ffmpeg -----------------------------------------------------------------

def run(command, capture=False):
    """Run a command, exiting with its stderr on failure."""
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        head = " ".join(str(part) for part in command[:3])
        sys.exit(f"falló: {head}...\n{result.stderr[-3000:]}")
    return result if capture else None


def probe_duration(video):
    """Container duration in seconds."""
    result = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=nw=1:nk=1", str(video)], capture=True)
    return float(result.stdout.strip())


def probe_stream(video):
    """(width, height, fps) of the first video stream."""
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height,r_frame_rate",
                  "-of", "json", str(video)], capture=True)
    stream = json.loads(result.stdout)["streams"][0]
    numerator, _, denominator = stream["r_frame_rate"].partition("/")
    return stream["width"], stream["height"], float(numerator) / float(denominator or 1)


def ff_path(path):
    """Quote a path for use inside an ffmpeg filter argument.

    Forward slashes and an escaped colon, so a Windows drive letter does not read
    as a filter option separator. On POSIX there is no colon and this is a no-op.
    """
    return str(Path(path).resolve()).replace("\\", "/").replace(":", "\\:")


# --- cut timeline -----------------------------------------------------------
#
# A cut is a list of segments {start, end, speed} in SOURCE time. The output
# timeline is those segments concatenated, so mapping between the two is the
# arithmetic every stage of the pipeline depends on.

def atempo_chain(speed):
    """atempo only accepts 0.5-2.0 per instance; chain until we reach `speed`."""
    stages, remaining = [], speed
    while remaining > 2.0:
        stages.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        stages.append("atempo=0.5")
        remaining /= 0.5
    stages.append(f"atempo={remaining:.6f}")
    return ",".join(stages)


def audio_cut_graph(segments):
    """Filtergraph that trims and concatenates the kept audio into [ac]."""
    chunks, labels = [], []
    for index, segment in enumerate(segments):
        speed = segment.get("speed", 1.0)
        chain = (f"[0:a]atrim=start={segment['start']}:end={segment['end']},"
                 f"asetpts=PTS-STARTPTS")
        if speed != 1.0:
            chain += f",{atempo_chain(speed)}"
        chunks.append(f"{chain}[a{index}]")
        labels.append(f"[a{index}]")
    chunks.append(f"{''.join(labels)}concat=n={len(segments)}:v=0:a=1[ac]")
    return ";".join(chunks)


def source_to_output(timestamp, segments):
    """Map a source timestamp onto the cut timeline.

    Returns None if the timestamp falls inside a removed gap.
    """
    elapsed = 0.0
    for segment in segments:
        speed = segment.get("speed", 1.0)
        span = (segment["end"] - segment["start"]) / speed
        if segment["start"] <= timestamp <= segment["end"]:
            return elapsed + (timestamp - segment["start"]) / speed
        elapsed += span
    return None


def output_duration(segments):
    """Length of the cut timeline in seconds."""
    return sum((s["end"] - s["start"]) / s.get("speed", 1.0) for s in segments)
