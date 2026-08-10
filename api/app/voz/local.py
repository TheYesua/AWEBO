"""Síntesis de voz local con aHoTTS (HiTZ / UPV-EHU).

POR QUÉ LOCAL Y NO UN PROVEEDOR DE NUBE
----------------------------------------
Dos motivos, y el segundo pesa más.

El barato: no hay coste por carácter, así que generar el audio de una SdA
entera deja de ser una decisión económica.

El importante: **el contenido de las situaciones no sale de la máquina**. Una
programación docente lleva dentro el perfil del aula, y el perfil del aula
describe a menores concretos —«dos alumnos con desfase curricular de dos
cursos», «una alumna recién incorporada que no habla castellano»—. Mandar eso
a un tercero para que lo lea en voz alta no compensa por ahorrarse trabajo.

POR QUÉ aHoTTS Y NO PIPER
--------------------------
Se intentó con Piper y no se puede, comprobado midiendo: los modelos de HiTZ
tienen entre 52 y 137 símbolos en su tabla de fonemas y Piper usa 256, el mapa
IPA de espeak-ng. La firma del ONNX coincide, el alfabeto no. El detalle
completo está en ``docs/VOCES.md``.

El motivo de fondo es que **el ONNX es solo el modelo acústico**: quien
convierte texto en fonemas es el binario ``tts``, con un diccionario
lingüístico distinto por lengua. Ese binario viene compilado en el repositorio
de aHoTTS junto a su propio ``libonnxruntime``, así que no hay que construir
C++ en el Dockerfile.

Cubre las cuatro lenguas de la interfaz con una sola fuente institucional, y es
Apache-2.0.

CÓMO SE LLAMA AL BINARIO
-------------------------
El texto va por la **entrada estándar**, no como argumento. No es un detalle
menor: los argumentos de un proceso son visibles para cualquiera que liste los
procesos de la máquina, y aquí el argumento sería el contenido de una situación
de aprendizaje.

El binario **escribe a un fichero**, no a la salida estándar, así que hay un
temporal inevitable. Se crea con permisos de solo su dueño y se borra en un
``finally``.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

from .proveedor import Audio, Locucion, VozError


logger = logging.getLogger("voz.local")


@dataclass(frozen=True)
class _Lengua:
    """Cómo hay que llamar al binario para una lengua concreta.

    Cada una tiene su frente lingüístico y no hay forma de unificarlo: gallego
    usa la base de datos de Cotovía —de ahí ``-HDicDB`` en vez de ``-HDic``— y
    catalán reutiliza los datos de espeak-ng. Se toma tal cual de
    ``synthesize.py`` del propio aHoTTS.
    """

    opcion_diccionario: str
    ruta_diccionario: str
    #: Castellano y euskera **exigen ISO-8859-1**; los otros dos van en UTF-8.
    #: Es del binario, no una elección nuestra.
    codificacion: str


LENGUAS = {
    "es": _Lengua("-HDic", "dicts/es/es_dicc", "iso-8859-1"),
    "eu": _Lengua("-HDic", "dicts/eu/eu_dicc", "iso-8859-1"),
    "ca": _Lengua("-HDic", "dicts/ca/espeak-ng-data", "utf-8"),
    "gl": _Lengua("-HDicDB", "dicts/gl/cotovia", "utf-8"),
}

#: Reemplazos de caracteres tipográficos. **La raya larga se cambia por una
#: coma, no por un guion**, y eso no es cosmético: ver abajo.
_TIPOGRAFICOS = str.maketrans({
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...",
    "•": ",", "·": ",",
    "→": " a ", "≤": " menor o igual que ", "≥": " mayor o igual que ",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ",
})

#: Un guion suelto entre espacios —o una raya larga, que es lo que escribe un
#: modelo de lenguaje— se convierte en coma.
#:
#: POR QUÉ, Y CÓMO SE DESCUBRIÓ
#: Al probar las cuatro lenguas, el catalán reventaba con
#: `std::invalid_argument: stoll` y dejaba un WAV de 44 bytes: la cabecera sin
#: una sola muestra. Aislando el texto frase a frase resultó que el disparador
#: era exactamente eso, un guion suelto: «Text - amb guio» mata el proceso y
#: «Text, amb coma» no. Solo le pasa al catalán, que es el único que usa
#: espeak-ng como frente lingüístico.
#:
#: Lo importante es que **mi primera versión provocaba el fallo en vez de
#: evitarlo**: traducía «—» por «-» para que cupiera en ISO-8859-1, y con eso
#: convertía un texto que funcionaba en uno que estrella el proceso. Se vio
#: porque la frase de prueba llevaba raya larga; con «Hola, qué tal» —el
#: ejemplo del README— no habría aparecido nunca.
#:
#: La coma además es lo correcto por significado: una raya larga es una pausa,
#: y un guion no.
_GUION_SUELTO = re.compile(r"(?<=\s)[-\u2010-\u2015](?=\s)|(?<=\s)[-\u2010-\u2015]$|^[-\u2010-\u2015](?=\s)")

#: Los guiones **dentro** de palabra se dejan intactos: `ikaskuntza-egoera` es
#: el término oficial del decreto vasco y se pronuncia bien. Comprobado.


def _adaptar(texto: str, codificacion: str) -> str:
    """Deja el texto en algo que el motor sepa decir y la codificación admita.

    Tres pasos, del menos destructivo al más:

    1. tipográficos por su equivalente, y guiones sueltos por coma;
    2. descomponer lo que quede —``NFKD``— para que «ﬁ» acabe siendo «fi»;
    3. tirar lo que siga sin caber, **avisando en el registro**.

    El tercer paso pierde información y por eso deja rastro: si empieza a
    aparecer a menudo, falta una entrada en las tablas de arriba.
    """
    adaptado = _GUION_SUELTO.sub(",", texto.translate(_TIPOGRAFICOS))
    try:
        adaptado.encode(codificacion)
        return adaptado
    except UnicodeEncodeError:
        pass

    descompuesto = unicodedata.normalize("NFKD", adaptado)
    limpio = descompuesto.encode(codificacion, errors="ignore").decode(codificacion)
    perdidos = len(descompuesto) - len(limpio)
    if perdidos:
        # Cuántos, no cuáles: el log no debe llevar el contenido de la SdA.
        logger.warning(
            "%d caracteres no representables en %s se han descartado del audio",
            perdidos, codificacion,
        )
    return limpio


def _raiz() -> Path:
    return Path(current_app.config.get("VOZ_AHOTTS_DIR", "/ahotts"))


def _comprobar_instalacion(idioma: str) -> tuple[Path, _Lengua, Path]:
    """Binario, parámetros de la lengua y carpeta de la voz.

    Se comprueba todo **antes** de lanzar el subproceso para poder decir qué
    falta. El binario, cuando no encuentra algo, se limita a no escribir el
    fichero de salida y termina con código cero: sin estas comprobaciones el
    síntoma sería «no hay audio» sin ninguna pista.
    """
    corto = (idioma or "es").split("-")[0].lower()
    lengua = LENGUAS.get(corto)
    if lengua is None:
        raise VozError(
            f"No hay voz para el idioma «{corto}». "
            f"Disponibles: {', '.join(sorted(LENGUAS))}."
        )

    raiz = _raiz()
    binario = raiz / "ahotts" / "tts"
    if not binario.is_file():
        raise VozError(
            f"No está el binario de síntesis en {binario}. "
            f"Clona hitz-zentroa/aHoTTS ahí. Ver docs/VOCES.md."
        )

    voz = raiz / "ahotts" / "voices" / corto
    if not (voz / "vits.onnx").is_file():
        raise VozError(
            f"Falta el modelo de «{corto}» en {voz / 'vits.onnx'}. "
            f"Ver docs/VOCES.md."
        )

    # `es_dicc` y `eu_dicc` **no son ficheros**: son un prefijo, y en el disco
    # están `es_dicc.dic`, `es_dicc_mx.dic`… Comprobar `.exists()` sobre el
    # prefijo daba «falta el diccionario» con el diccionario delante. Catalán y
    # gallego sí apuntan a un directorio de verdad.
    diccionario = raiz / "ahotts" / lengua.ruta_diccionario
    if not (diccionario.exists() or any(diccionario.parent.glob(diccionario.name + "*"))):
        raise VozError(
            f"Falta el diccionario lingüístico de «{corto}» en {diccionario}."
        )
    return binario, lengua, voz


class ProveedorLocal:
    nombre = "local"

    def sintetizar(self, locucion: Locucion) -> Audio:
        texto = locucion.texto.strip()
        if not texto:
            raise VozError("No hay texto que leer")

        binario, lengua, voz = _comprobar_instalacion(locucion.idioma)
        raiz = _raiz()

        entrada = _adaptar(texto, lengua.codificacion).encode(lengua.codificacion)

        # `libonnxruntime.so` viaja con el repositorio de aHoTTS y no está en
        # las rutas del sistema; sin esto el binario no arranca.
        entorno = dict(os.environ)
        entorno["LD_LIBRARY_PATH"] = f"{raiz}:{entorno.get('LD_LIBRARY_PATH', '')}"

        destino = Path(
            tempfile.mkstemp(prefix="awebo-voz-", suffix=".wav")[1]
        )
        try:
            proceso = subprocess.run(
                [str(binario), f"-Lang={locucion.idioma.split('-')[0].lower()}",
                 "-Method=Vits",
                 f"{lengua.opcion_diccionario}={raiz / 'ahotts' / lengua.ruta_diccionario}",
                 f"-voice_path={voz}", str(destino)],
                input=entrada, capture_output=True, env=entorno,
                cwd=str(raiz),
                timeout=int(current_app.config.get("VOZ_TIMEOUT", 60)),
            )
            if proceso.returncode != 0:
                logger.error(
                    "aHoTTS terminó con código %d: %s",
                    proceso.returncode,
                    proceso.stderr.decode("utf-8", "replace")[:200],
                )
                raise VozError("La síntesis de voz ha fallado")

            wav = destino.read_bytes()
        except subprocess.TimeoutExpired as exc:
            raise VozError("La síntesis de voz ha tardado demasiado") from exc
        except OSError as exc:
            logger.error("No se pudo ejecutar aHoTTS: %s", type(exc).__name__)
            raise VozError(f"Voz local: {type(exc).__name__}") from exc
        finally:
            # El temporal lleva dentro el contenido de una situación: se borra
            # pase lo que pase, también si la síntesis falló a medias.
            destino.unlink(missing_ok=True)

        if len(wav) <= 44:      # 44 bytes es la cabecera WAV sin una sola muestra
            raise VozError("La síntesis no produjo audio")

        datos = _a_mp3(wav)
        logger.info(
            "Audio generado: idioma=%s, %d caracteres, %d bytes",
            locucion.idioma, len(texto), len(datos),
        )
        return Audio(datos=datos, formato="mp3")


def _a_mp3(wav: bytes) -> bytes:
    """Convierte a MP3 el WAV que produce aHoTTS.

    El WAV sale a 22 kHz y 16 bits: unos 44 KB por segundo, así que una SdA
    leída entera pasaría de veinte megas. Inservible para descargar desde un
    centro educativo, y llenaría el volumen a esa misma velocidad. Comprimido
    queda en torno al 4 %.

    ffmpeg va por tubería, sin fichero temporal: ya hay uno inevitable —el
    binario de síntesis solo sabe escribir a disco— y no hace falta un segundo.
    """
    try:
        proceso = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "wav", "-i", "pipe:0",
             "-codec:a", "libmp3lame", "-qscale:a", "5",
             "-f", "mp3", "pipe:1"],
            input=wav, capture_output=True, timeout=120, check=True,
        )
    except FileNotFoundError as exc:
        raise VozError(
            "ffmpeg no está instalado; hace falta para comprimir el audio."
        ) from exc
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg falló: %s", exc.stderr.decode("utf-8", "replace")[:200])
        raise VozError("No se ha podido comprimir el audio") from exc
    except subprocess.TimeoutExpired as exc:
        raise VozError("La compresión del audio ha tardado demasiado") from exc

    if not proceso.stdout:
        raise VozError("La compresión del audio no produjo nada")
    return proceso.stdout
