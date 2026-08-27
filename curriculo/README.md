# Currículo LOMLOE — Extracción y carga

Este directorio contiene las herramientas para transformar el currículo
oficial publicado en el BOE (Real Decreto 217/2022) en datos
estructurados que el sistema utilizará para asistir al docente.

## Fuentes

Desde el 14/08/2026 hay **una carpeta por comunidad**, porque el currículo
dejó de ser uno solo:

```
curriculo/fuentes/estatal/rd_217_2022.xml         RD 217/2022 (BOE-A-2022-4975)
curriculo/fuentes/ceuta/orden_efp_754_2022.xml    Orden EFP/754/2022 (BOE-A-2022-13172)
curriculo/fuentes/cataluna/decret_175_2022.xml    Decret 175/2022 (Akoma Ntoso del DOGC)
curriculo/fuentes/cataluna/xtec/*.pdf             un PDF por materia (XTEC)
curriculo/fuentes/andalucia/*.pdf                 BOJA núm. 104 de 2 de junio de 2023
curriculo/fuentes/galicia/*.pdf                   un PDF por materia (Guía LOMLOE)
```

**Los PDF no están en el repositorio**, por tamaño: son 55 MB. Cada carpeta
lleva un `LEEME.md` con de dónde se descargan y qué tienen de particular. En el
caso del DOGC, un aviso importante: sus PDF traen la codificación de fuente
rota —pierden o sustituyen letras acentuadas sin que se pueda detectar— y por
eso el currículo catalán se extrae de los PDF por materia de la XTEC.

Todos son texto legal publicado en boletín oficial, de reproducción libre.

**La fuente en uso es la Orden EFP/754.** Desarrolla el mismo real decreto para
el ámbito de Ceuta y Melilla, y se prefiere por dos razones: parte el currículo
por curso individual en vez de por ciclo, y es la única de las dos que publica
el currículo de Matemáticas de 4.º en sus itinerarios A y B. El RD 217 se
mantiene extraíble (`--perfil rd_217`) y sus artículos se usan igualmente para
derivar en qué cursos se imparte cada materia.

Ambos son texto legal publicado en el BOE, de reproducción libre.

## Por qué la salida sí se versiona

Los JSON de `salida*/` están en el repositorio **a propósito**, aunque sean un
producto derivado. La razón es la de arriba: las fuentes en PDF no están, así
que sin ellos nadie que clone el proyecto podría sembrar el currículo de
Cataluña, Andalucía ni Galicia. Son unos 4 MB de texto.

```
curriculo/salida/            estatal y Ceuta (BOE)
curriculo/salida_cataluna/   Decret 175/2022 + PDF de la XTEC
curriculo/salida_andalucia/  Orden de 30 de mayo de 2023 (BOJA)
curriculo/salida_galicia/    Decreto 156/2022 (Guía LOMLOE de la Xunta)
```

Cada JSON lleva dentro su `comunidad` y su `idioma`, y **el fichero manda**
sobre lo que se pase en la orden: el dato correcto es el del extractor, no el
de quien teclea. *(Excepción histórica: los de `salida/` son anteriores al
campo y no lo traen, así que para ellos vale el valor por defecto, `ceuta`.)*

## Workflow

```
┌──────────────────────┐    extractor*.py     ┌──────────────────────┐
│ boletín oficial      │ ───────────────────▶ │ salida*/*.json       │
│ (XML o PDF)          │                      │ (datos estructurados) │
└──────────────────────┘                      └──────────────────────┘
                                                        │
                                              revisión humana
                                                        │
                                                        ▼
                                              ┌──────────────────────┐
                                              │ flask seed curriculo │
                                              │ (carga en BD)        │
                                              └──────────────────────┘
```

1. **Extracción automática**: produce un JSON por cada `(materia, ciclo)` con
   competencias específicas, criterios de evaluación y saberes básicos. Hay
   **cuatro extractores**, porque cada boletín publica de una forma distinta
   y forzar uno solo salía más caro que tener cuatro:

   | Módulo | Fuente | Cómo lee |
   |---|---|---|
   | `extractor.py` | BOE y DOGC (XML) | máquina de estados sobre el texto en orden |
   | `extractor_xtec.py` | PDF de la XTEC | posición horizontal: las tablas no tienen bordes |
   | `extractor_boja.py` | PDF del BOJA | celda a celda: estas tablas sí tienen bordes |
   | `extractor_dog.py` | PDF de la Xunta | celda a celda, más el texto suelto: los cursos no siempre van en tabla |

   El BOJA es el único que **numera sus saberes básicos** (`BYG.1.A.8`), y ese
   código se conserva. Galicia numera los **bloques** pero no los contidos, así
   que su código lleva la mitad oficial. En los otros dos, el cargador les pone
   un contador propio.

   Y Galicia usa **otro vocabulario**: donde la LOMLOE dice «competencias
   específicas», el decreto gallego dice «obxectivos» (`OBX1`), y los saberes
   básicos son «contidos». No es traducción — el decreto no habla de
   competencias específicas en el currículo de cada materia.

2. **Revisión humana**: el JSON producido se inspecciona y corrige
   manualmente si fuera necesario (errores de parsing, cabeceras
   atípicas, etc.).

3. **Carga en BD**: el comando `flask seed curriculo` lee el JSON
   revisado y lo persiste de forma idempotente.

## Alcance actual

| Comunidad | Materias | Bloques | Criterios | Saberes |
|---|---:|---:|---:|---:|
| Ceuta y Melilla (Orden EFP/754) | 22 | 42 | 752 | 1461 |
| Cataluña (Decret 175/2022 + XTEC) | 26 | 36 | 737 | 1918 |
| Andalucía (Orden 30/05/2023) | 19 | 41 | 737 | 957 |
| Galicia (Decreto 156/2022 + Guía LOMLOE) | 30 | 60 | 1583 | 4643 |
| País Vasco (Decreto 77/2023) | 32 | 43 | 733 | 1479 |

Un bloque es un par `(materia, cursos)`: Andalucía y Galicia publican curso a
curso y por eso tienen más bloques que materias, mientras que Cataluña agrupa
1.º–3.º. Los «saberes» de Galicia son sus contidos, que están más desglosados
que los saberes básicos de las otras comunidades — de ahí que salgan 4.643.

El País Vasco agrupa por **ciclos** —«1.º y 2.º», «3.º y 4.º»—, así que sus
bloques son pocos para las materias que tiene. Las 32 materias salen de 30
títulos del Anexo III: Matemáticas de 4.º se desdobla en los itinerarios A y B,
que tienen currículos distintos.

Empezó siendo cuatro materias —Tecnología, Lengua, Matemáticas e Inglés—, que
es el alcance con el que nació el proyecto como TFG.

## Ciclos según el RD 217/2022

El BOE agrupa competencias y saberes por ciclos, no por cursos
individuales:

- **Cursos de primero a tercero** → comunes a 1.º, 2.º y 3.º ESO
- **Curso de cuarto** → específicos de 4.º ESO

Esta agrupación se preserva en el modelo: las entidades
`Competencia`, `CriterioEvaluacion` y `SaberBasico` llevan un
`cursos_aplicables` (lista de cursos a los que pertenece el elemento).

## Uso

`./curriculo` se monta en el contenedor como `/curriculo`, **en solo lectura**:
basta para sembrar, que es lo único que hace falta desde dentro. Para volver a
extraer hay que escribir, así que se hace desde el host.

```bash
# Sembrar. Cada JSON lleva su comunidad dentro, así que no hace falta decirla.
docker compose exec api flask seed curriculo --directorio /curriculo/salida
docker compose exec api flask seed curriculo --directorio /curriculo/salida_cataluna
docker compose exec api flask seed curriculo --directorio /curriculo/salida_andalucia
docker compose exec api flask seed curriculo --directorio /curriculo/salida_galicia
```

El seed **añade y actualiza, pero no borra**. Cuando un extractor mejora y
cambian los códigos, las filas viejas se quedan: currículo que ya no está en el
boletín, indistinguible del bueno y ofreciéndose en los desplegables. Para eso
está la recarga limpia:

```bash
docker compose exec api flask seed curriculo \
    --directorio /curriculo/salida_cataluna --borrar-sobrantes
```

No es el comportamiento por defecto porque borra: apuntar sin querer a una
carpeta a medias se llevaría el resto del currículo de esa comunidad. Y **no
borra lo que alguna SdA esté citando** — el documento de esa situación pasaría
a decir «(no encontrado en el currículo)» donde antes había texto, sin que el
docente haya tocado nada. Esas filas se conservan y el comando las cuenta.

```bash
# Volver a extraer (solo si se cambia el extractor o llega un boletín nuevo).
cd api

python -m app.curriculo.extractor \
    --xml ../curriculo/fuentes/ceuta/orden_efp_754_2022.xml \
    --salida ../curriculo/salida

python -m app.curriculo.extractor_xtec \
    --pdfs ../curriculo/fuentes/cataluna/xtec \
    --articulado ../curriculo/fuentes/cataluna/decret_175_2022.xml \
    --salida ../curriculo/salida_cataluna

# El Anexo II del BOJA está partido entre dos ficheros y una materia queda a
# caballo, así que los tramos se concatenan antes de leer. El formato es
# RUTA:DESDE:HASTA, con las páginas en base 0 y HASTA excluido.
python -m app.curriculo.extractor_boja \
    --pdf "../curriculo/fuentes/andalucia/BOJA23-104-00289-9727-01_00284752.pdf:49:" \
    --pdf "../curriculo/fuentes/andalucia/BOJA23-104-00246-9727-02_00284752.pdf:0:16" \
    --salida ../curriculo/salida_andalucia

# Galicia: un PDF por materia, como la XTEC. Los cursos van dentro del PDF.
python -m app.curriculo.extractor_dog \
    --pdfs ../curriculo/fuentes/galicia \
    --salida ../curriculo/salida_galicia
```

## Formato JSON producido

```json
{
  "materia": "Tecnología y Digitalización",
  "etapa": "ESO",
  "ciclo": "Cursos de primero a tercero",
  "cursos_aplicables": ["1º ESO", "2º ESO", "3º ESO"],
  "competencias_especificas": [
    {
      "codigo": "CE1",
      "descripcion": "Buscar y seleccionar información ...",
      "descriptores": ["CCL3", "STEM1", "CD1"]
    }
  ],
  "criterios_evaluacion": [
    {"codigo": "1.1", "competencia": "CE1", "descripcion": "..."},
    {"codigo": "1.2", "competencia": "CE1", "descripcion": "..."}
  ],
  "saberes_basicos": [
    {
      "bloque": "A. Proceso de resolución de problemas",
      "items": ["Identificación y formulación ...", "..."]
    }
  ]
}
```
