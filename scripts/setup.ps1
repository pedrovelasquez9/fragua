# Fetch whisper.cpp (Windows x64 build) and a model into vendor/. Run once.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   ...\setup.ps1 -Model ggml-medium      # smaller/faster alternative

param([string]$Model = "ggml-large-v3-turbo")

$ErrorActionPreference = "Stop"
$vendor = Join-Path (Split-Path $PSScriptRoot -Parent) "vendor"
$models = Join-Path $vendor "models"
New-Item -ItemType Directory -Force -Path $models | Out-Null

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg no está en el PATH. Instálalo con: winget install Gyan.FFmpeg"
}

# Pillow rasterises the cards. ASS can only put a box behind a line of text.
python -c "import PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    "instalando Pillow..."
    python -m pip install --quiet pillow
    python -c "import PIL" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "no pude instalar Pillow" }
}

# Same preference order as transcribe.py, so both report the same executable.
function Find-Whisper {
    foreach ($name in "whisper-cli.exe", "main.exe") {
        $hit = Get-ChildItem -Path $vendor -Recurse -Filter $name -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($hit) { return $hit }
    }
}

# --- binary -----------------------------------------------------------------
$existing = Find-Whisper
if ($existing) {
    "binario ya presente: $($existing.FullName)"
} else {
    "buscando la última release de whisper.cpp..."
    $release = Invoke-RestMethod "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest" `
        -Headers @{ "User-Agent" = "fragua" }
    $asset = $release.assets | Where-Object { $_.name -match "bin-x64" } | Select-Object -First 1
    if (-not $asset) { throw "no encontré un binario x64 en la release $($release.tag_name)" }

    $zip = Join-Path $env:TEMP $asset.name
    "descargando $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)..."
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $vendor -Force
    Remove-Item $zip
}

# --- model ------------------------------------------------------------------
$bin = Join-Path $models "$Model.bin"
if (Test-Path $bin) {
    "modelo ya presente: $bin"
} else {
    $url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$Model.bin"
    "descargando $Model (puede tardar, ~1.6 GB para large-v3-turbo)..."
    Invoke-WebRequest $url -OutFile $bin
}

# --- fonts (OFL, redistributable) -------------------------------------------
# Poppins ExtraBold for captions, Anton for on-screen hooks. Windows' built-in
# faces read as generic; these are what short-form editors actually use.
$fonts = Join-Path $vendor "fonts"
New-Item -ItemType Directory -Force -Path $fonts | Out-Null
# Roboto ships variable-only. libass resolves named instances, so ask for the
# family name "Roboto Black" in presets.json — it will NOT synthesise bold.
$want = @{
    "Roboto-Variable.ttf"   = "https://github.com/google/fonts/raw/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"
    "Anton-Regular.ttf"     = "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
    "Poppins-ExtraBold.ttf" = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-ExtraBold.ttf"
    "OFL-Roboto.txt"        = "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/OFL.txt"
    "OFL-Anton.txt"         = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/OFL.txt"
    "OFL-Poppins.txt"       = "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/OFL.txt"
}
foreach ($name in $want.Keys) {
    $dest = Join-Path $fonts $name
    if (Test-Path $dest) { continue }
    "descargando $name..."
    Invoke-WebRequest $want[$name] -OutFile $dest
}

# --- verify -----------------------------------------------------------------
$cli = Find-Whisper
if (-not $cli) { throw "la descarga terminó pero no encuentro el ejecutable en $vendor" }
$missing = @("Roboto-Variable.ttf", "Anton-Regular.ttf", "Poppins-ExtraBold.ttf") |
           Where-Object { -not (Test-Path (Join-Path $fonts $_)) }
if ($missing) { throw "faltan fuentes: $($missing -join ', ')" }

"listo: $($cli.FullName)"
"       $bin"
"       $fonts (Anton, Poppins ExtraBold)"
