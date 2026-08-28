# Currículo del País Vasco — Decreto 77/2023

**Norma:** Decreto 77/2023, de 30 de mayo (BOPV núm. 109, 09/06/2023), de
establecimiento del currículo de la **Educación Básica** e implantación en la
Comunidad Autónoma de Euskadi. Con **corrección de errores** publicada en el
BOPV del 31/07/2023.

Ojo con el alcance: «Educación Básica» aquí es **Primaria + ESO + FP Básica**
en un solo decreto. A AWEBO solo le interesa la parte de DBH (ESO).

El código de comunidad es **`pais-vasco`**, con guion. `euskadi` es un alias
que resuelve `normalizar()`, pero los JSON deben llevar el canónico.

## En euskera, y por qué

Igual que Cataluña se cargó en catalán y Galicia en gallego, habiendo versión
castellana oficial de las dos. La razón de fondo no es la simetría: el
currículo que un docente vasco cita en su programación es el de su comunidad,
y el texto en euskera es el que aparece en los documentos oficiales de su
centro. Cargar la versión castellana le obligaría a traducir de vuelta lo que
la aplicación le devuelve.

En los ficheros de Berrigasteiz el sufijo **`_e`** es *euskaraz* y **`_c`**
castellano.

## De dónde se descarga, y por qué no del BOPV

De **Berrigasteiz**, el portal del Berritzegune del Gobierno Vasco:

<https://www.berrigasteiz.com/monografikoak/ec22/etapa_oinarrizkoa/>

Con `docs/scripts/descargar-pais-vasco.cmd`. Dos razones, y la segunda pesa
más que la primera:

1. Publica **un PDF por materia** en `jakintzagaiak_dbh/`, igual que la XTEC y
   la Guía LOMLOE. Van **tres de tres**: cuando una comunidad tiene lengua
   propia, su consejería republica el currículo por materias mejor que el
   boletín.
2. Su copia del decreto lleva **la corrección de errores ya incorporada**
   (`_ZUZENDUTA` = corregido). En el BOPV la corrección es un documento aparte
   que habría que cruzar a mano.

La fuente oficial, por si hace falta contrastar:

* Decreto: <https://www.euskadi.eus/web01-bopv/es/bopv2/datos/2023/06/2302729a.pdf>
* Corrección: <https://www.euskadi.eus/bopv2/datos/2023/07/2303691a.pdf>
* Articulado en HTML (euskera): <https://www.legegunea.euskadi.eus/eli/es-pv/d/2023/05/30/77/dof/eus/html/>

**No se versionan** (`.gitignore`), como los de las demás comunidades.

## El vocabulario NO cambia, y eso es la buena noticia

Comprobado sobre el articulado en euskera de Legegunea (artículos 2 y 5):

| LOMLOE estándar | País Vasco (euskera) |
|---|---|
| Competencias específicas | **konpetentzia espezifikoak** |
| Criterios de evaluación | **ebaluazio-irizpideak** |
| Saberes básicos | **oinarrizko jakintzak** |
| Situaciones de aprendizaje | ikas-egoerak |
| Área / materia | arloa / **ikasgaia** |
| Ámbito | eremua |
| Anexo | eranskina |

Es traducción literal, no un vocabulario propio. **Al revés que Galicia**,
donde «obxectivos» ocupa el lugar de las competencias específicas y hubo que
invertir la relación criterio→competencia. Aquí la estructura de datos que ya
existe debería valer tal cual.

Del artículo 5.5, textualmente: los anexos **II y III** fijan «arlo eta ikasgai
bakoitzerako konpetentzia espezifikoak, ebaluazio-irizpideak eta oinarrizko
jakintza».

## Los anexos

| Anexo | Qué lleva |
|---|---|
| I | Perfil de salida y descriptores operativos |
| II | Currículo de las **áreas** (Lehen Hezkuntza / primaria) |
| **III** | Currículo de las **materias de DBH** ← lo que interesa |
| IV | Orientaciones para diseñar situaciones de aprendizaje |
| V | Situaciones de aprendizaje |
| VI | Horario semanal mínimo por materia |

El **articulado en HTML de Legegunea no incluye los anexos**: llega hasta las
disposiciones y ahí acaba. Comprobado. Por eso hace falta el PDF.

El Anexo VI puede servir para deducir qué materias van en qué curso, que es el
dato que en Cataluña hubo que sacar del articulado. Está por comprobar si lo
dice curso a curso o solo por etapa.

## Comprobado sobre los ficheros (27/08/2026)

El script descargó **33 PDF, 18 MB**: el decreto completo, 30 por materia y dos
que no son currículo (ver abajo). Lo averiguado:

* **El decreto NO es bilingüe.** 377 páginas, **ninguna** con cabecera
  castellana. Berrigasteiz publica la versión en euskera ya separada, así que
  no hay que partir columnas. Era la duda que más trabajo podía costar.
* **Texto limpio**, sin OCR y sin el problema de codificación del DOGC. El
  único artefacto es que las palabras se parten con **guion normal** (U+002D) y
  no con el blando, así que hay que unirlas a mano.
* **El Anexo III ocupa las páginas 127 a 352** y contiene **30 materias**, que
  son exactamente los 30 PDF sueltos. El contraste cuadra.
* **Los bloques llevan código oficial** —letra o número del decreto—; los
  saberes de dentro no, igual que en Galicia.
* **Los cursos salen de las cabeceras de las tablas por ciclo** en las materias
  que se imparten en varios; el resto, de la tabla del artículo 13.
* **Matemáticas de 4.º tiene itinerarios A y B** con currículos distintos.

### Dos ficheros que NO son currículo

El rastreo del script los recoge porque el nombre empieza por `DBH`, y el
extractor los descarta explícitamente:

| Fichero | Qué es |
|---|---|
| `DBH1_EUSKARA_nire_begiak_e.pdf` | Material de aula, no currículo |
| `III_eranskina_e.pdf` | Anexo III del **Decreto 76/2023**, el de Bachillerato, y además el de situaciones de aprendizaje |

El segundo es el que más conviene tener anotado: viene del monográfico de otra
etapa y su nombre coincide con lo que se busca.

### Faltan `DBH2` y `DBH7` en la numeración

Y **no es un fallo de descarga**: la numeración de Berrigasteiz no es
correlativa con el anexo. Los 30 PDF por materia se corresponden uno a uno con
los 30 títulos del Anexo III, comprobado por recuento.

## Lo cerrado y lo que sigue abierto

1. ~~**El asterisco de los saberes.**~~ **Cerrado el 27/08: no tiene leyenda.**
   Se buscó en el articulado, en los seis anexos, en Berrigasteiz y fuera. Los
   dos asteriscos explicados del decreto son otros —el del artículo 13, que
   marca las optativas de oferta obligatoria, y el `**` del Anexo VI, casillas
   de horario sin mínimo—. Va al final del saber salvo en Lengua, donde va al
   principio, y está en el 26 % de ellos; esa proporción encaja mejor con
   «añadido vasco» que con «mínimo estatal», pero es conjetura y no se usa. Se
   retira del texto sin atribuirle significado.
2. ~~**Lengua va como una sola materia.**~~ **Aceptado el 27/08**, y no por
   pereza: el Anexo III da un currículo conjunto para «Euskara eta Literatura
   eta Gaztelania eta Literatura» y el artículo 13 las lista como dos.
   Separarlas exigiría repartir los saberes entre las dos lenguas, y el único
   indicio de cuál es de cuál es el asterisco — que, cerrado el punto 1, no se
   sabe qué significa. Un reparto inventado sería peor que un nombre largo, y
   además ese nombre es el que el docente vasco reconoce.
3. **Los ámbitos de diversificación** (`eremua`): el artículo 25.6 nombra dos
   —lingüístico-social y científico-tecnológico— y dice qué materias agrupa
   cada uno, pero **no tienen currículo propio en el Anexo III**. Igual que en
   Galicia, habrá que decidir si se montan a partir de las materias que
   agrupan o si se dejan fuera.
