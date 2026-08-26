#!/usr/bin/env bash
# Fetch whisper.cpp, a model and the fonts into vendor/. Run once per machine.
#   ./scripts/setup.sh [model-name]
#
# POSIX equivalent of setup.ps1. Unlike Windows, whisper.cpp ships no prebuilt
# binary for Linux/macOS, so this builds it — you need git, cmake and a compiler.
set -euo pipefail

MODEL="${1:-ggml-large-v3-turbo}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/vendor"
FONTS="$VENDOR/fonts"
MODELS="$VENDOR/models"

need() { command -v "$1" >/dev/null 2>&1 || { echo "falta '$1' — instálalo y reintenta"; exit 1; }; }

# --- requisitos previos -----------------------------------------------------
# Se instalan solos con el gestor de paquetes del sistema.
pkg_install() {
    if   command -v brew    >/dev/null 2>&1; then brew install "$@"
    elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y "$@"
    elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y "$@"
    elif command -v pacman  >/dev/null 2>&1; then sudo pacman -S --noconfirm "$@"
    elif command -v zypper  >/dev/null 2>&1; then sudo zypper install -y "$@"
    else return 1
    fi
}

ensure() {  # ensure <comando> <paquete> <etiqueta>
    command -v "$1" >/dev/null 2>&1 && return 0
    echo "instalando $3..."
    pkg_install "$2" || { echo "falta $3 y no reconozco tu gestor de paquetes. Instálalo a mano."; exit 1; }
    command -v "$1" >/dev/null 2>&1 || { echo "$3 se instaló pero no aparece en el PATH"; exit 1; }
}

ensure ffmpeg  ffmpeg  "ffmpeg"
ensure curl    curl    "curl"
ensure python3 python3 "Python 3"

mkdir -p "$FONTS" "$MODELS"

# --- Pillow -----------------------------------------------------------------
# Pillow rasterises the cards. ASS can only put a box behind a line of text.
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "instalando Pillow..."
    python3 -m pip install --quiet pillow
fi

# --- whisper.cpp ------------------------------------------------------------
if find "$VENDOR" -name whisper-cli -o -name main 2>/dev/null | grep -q .; then
    echo "binario ya presente"
else
    need git
    need cmake
    echo "compilando whisper.cpp (unos minutos)..."
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$work/src"
    cmake -B "$work/build" -S "$work/src" -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$work/build" -j --config Release >/dev/null
    found="$(find "$work/build" -name whisper-cli -type f | head -1)"
    [ -n "$found" ] || { echo "la compilación no produjo whisper-cli"; exit 1; }
    cp "$found" "$VENDOR/"
    chmod +x "$VENDOR/whisper-cli"
fi

# --- model ------------------------------------------------------------------
if [ -f "$MODELS/$MODEL.bin" ]; then
    echo "modelo ya presente: $MODEL"
else
    echo "descargando $MODEL (puede tardar, ~1.6 GB para large-v3-turbo)..."
    curl -fL --progress-bar -o "$MODELS/$MODEL.bin" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL.bin"
fi

# --- fonts (OFL, redistributable) -------------------------------------------
# Roboto ships variable-only, y libass NO saca de ahí la instancia Black: pide
# "Roboto Black" y te da Arial (medido con libass 0.17.5, ni con bold=1 cambia).
# Por eso los subtítulos usan "Poppins ExtraBold", que va vendorizada estática.
# Roboto se sigue descargando porque las cards la usan por fichero, no por nombre.
fetch_font() {
    [ -f "$FONTS/$1" ] && return 0
    echo "descargando $1..."
    curl -fL --progress-bar -o "$FONTS/$1" "$2"
}
GF="https://github.com/google/fonts/raw/main/ofl"
RAW="https://raw.githubusercontent.com/google/fonts/main/ofl"
fetch_font "Roboto-Variable.ttf"   "$GF/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"
fetch_font "Anton-Regular.ttf"     "$GF/anton/Anton-Regular.ttf"
fetch_font "Poppins-ExtraBold.ttf" "$GF/poppins/Poppins-ExtraBold.ttf"
fetch_font "OFL-Roboto.txt"        "$RAW/roboto/OFL.txt"
fetch_font "OFL-Anton.txt"         "$RAW/anton/OFL.txt"
fetch_font "OFL-Poppins.txt"       "$RAW/poppins/OFL.txt"

# --- cards animadas (opcional) ----------------------------------------------
# Remotion arrastra Node y su propio Chrome, así que no se instala solo. Si Node
# ya está en la máquina, se preparan las dependencias; si no, la edición sigue
# con las cards quietas.
if command -v npm >/dev/null 2>&1; then
    echo "preparando cards animadas (remotion)..."
    if (cd "$ROOT/remotion" && npm install --silent --no-fund --no-audit); then
        echo "ok  cards animadas disponibles"
    else
        echo "aviso: npm install falló en remotion/; las cards seguirán quietas"
    fi
else
    echo "sin Node: las cards saldrán quietas. Para animarlas, instala Node y"
    echo "vuelve a lanzar este setup (brew install node / apt install nodejs npm)."
fi

# --- verify -----------------------------------------------------------------
cli="$(find "$VENDOR" -name whisper-cli -o -name main | head -1)"
[ -n "$cli" ] || { echo "no encuentro el ejecutable en $VENDOR"; exit 1; }
for f in Roboto-Variable.ttf Anton-Regular.ttf Poppins-ExtraBold.ttf; do
    [ -f "$FONTS/$f" ] || { echo "falta la fuente $f"; exit 1; }
done

echo "listo: $cli"
echo "       $MODELS/$MODEL.bin"
echo "       $FONTS (Roboto, Anton, Poppins)"
