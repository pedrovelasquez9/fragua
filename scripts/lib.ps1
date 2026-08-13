# Helpers compartidos por setup.ps1 e install.ps1. Se cargan con dot-sourcing.

function Update-SessionPath {
    <# winget no refresca el PATH del proceso en curso. #>
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Invoke-Tool {
    <# Ejecuta una invocación de varias palabras con argumentos extra.

    Existe para no trocear arrays en cada llamada: en PowerShell, @('x')[1..0]
    no da un array vacío sino un rango invertido con nulos, y eso rompía la
    detección para invocaciones de una sola palabra como @('python').
    #>
    param([string[]]$Invocation, [string[]]$Arguments)
    $rest = if ($Invocation.Count -gt 1) { $Invocation[1..($Invocation.Count - 1)] } else { @() }
    # El splat tiene que ser de una VARIABLE. Con un array en línea, PowerShell
    # puede fusionar un elemento que empieza por guion con el siguiente:
    # @('-3') + @('--version') acaba llegando como "3--version".
    $all = @($rest) + @($Arguments)
    & $Invocation[0] @all
}

function Test-Interpreter {
    <# ¿Esta invocación arranca un Python 3 de verdad?

    No basta con Get-Command: Windows trae alias de ejecución de 0 bytes en
    WindowsApps para python, python3 y py que existen SIEMPRE, aunque no haya
    Python instalado. Al ejecutarlos abren el Microsoft Store y no hacen nada,
    así que la única comprobación fiable es lanzarlos y mirar qué contestan.
    #>
    param([string[]]$Invocation)
    try {
        $out = Invoke-Tool $Invocation @("--version") 2>&1 | Out-String
    } catch { return $false }
    return ($LASTEXITCODE -eq 0) -and ($out -match "Python 3\.")
}

function Resolve-Python {
    <# Devuelve la invocación que funciona, p.ej. @("py","-3") o @("python").
       Instala Python con winget si no hay ninguna. #>
    param([switch]$NoInstall)

    $candidates = @(, @("py", "-3")), @(, @("python")), @(, @("python3"))
    foreach ($candidate in $candidates) {
        if (Test-Interpreter $candidate[0]) { return $candidate[0] }
    }

    if ($NoInstall) { return $null }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "no hay un Python 3 utilizable y no encuentro winget. Instálalo desde python.org y reintenta."
    }
    "instalando Python..."
    winget install --id Python.Python.3.12 --silent `
                   --accept-package-agreements --accept-source-agreements | Out-Null
    Update-SessionPath

    # El alias de WindowsApps puede seguir teniendo prioridad en el PATH sobre la
    # instalación real, así que la buscamos y la anteponemos.
    $installed = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*" `
                     -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
                 Where-Object { $_.Length -gt 0 } | Select-Object -First 1
    if ($installed) { $env:Path = "$($installed.DirectoryName);$env:Path" }

    foreach ($candidate in $candidates) {
        if (Test-Interpreter $candidate[0]) { return $candidate[0] }
    }
    throw "Python se instaló pero no arranca. Abre un terminal nuevo y reintenta."
}

function Install-Prerequisite {
    <# Instala una herramienta con winget si su comando no responde. #>
    param([string]$Command, [string]$TestArg, [string]$WingetId, [string]$Label)

    $works = $false
    try { & $Command $TestArg 2>&1 | Out-Null; $works = ($LASTEXITCODE -eq 0) } catch { }
    if ($works) { return }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "falta $Label y no encuentro winget. Instálalo a mano y reintenta."
    }
    "instalando $Label..."
    winget install --id $WingetId --silent `
                   --accept-package-agreements --accept-source-agreements | Out-Null
    Update-SessionPath

    try { & $Command $TestArg 2>&1 | Out-Null; $works = ($LASTEXITCODE -eq 0) } catch { }
    if (-not $works) { throw "$Label se instaló pero no responde. Abre un terminal nuevo y reintenta." }
}
