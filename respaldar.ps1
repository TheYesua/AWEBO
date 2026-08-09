<#
.SYNOPSIS
    Copia de seguridad de la base de datos de AWEBO, verificada restaurándola.

.DESCRIPTION
    Vuelca la base de datos con pg_dump, la restaura en una base de usar y
    tirar y compara los recuentos de todas las tablas. Si no cuadran, avisa en
    ese momento.

    POR QUÉ SE VERIFICA
    Un backup que nadie ha restaurado no es un backup: es un fichero. Es la
    misma regla que el proyecto aplica a los tests —no valen hasta haberlos
    visto fallar— llevada a los datos. Un pg_dump que termina con código 0
    puede haber escrito un fichero truncado si se llenó el disco, y eso no se
    descubre hasta que hace falta. Se comprobó que la comparación detecta tanto
    un volcado truncado como uno de cero bytes.

    DÓNDE SE GUARDAN
    Fuera del árbol del repositorio, a propósito: contienen correos, nombres,
    centros educativos y hashes de contraseña. No deben acabar en git —ni en el
    repositorio público ni en el privado— porque git conserva todas las
    versiones para siempre y un repositorio privado sigue siendo un tercero.

.PARAMETER Destino
    Carpeta donde se guardan los volcados. Por defecto, una carpeta hermana del
    proyecto, que queda fuera de git por construcción.

.PARAMETER Conservar
    Cuántos volcados mantener. Los más antiguos se borran.

.PARAMETER SinVerificar
    Salta la restauración de comprobación. Más rápido, y renuncia a lo único
    que distingue este script de un pg_dump a pelo. Para cuando solo quieres
    una copia rápida antes de tocar algo.

.EXAMPLE
    .\respaldar.ps1
    Copia verificada en ..\AWEBO_backups, conservando las 7 últimas.

.EXAMPLE
    .\respaldar.ps1 -Destino D:\copias -Conservar 30
#>
[CmdletBinding()]
param(
    # Vacío a propósito: el valor real se calcula abajo, cuando ya se sabe
    # dónde está el script. Ponerlo aquí con $PSScriptRoot falla —esa variable
    # llega vacía a los valores por defecto de param() en Windows PowerShell
    # 5.1— y el error que da, «Cannot bind argument to parameter 'Path'
    # because it is an empty string», no señala en absoluto a la causa.
    [string]$Destino,
    [int]$Conservar = 7,
    [switch]$SinVerificar
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Dónde está este script. Tres formas de averiguarlo porque ninguna funciona
# en todos los casos: $PSScriptRoot no está disponible en algunos contextos,
# $MyInvocation cambia según cómo se invoque, y si fallan las dos hay que
# asumir que se está ejecutando desde la carpeta del proyecto.
# ---------------------------------------------------------------------------
$raiz = $PSScriptRoot
if (-not $raiz) { $raiz = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $raiz) { $raiz = (Get-Location).Path }

if (-not (Test-Path (Join-Path $raiz 'docker-compose.yml'))) {
    throw "No encuentro docker-compose.yml en '$raiz'. Ejecuta el script desde la carpeta del proyecto."
}

if (-not $Destino) {
    $Destino = Join-Path (Split-Path $raiz -Parent) 'AWEBO_backups'
}

function Paso($texto) { Write-Host "`n=== $texto ===" -ForegroundColor Cyan }
function Bien($texto) { Write-Host "  $texto" -ForegroundColor Green }
function Mal($texto)  { Write-Host "  $texto" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Credenciales: del .env, nunca escritas aquí ni mostradas por pantalla.
# ---------------------------------------------------------------------------
$env_ = Join-Path $raiz '.env'
if (-not (Test-Path $env_)) { throw "No existe $env_. Cópialo de .env.example." }

$valores = @{}
Get-Content $env_ | Where-Object { $_ -match '^\s*[A-Z_]+\s*=' } | ForEach-Object {
    $partes = $_ -split '=', 2
    $valores[$partes[0].Trim()] = $partes[1].Trim()
}
$usuario = $valores['POSTGRES_USER']
$base    = $valores['POSTGRES_DB']
if (-not $usuario -or -not $base) { throw "Faltan POSTGRES_USER o POSTGRES_DB en .env" }

# ---------------------------------------------------------------------------
Paso "Comprobaciones previas"
docker compose exec -T postgres pg_isready -U $usuario 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "postgres no responde. Arranca el stack con: docker compose up -d"
}
Bien "postgres responde"

New-Item -ItemType Directory -Force -Path $Destino | Out-Null
Bien "destino: $Destino"

# ---------------------------------------------------------------------------
Paso "Volcado"
$marca   = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$nombre  = "awebo_$marca.dump"
$enTmp   = "/tmp/$nombre"

# pg_dump escribe DENTRO del contenedor y luego se copia el fichero. Podría
# parecer más simple redirigir la salida estándar al fichero del host, pero
# PowerShell no tiene un modo binario limpio para eso: `>` y `Out-File`
# reinterpretan la codificación y corrompen el volcado, y el resultado es un
# fichero que parece correcto y no restaura. Con `docker compose cp` los bytes
# viajan intactos.
docker compose exec -T postgres pg_dump -Fc -U $usuario -d $base -f $enTmp
if ($LASTEXITCODE -ne 0) { throw "pg_dump ha fallado" }

$rutaFinal = Join-Path $Destino $nombre
docker compose cp "postgres:$enTmp" $rutaFinal
docker compose exec -T postgres rm -f $enTmp | Out-Null

if (-not (Test-Path $rutaFinal)) { throw "El volcado no ha llegado al host" }
$tamano = (Get-Item $rutaFinal).Length
if ($tamano -lt 1024) { throw "El volcado son solo $tamano bytes: algo ha ido mal" }
Bien ("volcado: {0} ({1:N0} KB)" -f $nombre, ($tamano / 1KB))

# ---------------------------------------------------------------------------
if (-not $SinVerificar) {
    Paso "Verificación: restaurar y comparar"
    $comprobacion = 'awebo_verificacion'

    function Consulta($db, $sql) {
        (docker compose exec -T postgres psql -qAt -U $usuario -d $db -c $sql) -join ''
    }

    # La lista de tablas se pregunta a la base de datos, no se escribe aquí:
    # así una tabla nueva entra en la comprobación sola. Escribirla a mano
    # significaría que la tabla que se añada mañana no se verifica y nadie se
    # entera.
    $consultaTablas = "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    $tablas = @(docker compose exec -T postgres psql -qAt -U $usuario -d $base -c $consultaTablas |
                Where-Object { $_ -and $_.Trim() } |
                ForEach-Object { $_.Trim() })
    if ($tablas.Count -eq 0) { throw "No he podido listar las tablas de '$base'" }

    Bien "$($tablas.Count) tablas que comprobar"

    docker compose exec -T postgres psql -qAt -U $usuario -d postgres `
        -c "DROP DATABASE IF EXISTS $comprobacion" | Out-Null
    docker compose exec -T postgres psql -qAt -U $usuario -d postgres `
        -c "CREATE DATABASE $comprobacion" | Out-Null

    docker compose cp $rutaFinal "postgres:$enTmp"
    # pg_restore devuelve código distinto de cero por avisos inofensivos
    # (dueños que no existen, extensiones ya creadas), así que su código no
    # sirve de veredicto. El veredicto son los recuentos.
    docker compose exec -T postgres pg_restore -U $usuario -d $comprobacion $enTmp 2>&1 | Out-Null

    $descuadres = @()
    foreach ($t in $tablas) {
        $a = Consulta $base "SELECT count(*) FROM ""$t"""
        $b = Consulta $comprobacion "SELECT count(*) FROM ""$t"""
        if ($a -ne $b) {
            $descuadres += "$t (original $a, restaurado $b)"
            Mal ("{0,-28} {1,7} -> {2,7}  DISTINTO" -f $t, $a, $b)
        } else {
            Write-Host ("  {0,-28} {1,7} filas" -f $t, $a)
        }
    }

    docker compose exec -T postgres psql -qAt -U $usuario -d postgres `
        -c "DROP DATABASE IF EXISTS $comprobacion" | Out-Null
    docker compose exec -T postgres rm -f $enTmp | Out-Null

    if ($descuadres.Count -gt 0) {
        Mal "LA COPIA NO ES FIABLE. Descuadran: $($descuadres -join '; ')"
        Write-Host "  El fichero se conserva en $rutaFinal para que puedas mirarlo." -ForegroundColor Yellow
        exit 1
    }
    Bien "restauración verificada: todos los recuentos coinciden"
}

# ---------------------------------------------------------------------------
Paso "Rotación"
$copias = Get-ChildItem $Destino -Filter 'awebo_*.dump' | Sort-Object Name -Descending
if ($copias.Count -gt $Conservar) {
    $copias | Select-Object -Skip $Conservar | ForEach-Object {
        Remove-Item $_.FullName
        Write-Host "  borrada la antigua $($_.Name)"
    }
}
Bien "$([Math]::Min($copias.Count, $Conservar)) copias en $Destino"

Write-Host "`nCOPIA CORRECTA" -ForegroundColor Green
Write-Host "Para restaurarla, mira la sección «Restaurar una copia» del README." -ForegroundColor DarkGray
