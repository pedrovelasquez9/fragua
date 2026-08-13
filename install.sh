#!/usr/bin/env bash
# Instala la skill para Claude Code y/o OpenCode, y prepara sus dependencias.
#
#   ./install.sh                    # ambos, global
#   ./install.sh --target claude    # solo Claude Code
#   ./install.sh --target opencode  # solo OpenCode
#   ./install.sh --project          # en la carpeta actual, no global
#   ./install.sh --model ggml-medium
#
# La carpeta de destino se llama SIEMPRE 'fragua': OpenCode valida que el
# nombre coincida con el campo 'name' del frontmatter y rechaza la skill si no.
set -euo pipefail

TARGET="both"
PROJECT=0
MODEL="ggml-large-v3-turbo"
SKILL_NAME="fragua"

while [ $# -gt 0 ]; do
    case "$1" in
        --target)  TARGET="$2"; shift 2 ;;
        --project) PROJECT=1; shift ;;
        --model)   MODEL="$2"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "opción desconocida: $1"; exit 1 ;;
    esac
done

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SOURCE/SKILL.md" ] || { echo "no encuentro SKILL.md — ejecútalo desde la carpeta de la skill"; exit 1; }

# --- destinos ---------------------------------------------------------------
targets=()
if [ "$PROJECT" -eq 1 ]; then
    [ "$TARGET" = "both" ] || [ "$TARGET" = "claude" ]   && targets+=("$PWD/.claude/skills/$SKILL_NAME")
    [ "$TARGET" = "both" ] || [ "$TARGET" = "opencode" ] && targets+=("$PWD/.opencode/skills/$SKILL_NAME")
else
    [ "$TARGET" = "both" ] || [ "$TARGET" = "claude" ]   && targets+=("$HOME/.claude/skills/$SKILL_NAME")
    [ "$TARGET" = "both" ] || [ "$TARGET" = "opencode" ] && targets+=("$HOME/.config/opencode/skills/$SKILL_NAME")
fi

# --- copia ------------------------------------------------------------------
# vendor/ son 1.5 GB regenerables: se instala una vez en el primer destino y los
# demás lo comparten con un symlink.
primary=""
for destination in "${targets[@]}"; do
    echo "instalando en $destination"
    mkdir -p "$destination"
    for item in "$SOURCE"/* "$SOURCE"/.[!.]*; do
        [ -e "$item" ] || continue
        case "$(basename "$item")" in
            vendor|__pycache__|.git|cards) continue ;;
        esac
        cp -R "$item" "$destination/"
    done

    if [ -z "$primary" ]; then
        primary="$destination"
    elif [ ! -e "$destination/vendor" ]; then
        ln -s "$primary/vendor" "$destination/vendor"
        echo "  vendor/ enlazado a la primera instalación"
    fi
done

# --- dependencias -----------------------------------------------------------
echo
echo "preparando dependencias (whisper.cpp, modelo y fuentes)..."
chmod +x "$primary/scripts/setup.sh"
"$primary/scripts/setup.sh" "$MODEL"

# --- comprobación -----------------------------------------------------------
echo
echo "verificando la instalación..."
(cd "$primary" && python3 test_pipeline.py)

echo
echo "Listo. Abre Claude Code u OpenCode y escribe algo como:"
echo "   edita este video para tiktok: ~/videos/mi-video.mp4"
