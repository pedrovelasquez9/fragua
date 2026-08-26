#!/usr/bin/env bash
# Instala la skill para Claude Code y/o OpenCode, y prepara sus dependencias.
#
#   ./install.sh                    # ambos, global
#   ./install.sh --target claude    # solo Claude Code
#   ./install.sh --target opencode  # solo OpenCode
#   ./install.sh --project          # en la carpeta actual, no global
#   ./install.sh --model ggml-medium
#   ./install.sh --version v1.12.0  # una versión concreta, para volver atrás
#
# La carpeta de destino se llama SIEMPRE 'fragua': OpenCode valida que el
# nombre coincida con el campo 'name' del frontmatter y rechaza la skill si no.
set -euo pipefail

TARGET="both"
PROJECT=0
VERSION=""
MODEL="ggml-large-v3-turbo"
SKILL_NAME="fragua"

while [ $# -gt 0 ]; do
    case "$1" in
        --target)  TARGET="$2"; shift 2 ;;
        --project) PROJECT=1; shift ;;
        --model)   MODEL="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "opción desconocida: $1"; exit 1 ;;
    esac
done

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SOURCE/skills/fragua/SKILL.md" ] || { echo "no encuentro skills/fragua/SKILL.md — ejecútalo desde la carpeta de Fragua"; exit 1; }

# Instalar una versión concreta es sacar ese tag antes de copiar nada. Se exige
# el árbol limpio: copiar cambios locales bajo una etiqueta que no los tiene
# dejaría al usuario creyendo que está en la versión que pidió.
if [ -n "$VERSION" ]; then
    command -v git >/dev/null 2>&1 || { echo "--version necesita git"; exit 1; }
    git -C "$SOURCE" rev-parse "$VERSION" >/dev/null 2>&1 || {
        echo "no existe la versión '$VERSION'. Disponibles:"
        git -C "$SOURCE" tag | sort -V | tr '\n' ' '; echo; exit 1; }
    [ -z "$(git -C "$SOURCE" status --porcelain)" ] || {
        echo "hay cambios sin guardar en el repo: guárdalos antes de cambiar de versión"; exit 1; }
    git -C "$SOURCE" checkout -q "$VERSION"
    echo "instalando $VERSION"
fi

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
            vendor|__pycache__|.git|cards|skills|.claude-plugin) continue ;;
        esac
        cp -R "$item" "$destination/"
    done
    # Claude Code carga las skills desde skills/<nombre>/, pero OpenCode y la
    # instalación suelta esperan SKILL.md en la raíz del destino. Aplanamos la
    # skill principal; assets y setup son comandos de Claude y no aplican aquí.
    cp "$SOURCE/skills/fragua/SKILL.md" "$destination/SKILL.md"

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
