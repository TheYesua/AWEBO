# Bachillerato de Ceuta y Melilla — Orden EFP/755/2022

> **Estado: extraído y verificado.** 47 materias, 61 bloques, 279 competencias
> específicas, 918 criterios y 1784 saberes, en
> `curriculo/salida_ceuta_bachillerato/`. Lo que hubo que averiguar con el XML
> delante está en el último apartado, ya con las respuestas.

## La norma

* **Real Decreto 243/2022**, de 5 de abril: ordenación y enseñanzas mínimas de
  Bachillerato. Es el hermano del 217/2022, que es el de la ESO.
* **Orden EFP/755/2022, de 31 de julio** (BOE núm. 187, de 5 de agosto de 2022,
  `BOE-A-2022-13173`): **la que importa**. Establece el currículo y regula la
  ordenación del Bachillerato **en el ámbito de gestión del Ministerio**, que es
  como el BOE llama a los centros de Ceuta y Melilla.

Y aquí la coincidencia que hace barata esta carga: la Orden de la ESO es la
**EFP/754/2022**, `BOE-A-2022-13172`. **Consecutivas, del mismo departamento y
publicadas el mismo día.** La 754 es de 28 de julio y la 755 de 31.

| Etapa | Norma | Referencia BOE |
|---|---|---|
| ESO | Orden EFP/754/2022 | `BOE-A-2022-13172` |
| **Bachillerato** | **Orden EFP/755/2022** | **`BOE-A-2022-13173`** |

## De dónde se descarga

Con `docs/scripts/descargar-boe.ps1`, que baja las tres normas estatales —el RD
217, la 754 y la 755— y las deja donde el extractor las espera.

**Ese guion no existía hasta el 18/09/2026**: los dos XML que ya había se
bajaron a mano en agosto, cuando solo había una fuente y una etapa. Las otras
cuatro comunidades sí tenían el suyo.

Tres avisos que el guion comprueba solo, y que están ahí porque son las tres
formas de acabar con un fichero que parece bueno y no lo es:

1. **La API del BOE devuelve JSON si no le pides XML.** Hay que mandar
   `Accept: application/xml`; sin eso se guarda un fichero que empieza por `{`
   y el extractor no se entera hasta doscientas líneas después, cuando no
   encuentra ni un párrafo.
2. **Se baja el texto consolidado, no el del diario.** La EFP/755 tiene una
   modificación del 21/07/2023 y el texto original no la lleva: cargaríamos
   currículo derogado sin que nada lo avisara. Mismo criterio que en el País
   Vasco, donde se prefirió la copia de Berrigasteiz por traer la corrección de
   errores ya dentro.
3. **PowerShell descodifica la respuesta antes de que la veas.** Y pasó el
   18/09/2026 con este mismo fichero: `Invoke-WebRequest` elige el codec con el
   `Content-Type`, el BOE no manda `charset`, así que PS 5.1 leyó los bytes
   UTF-8 como ISO-8859-1 y al reescribirlos en UTF-8 quedaron los 7067 acentos
   rotos. **Las dos comprobaciones de arriba lo dieron por bueno**, porque `<` y
   `ANEXO II` son ASCII puro y no se enteran. Ahora el guion escribe los bytes
   tal cual llegaron y busca además el patrón del doble encoding.

Y una diferencia que no es del guion sino del BOE: la API de consolidada
envuelve el texto en `<response><data><texto><bloque>`, y el diario en
`<documento><texto>`. Los `<p>` de dentro son idénticos. Los dos XML que ya
había son del diario porque se bajaron a mano; `leer_parrafos_boe` busca
`<texto>` en profundidad desde entonces, así que le da igual cuál sea.

**El XML sí se versiona**, en el repositorio público y no en `awebo_fuentes`.
Lo que el `.gitignore` deja fuera por tamaño son los **PDF**; los XML del BOE
son pequeños —este pesa 2,6 MB— y los otros tres ya están subidos. Sin ellos,
quien clone el proyecto no podría volver a extraer ni correr los tests que
vuelven a la fuente, que son la mitad de los del extractor.

## Dónde está el currículo dentro de la Orden

En el **Anexo II, «Materias de Bachillerato»** — el mismo sitio que en la ESO,
donde el Anexo II de la EFP/754 trae las 22 materias que hoy están cargadas.

Los seis anexos, del índice del BOE:

| Anexo | Qué trae |
|---|---|
| I | Competencias clave en el Bachillerato |
| **II** | **Materias de Bachillerato** ← el currículo |
| III | Situaciones de aprendizaje |
| IV | Horario para la etapa |
| V | Bloques de materias del Bachillerato en tres años académicos |
| VI | Continuidad entre materias |

## Las modalidades

Cuatro, en los artículos 11 a 14: **Artes**, **Ciencias y Tecnología**,
**General** y **Humanidades y Ciencias Sociales**. El artículo 15 añade las
optativas.

**No se modelan**, igual que en Andalucía y el País Vasco y por la misma razón:
para generar una SdA basta con curso y materia. Si un día hicieran falta, están
en esos artículos.

## Lo que había que averiguar con el XML delante, y lo que salió

Lo de arriba sale del articulado, que el BOE publica entero en HTML. Lo que no
se podía saber sin el fichero era cómo está escrito el Anexo II. Las tres
preguntas, con la respuesta:

**1. Cómo titula cada materia.** En `<p class="centro_cursiva">` y en caja de
título: «Análisis Musical». **No** en `centro_redonda` y mayúsculas, que es lo
que hace su Orden hermana de la ESO. Aquí `centro_redonda` son los 561
epígrafes de «Orientaciones metodológicas» —«Gestión emocional», «Escucha
activa y uso de partituras»—, así que heredar el perfil de la 754 cambiándole
la lista de materias **devuelve cero materias y ningún error**. Por eso el
perfil `orden_efp_755` existe y no es un `orden_efp_754` con otra lista.

**2. Cómo marca los cursos.** Con numeral romano en el propio título, como el
BOPV: «Matemáticas», «Matemáticas I», «Matemáticas II». Le pasa a 14 de las 47.

**3. Si las materias con I y II son una o dos.** **Una, con dos cursos**, igual
que en Andalucía — y aquí no es una preferencia, lo decide el boletín: la
sección sin numeral trae las competencias específicas y **ni un criterio**, y
las del numeral traen criterios y saberes y **ni una competencia**. Partirlas
en dos materias dejaría a catorce sin una sola competencia específica, que es
justo lo que el generador necesita para redactar. El extractor las procesa como
cambio de ciclo, que ya heredaba las competencias.

### Dos cosas más que solo se ven con el fichero delante

- **«Segunda Lengua Extranjera» no tiene currículo.** El anexo le dedica una
  sección sin competencias, criterios ni saberes: la Orden la remite entera a la
  primera lengua extranjera. Son 48 cabeceras y 47 materias. **En la ESO sí lo
  tiene** y está cargada, así que la diferencia es entre las dos Órdenes, no un
  descuido de esta carga.
- **El boletín etiqueta mal dos párrafos.** «Matemáticas inclusivas» y
  «Matemáticas y herramientas digitales» son epígrafes de metodología: en
  Matemáticas I y II van en `centro_redonda` y dentro de Matemáticas Generales
  alguien los dejó en `centro_cursiva`, que es la clase de las cabeceras. No
  rompen nada porque caen después de «Orientaciones metodológicas», que ya cerró
  la materia, pero hay un test que lo vigila por si algún día lo mueven.

Y una contradicción del propio BOE: titula la materia «Matemáticas **A**plicadas
a las Ciencias Sociales» y sus dos cursos «Matemáticas **a**plicadas…». Sin
comparar en *casefold*, esa materia se quedaba con las competencias y perdía
sus dos cursos enteros, criterios y saberes incluidos.

## La cota

**279 competencias específicas, 918 criterios, 270 bloques y 1744 saberes con
guion**, contados en el XML con una máquina de estados independiente de la del
extractor, y comprobados **uno a uno**, no solo en total: un recuento que cuadra
puede estar cambiando un saber por otro. No se perdió ninguno.

La salida trae 1784 items de saber, 40 más que los 1744 con guion. Son
sub-epígrafes numerados —«1.1 El texto teatral: Definición y elementos.»— que el
extractor guarda como un item más. **Ya lo hacía con la ESO**: 20 casos en la
Orden EFP/754 y 11 en el RD 217, cargados desde hace meses. Cambiarlo ahora
movería saberes ya sembrados que alguna SdA puede citar, así que se deja y queda
escrito.

Era, como se esperaba, más fácil que en ningún otro sitio por ser XML y no PDF:
no hay bordes de tabla que corten palabras ni membretes que se cuelen. Lo que sí
hubo fue la otra forma que tiene de fallar un XML —una maquetación distinta de
la esperada— y, antes que nada, un fichero con todos los acentos rotos que pasó
las dos verificaciones de la descarga.
