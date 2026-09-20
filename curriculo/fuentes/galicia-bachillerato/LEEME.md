# Bacharelato de Galicia — Decreto 157/2022

> **Estado: extraído y verificado.** 58 materias, 69 bloques, 361 obxectivos,
> 1695 criterios y 6065 contidos, en `curriculo/salida_galicia_bachillerato/`.
> Con esto 9b queda cerrada: Bachillerato en las cinco comunidades.

## La norma

* **Decreto 157/2022, do 15 de setembro** (DOG núm. 183, 26/09/2022), por el que
  se establecen la ordenación y el currículo del **bacharelato** en Galicia.
* Modificado por el **Decreto 118/2023, do 27 de xullo**.

Es el hermano exacto del de la ESO: **Decreto 156/2022, del mismo día**, y su
modificación **117/2023, también del 27 de julio**. Mismo patrón que Ceuta con
las Órdenes EFP/754 y 755, y que Andalucía con sus dos Órdenes de 30 de mayo.

Las **optativas** no salen del Decreto sino de dos Órdenes propias: la del
**13 de febreiro de 2023**, que establece su currículo, y la del **9 de agosto
de 2023**, que amplía la relación. Son 10 de las 54 materias.

En `comunidades.NORMAS` se citará **«Decreto 157/2022»** a secas, igual que la
ESO cita «Decreto 156/2022» aunque sus optativas también vengan de una Orde
aparte. Es una simplificación heredada, no una decisión nueva: el docente pone
en su programación la norma que ordena la etapa.

Todo esto sale de la página de Normativa de la propia Guía:
<https://www.edu.xunta.gal/portal/guialomloe/normativa>

## De dónde se descarga

De la Guía LOMLOE de la Consellería, igual que la ESO pero de su página de
Bacharelato:

<https://www.edu.xunta.gal/portal/guialomloe/bacharelato>

**Un PDF por materia**, 54, con el currículo completo y el texto limpio. Con
`docs/scripts/descargar-galicia-bacharelato.ps1`, que les pone el nombre de la
materia: el portal los sirve con nombres de hash y bajarlos a mano deja 54
ficheros indistinguibles.

Dos cosas que su hermano de la ESO no necesitaba:

* **La tabla de hashes no se escribió a mano.** Se leyó de los enlaces de la
  propia página. Un hash son 32 caracteres sin significado: teclearlos garantiza
  una errata, y la errata no da error sino **el PDF de otra materia**.
* **Dos carpetas de fecha.** El portal sirve unos desde `2023/09/08` y otros
  desde `2023/09/11`. La ESO cabía en una sola y su guion lleva la fecha en
  `$base`; aquí va con cada hash.

**El XML no existe aquí y el PDF del DOG no se usa**, por lo mismo que en la
ESO: el decreto publica el anexo entero en un solo documento.

## Lo comprobado antes de bajar nada (20/09/2026)

Sobre el PDF de **Matemáticas (I e II)**, 22 páginas, leído entero:

**La estructura es la misma que la de la ESO.** Literalmente la misma, con
«Bacharelato» donde aquella dice «Educación secundaria obrigatoria»:

```
CURRÍCULO / Bacharelato / Matemáticas
1. Matemáticas
   1.1 Introdución
   1.2 Obxectivos
        Obxectivos da materia
        OBX1. Modelizar e resolver problemas…
   1.3 Criterios de avaliación e contidos
        Primeiro curso
        Materia de Matemáticas
        1º curso
        Bloque 1. Sentido numérico
            Criterios de avaliación | Obxectivos
            ▪ CA1.1. Adquirir novo coñecemento…
            Contidos
            ▪ …
        Segundo curso
        …
```

Recuento de ese PDF: 76 `OBX`, 57 `CA`, 12 `Bloque` (6 por curso) y 12
`Contidos`. El mismo vocabulario gallego —obxectivos, criterios de avaliación,
contidos— y el mismo artefacto de guion de división (`\x02`) que ya normaliza el
extractor.

### El curso va sin punto, y eso ya estaba cubierto

La ESO escribe `1.º curso`; Bacharelato escribe **`1º curso`**, sin punto.
No hace falta tocar nada: `RX_CURSO_ORDINAL` ya lleva el punto opcional
(`^([1-4])\.?[ºo]\s+curso\s*$`). Se anota porque **parece** una diferencia que
rompe y no lo es, y para que nadie la «arregle» dos veces.

### Y una que sí rompía: «CA 1.1» con espacio

En el segundo curso de ese PDF aparece **`▪ CA 1.1. Adquirir…`**, con un espacio
entre `CA` y el número, mientras el primer curso escribe `CA1.1`. Contar eso en
los 54 fue lo que destapó el fallo de la ESO; está abajo.

## Lo que se hizo con los ficheros delante

**1. `extractor_dog.py` parametrizado por etapa**, con una `EtapaDOG` dentro del
propio fichero. Misma decisión que `EtapaBOJA` en el andaluz y con más motivo:
allí las dos etapas comparten maquetador, aquí comparten **el mismo documento**.
Lo único que cambia es a qué se traduce un ordinal. La ESO sale byte a byte
idéntica después del cambio, comprobado.

**2. Los 54 PDF son los que dicen ser.** El guion solo puede comprobar que lo
bajado empiece por `%PDF`, y eso no distingue un hash mal copiado que traiga
otra materia. Un test abre los 54, lee su portada y exige que diga «Bacharelato»
y la materia del nombre del fichero. Los 54 pasan.

**3. Ninguna materia calló su curso.** La tabla de excepciones de Bacharelato se
queda vacía: las 16 de «I e II» declaran «Primeiro curso» y «Segundo curso»
dentro del PDF. La ESO sí necesita la suya, para tres.

### Los «CA » con espacio: 28 aquí, y 9 en la ESO que estaba cargada

Contarlos aquí fue lo que destapó que la **ESO llevaba nueve criterios de
menos** desde agosto. `RX_CRITERIO` exigía el dígito pegado al `CA`, y el
anclaje del test buscaba `\bCA\d+\.\d+\b`: los dos con el mismo punto ciego, así
que el test decía «0 perdidos» con razón sobre lo que miraba. Cultura Financeira
salía con 18 criterios de 23 e Intelixencia Artificial para a Sociedade con 16
de 20 — en las dos, el bloque 4 entero.

Arreglados los dos patrones a la vez. Está en el LEEME de la ESO y en la
migración correspondiente.

### Tres rarezas del boletín, y solo en esta etapa

La ESO no tiene ninguna; Bacharelato tiene tres, en dos materias de 1717
criterios.

| Dónde | Qué dice | Qué se hace |
|---|---|---|
| Lingua Galega e Literatura 1.º, CA1.3 y CA1.4 | `OBX1 10` | **Dos** objetivos para un criterio. El primero va en `competencia` y el resto en `competencias_extra`, columna nueva (migración `c1b8d94e37f2`) |
| Literatura Dramática 2.º, CA2.5 | `OBX55` | La materia tiene cinco obxectivos. Se lee como `OBX5`, como excepción documentada en `ERRATAS_OBXECTIVO` |

Las dos importan porque **el seed omite el criterio entero** cuando no encuentra
su competencia: sin tocarlo, esos tres criterios no llegaban a la base de datos.

Lo de los dos objetivos se resolvió con una columna y no con un many-to-many
después de medir el coste: `competencia` es una cadena en los **10 944**
criterios de las nueve comunidades, y la FK la leen el API, el prompt, el seed y
las dos exportaciones. Misma forma que `BloqueSaberes.codigos_items`.

## La cota, medida

| Qué | Resultado |
|---|---|
| Códigos `CA` del PDF que no se extraen | **0** de 1398 |
| Códigos extraídos que el PDF no tiene | **0** |
| Criterios que no se encuentran de una pieza | **0** de 1717 |
| Contidos en más de dos trozos | **0** de 6194 |
| Criterios que citan un OBX inexistente | **0** |
| Contido más largo | 686 caracteres, y es del decreto |

### Lo que la cota NO vio, y se vio al sembrar

Todo lo de arriba daba cero **y aun así una materia entró mal**. Tecnoloxías da
Información e da Comunicación se cargó como «Páxina 1 de 12 Bacharelato
Tecnoloxías da Información e da Comunicación» y con **0 criterios**, porque sus
40 salieron sin obxectivo y el seed los omite.

La causa es una sola: `find_tables()` devuelve **seis columnas** en ese PDF y
no dos, con casi todas vacías. El extractor leía `fila[0]` y `fila[1]` por
índice, así que en la fila del «Materia de …» —que cae en la columna 1— la
izquierda salía vacía y no casaba el patrón, y en las de criterio el `OBX1`
caía en la columna 3 y la derecha salía vacía. Ahora se toma **la primera
celda con texto y la última**, que no depende de cuántas invente el lector.

Por qué la cota no lo vio: medía códigos y texto, y los dos estaban bien. Lo
que estaba mal era **el nombre de la materia y la relación con el obxectivo**,
que no se medían. Y los dos tests que debían cubrirlo tenían un hueco cada uno:
el de la portada comprobaba el PDF y no lo extraído, y el de los obxectivos
decía `if x and x not in codigos` — ese `if x` saltaba justo el valor que hace
daño, la cadena vacía. Los dos corregidos.

Recuperó además 131 contidos y 5 obxectivos que se perdían por lo mismo. Las
cifras de la cota de arriba son ya de después del arreglo.

Y se cerró el círculo del objetivo de más: `competencias_extra` se guardaba y
**no lo pintaba nadie**. Guardar algo para no perderlo y dejarlo invisible en el
documento del docente es no perderlo solo sobre el papel, así que la columna
«Competencia» de la tabla de criterios enseña ahora «1, 10» cuando los hay. Se
hace en `filas_de_conexion`, que es donde PDF y DOCX convergen.

Dos trozos y no uno para los contidos, igual que en la ESO: van a dos niveles y
el extractor pega el agrupador a cada item, así que la cadena compuesta solo
aparece literal para el primero de cada grupo.

## Los cursos, según la página

La Guía dice el curso de cada materia en sus columnas, y las que llevan
«(I e II)» en el título van en los dos. **Se anota como contraste, no como
fuente**: en la ESO los cursos venían dentro del PDF en 32 de 35, y aquí el de
Matemáticas los trae. Lo que esta tabla sirve es para saber cuántos deberían
salir y detectar los que no los declaren.

| Cursos | Materias |
|---|---:|
| Solo 1.º | 18 |
| Solo 2.º | 20 |
| 1.º y 2.º (las de «I e II») | 16 |
| **Total** | **54** |

## Por qué Galicia fue la última de las cinco

No por dificultad sino por orden: era la única cuyo boletín no publica el
currículo en un formato del que se pueda extraer sin pasar por la Guía. Con la
Guía delante resultó ser **la más barata de las cinco**, porque el extractor y
su batería de contraste ya existían desde el 16/08.

Y aun siendo la más barata, fue la que encontró un fallo en currículo ya
cargado. No por auditarla: por contar una rareza de **la otra** etapa.

**No se versionan los PDF** (`.gitignore`), como el resto de fuentes en PDF.
