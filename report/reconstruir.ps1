$ErrorActionPreference = 'Stop'
$edgeRoot = Split-Path -Parent $PSScriptRoot

Push-Location -LiteralPath $edgeRoot
try {
    python results/analizar.py results/raw/benchmark-v1 results/processed/benchmark report --continuation results/raw/benchmark-v2
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la verificación de la evidencia ($LASTEXITCODE)."
    }
    $sessions = @(Get-ChildItem results/raw -Directory | Where-Object {
        $_.Name -match '^extension-eva02-(postgresql(?:-diagnostico)?|mongodb)-v\d+$'
    } | ForEach-Object { $_.FullName })
    python results/analizar_extension.py @sessions --out results/processed/extension-eva02 --latex report/extension_resultados.tex
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la reconstrucción de la matriz de la ampliación ($LASTEXITCODE)."
    }
} finally {
    Pop-Location
}

Push-Location -LiteralPath $PSScriptRoot
try {
    tectonic --untrusted --keep-logs articulo.tex
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la compilación del artículo ($LASTEXITCODE)."
    }
} finally {
    Pop-Location
}
