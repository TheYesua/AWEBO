# Currículo LOMLOE — Extracción y carga

Este directorio contiene las herramientas para transformar el currículo
oficial publicado en el BOE (Real Decreto 217/2022) en datos
estructurados que el sistema utilizará para asistir al docente.

## Fuentes

Los XML oficiales viven en este mismo directorio, para que el proyecto pueda
re-ejecutar su propio extractor sin depender de ninguna ruta externa:

```
curriculo/fuentes/rd_217_2022.xml         RD 217/2022 (BOE-A-2022-4975)
curriculo/fuentes/orden_efp_754_2022.xml  Orden EFP/754/2022 (BOE-A-2022-13172)
```

**La fuente en uso es la Orden EFP/754.** Desarrolla el mismo real decreto para
el ámbito de Ceuta y Melilla, y se prefiere por dos razones: parte el currículo
por curso individual en vez de por ciclo, y es la única de las dos que publica
el currículo de Matemáticas de 4.º en sus itinerarios A y B. El RD 217 se
mantiene extraíble (`--perfil rd_217`) y sus artículos se usan igualmente para
derivar en qué cursos se imparte cada materia.

Ambos son texto legal publicado en el BOE, de reproducción libre.

## Workflow

```
┌──────────────────────┐    extractor.py      ┌──────────────────────┐
│ rd_217_2022.xml      │ ───────────────────▶ │ salida/*.json        │
│ (BOE oficial)        │                      │ (datos estructurados) │
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

1. **Extracción automática** (`extractor.py`): lee el XML del BOE y
   produce un JSON por cada `(materia, ciclo)` con la estructura de
   competencias específicas, criterios de evaluación y saberes básicos.

2. **Revisión humana**: el JSON producido se inspecciona y corrige
   manualmente si fuera necesario (errores de parsing, cabeceras
   atípicas, etc.).

3. **Carga en BD**: el comando `flask seed curriculo` lee el JSON
   revisado y lo persiste de forma idempotente.

## Materias incluidas en el alcance

| Etiqueta del proyecto | Materia oficial en el BOE |
|-----------------------|---------------------------|
| Tecnología            | "Tecnología y Digitalización" (1.º a 3.º) y "Tecnología" (4.º) |
| Lengua                | "Lengua Castellana y Literatura"                              |
| Matemáticas           | "Matemáticas"                                                  |
| Inglés                | "Lengua Extranjera"                                            |

## Ciclos según el RD 217/2022

El BOE agrupa competencias y saberes por ciclos, no por cursos
individuales:

- **Cursos de primero a tercero** → comunes a 1.º, 2.º y 3.º ESO
- **Curso de cuarto** → específicos de 4.º ESO

Esta agrupación se preserva en el modelo: las entidades
`Competencia`, `CriterioEvaluacion` y `SaberBasico` llevan un
`cursos_aplicables` (lista de cursos a los que pertenece el elemento).

## Uso

```bash
# Desde el host (recomendado)
docker compose exec api python -m app.curriculo.extractor \
    --xml /app/../../DOCUMENTACION/referencias/rd_217_2022.xml \
    --salida /app/../../implementacion/curriculo/salida
```

(Las rutas dentro del contenedor pueden ajustarse; ver el script.)

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
