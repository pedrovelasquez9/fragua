# Instala la skill para Claude Code y/o OpenCode, y prepara sus dependencias.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   ...install.ps1 -Target claude          # solo Claude Code
#   ...install.ps1 -Target opencode        # solo OpenCode
#   ...install.ps1 -Project               # en la carpeta actual, no global
#   ...install.ps1 -Model ggml-medium      # modelo más pequeño y rápido
#   ...install.ps1 -Version v1.12.0        # una versión concreta, para volver atrás
#
# La carpeta de destino se llama SIEMPRE 'fragua': OpenCode valida que el
# nombre coincida con el campo 'name' del frontmatter y rechaza la skill si no.

param(
    [ValidateSet("both", "claude", "opencode")] [string]$Target = "both",
    [switch]$Project,
    [string]$Model = "ggml-large-v3-turbo",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$SkillName = "fragua"

# Instalar una versión concreta es sacar ese tag antes de copiar nada. Se exige
# el árbol limpio: copiar cambios locales bajo una etiqueta que no los tiene
# dejaría al usuario creyendo que está en la versión que pidió.
if ($Version) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host "-Version necesita git"; exit 1 }
    $ErrorActionPreference = "Continue"
    git -C $source rev-parse $Version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "no existe la versión '$Version'. Disponibles:"
        Write-Host ((git -C $source tag) -join " ")
        exit 1
    }
    if (git -C $source status --porcelain) {
        Write-Host "hay cambios sin guardar en el repo: guárdalos antes de cambiar de versión"
        exit 1
    }
    git -C $source checkout -q $Version
    $ErrorActionPreference = "Stop"
    Write-Host "instalando $Version"
}

if (-not (Test-Path (Join-Path $source "skills\$SkillName\SKILL.md"))) {
    throw "no encuentro skills\$SkillName\SKILL.md — ejecuta este script desde la carpeta de Fragua"
}

# --- destinos ---------------------------------------------------------------
$targets = @()
if ($Project) {
    if ($Target -in @("both", "claude"))   { $targets += Join-Path (Get-Location) ".claude\skills\$SkillName" }
    if ($Target -in @("both", "opencode")) { $targets += Join-Path (Get-Location) ".opencode\skills\$SkillName" }
} else {
    if ($Target -in @("both", "claude"))   { $targets += Join-Path $HOME ".claude\skills\$SkillName" }
    if ($Target -in @("both", "opencode")) { $targets += Join-Path $HOME ".config\opencode\skills\$SkillName" }
}

# --- copia ------------------------------------------------------------------
# vendor/ son 1.5 GB regenerables: no se copia, se instala una vez en el primero
# y los demás destinos lo comparten con un enlace.
$skip = @("vendor", "__pycache__", ".git", "cards", "skills", ".claude-plugin")
$primary = $null

foreach ($destination in $targets) {
    Write-Host "instalando en $destination"
    New-Item -ItemType Directory -Force -Path $destination | Out-Null

    Get-ChildItem -Path $source -Force | Where-Object { $_.Name -notin $skip } | ForEach-Object {
        Copy-Item $_.FullName -Destination $destination -Recurse -Force
    }
    # Claude Code carga las skills desde skills\<nombre>\, pero OpenCode y la
    # instalación suelta esperan SKILL.md en la raíz del destino. Aplanamos la
    # skill principal; assets y setup son comandos de Claude y no aplican aquí.
    Copy-Item (Join-Path $source "skills\$SkillName\SKILL.md") `
              -Destination (Join-Path $destination "SKILL.md") -Force

    if ($null -eq $primary) {
        $primary = $destination
    } else {
        $link = Join-Path $destination "vendor"
        if (-not (Test-Path $link)) {
            New-Item -ItemType Junction -Path $link -Target (Join-Path $primary "vendor") | Out-Null
            Write-Host "  vendor/ enlazado a la primera instalación"
        }
    }
}

# --- dependencias -----------------------------------------------------------
Write-Host ""
Write-Host "preparando dependencias (whisper.cpp, modelo y fuentes)..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $primary "scripts\setup.ps1") -Model $Model

# --- comprobación -----------------------------------------------------------
Write-Host ""
Write-Host "verificando la instalación..."
. (Join-Path $primary "scripts\lib.ps1")
$python = Resolve-Python
Push-Location $primary
try { Invoke-Tool $python @("test_pipeline.py") } finally { Pop-Location }

Write-Host ""
Write-Host "Listo. Abre Claude Code u OpenCode y escribe algo como:" -ForegroundColor Green
Write-Host '   edita este video para tiktok: C:\ruta\a\tu\video.mp4'
