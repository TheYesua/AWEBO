# Ejecuta toda la verificación del proyecto de una vez, en Windows.
#
#     .\verificar.ps1
#
# Es el equivalente local de .github/workflows/verificar.yml. No duplica
# lógica: los dos se limitan a invocar los mismos tests. Si aquí y allí llegan
# a decir cosas distintas, el que manda es el workflow, porque es el que corre
# siempre.
#
# POR QUÉ EXISTE
# El contenedor `api` es python:3.12-slim y no lleva Node, así que los tests de
# JavaScript no entran en `pytest` y se ejecutaban solo cuando alguien se
# acordaba. En agosto de 2026 se colaron tres fallos que la batería sí
# detectaba. Un solo comando quita la excusa.

$ErrorActionPreference = 'Continue'
$fallos = @()

# Dónde está este script. Tres formas porque ninguna funciona en todos los
# contextos; ver el comentario equivalente en respaldar.ps1, donde
# $PSScriptRoot vacío dio un error que no señalaba a su causa.
$raiz = $PSScriptRoot
if (-not $raiz) { $raiz = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $raiz) { $raiz = (Get-Location).Path }

function Bloque($titulo) {
    Write-Host ""
    Write-Host "=== $titulo ===" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
Bloque "Python (dentro del contenedor api)"
docker compose exec -T api pytest -q
if ($LASTEXITCODE -ne 0) { $fallos += "pytest" }

# ---------------------------------------------------------------------------
Bloque "JavaScript"
# Node en un contenedor efímero: no hace falta tenerlo instalado en Windows, y
# se prefiere a añadirlo a la imagen del proyecto, que es de producción.
$rutaApi = (Resolve-Path (Join-Path $raiz "api")).Path
foreach ($test in @('cobertura', 'lectura', 'llamadas', 'traducibles')) {
    Write-Host "--- $test.test.js"
    docker run --rm -v "${rutaApi}:/app" -w /app node:22-alpine node "tests/js/$test.test.js"
    if ($LASTEXITCODE -ne 0) { $fallos += "js/$test" }
}

# ---------------------------------------------------------------------------
Bloque "Catálogos de traducción compilados y al día"
# `pybabel compile` no falla si un .po cambió y no se recompiló: simplemente
# deja el .mo viejo, y la interfaz sale en castellano sin dar ningún error.
docker compose exec -T api pybabel compile -d app/translations
if ($LASTEXITCODE -ne 0) { $fallos += "pybabel compile" }

# ---------------------------------------------------------------------------
Write-Host ""
if ($fallos.Count -eq 0) {
    Write-Host "TODO VERDE" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FALLAN: $($fallos -join ', ')" -ForegroundColor Red
    exit 1
}
