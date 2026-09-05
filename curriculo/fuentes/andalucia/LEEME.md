# Andalucía · qué hace falta y qué NO sirve

## La norma

* **Decreto 102/2023**, de 9 de mayo (BOJA 90): ordenación y currículo de la ESO.
* **Orden de 30 de mayo de 2023** (BOJA 104, de 2 de junio): **la que importa**.
  Desarrolla el currículo y trae **diez anexos**. El que tiene competencias
  específicas, criterios de evaluación y saberes básicos por materia es el
  **Anexo II** (materias comunes y optativas); el **Anexo III** trae las
  optativas propias de Andalucía.

## Lo que se comprobó antes de escribir nada

**El HTML del BOJA no vale.** La propia página lo dice:

> «habiéndose suprimido todas las imágenes, ciertas tablas y algunos textos de
> la versión oficial al existir dificultades de edición»
> «Esta disposición incluye elementos no textuales, que no se muestran en esta
> página. Para visualizarlos, consulte la versión en PDF.»

En el HTML solo está el articulado: «Anexo II» aparece únicamente como
referencia cruzada, nunca como encabezado con contenido detrás. Y los anexos se
suprimen **sin dejar marcador**, así que no hay forma de notarlo leyendo el
HTML. Contraste que lo confirma: la Orden son 535 páginas de BOJA y el cuerpo
HTML son unas 40.

**No hay equivalente a la XTEC.** En Cataluña salvó el proyecto un PDF por
materia. La Consejería andaluza no publica nada así para LOMLOE.

## ⚠️ LA TRAMPA: los PDF por materia que SÍ hay son LOMCE

En `juntadeandalucia.es/educacion/portals/...` hay PDF por asignatura muy
apetecibles —«BIOLOGÍA Y GEOLOGÍA» y demás— y **son del currículo anterior**,
de la Orden de 14 de julio de 2016. Se reconocen porque hablan de «bloque de
asignaturas troncales», «Contenidos y criterios de evaluación» y códigos
competenciales LOMCE (CCL, CMCT, CD, CAA, CSC, SIEP).

**No traen «competencias específicas» ni «saberes básicos».** Usarlos metería
currículo derogado en una aplicación LOMLOE, y con la apariencia de estar bien.

Si un PDF de aquí no contiene la cadena «saberes básicos», no es el currículo
vigente.

## Sobre modificaciones posteriores

La Sentencia 308/2025 del TSJA anuló los artículos **14.2, 18.3 y 19.2** de esta
Orden, que son de toma de decisiones en evaluación y promoción. **No afecta a
los anexos curriculares.** No hay ninguna norma posterior que añada o quite
materias, al contrario que en Cataluña.

## Ficheros que hacen falta aquí

Los dos PDF oficiales de la Orden (535 páginas entre los dos):

```
https://www.juntadeandalucia.es/boja/2023/104/BOJA23-104-00289-9727-01_00284752.pdf
https://www.juntadeandalucia.es/boja/2023/104/BOJA23-104-00246-9727-02_00284752.pdf
```

Alternativa **no oficial** pero cómoda, de ADIDE-Andalucía (asociación de
inspectores), que publica la Orden troceada por anexos:

```
https://www.adideandalucia.es/normas/ordenes/Orden30mayo2023ESO-Anexo2.pdf
https://www.adideandalucia.es/normas/ordenes/Orden30mayo2023ESO-Anexo3.pdf
```

Vale para trabajar más cómodo, pero **el texto que se cargue debe salir del
BOJA**: es la fuente auténtica y es la que un docente puede citar.


---

# COMPROBADO con los ficheros delante (15/08/2026)

Los cuatro sirven. Se comprobó, en este orden:

## 1. No hay fuente rota

Cero anomalías de codificación en los cuatro PDF —tres en uno, que son siglas
legítimas—. Nada del problema del DOGC, donde el mapa de caracteres estaba
desplazado y se perdían `v` y `ç`.

**Aviso sobre el detector:** el primer recuento dio «1327 glifos rotos» y era
**falso positivo**. El patrón `[\x00-\x1f]` incluye el salto de línea, así que
contaba cada `palabra\npalabra` como anomalía. Al excluir `\n` y `\t`: cero.
Es la tercera vez que este mismo detector engaña; si vuelve a dar un número
alto, mirar **qué** caracteres son antes de creérselo.

## 2. Es LOMLOE, no LOMCE

La regla del apartado anterior, aplicada:

| | «saberes básicos» | «competencias específicas» | «troncales» |
|---|---|---|---|
| BOJA 1/2 | 58 | 87 | **0** |
| BOJA 2/2 | 67 | 84 | **0** |
| ADIDE Anexo 2 | 50 | 67 | **0** |

## 3. Dónde está el Anexo II

**Página 50** del primer PDF del BOJA (`...00289...`), con el encabezado
«ANEXO II · Materias comunes obligatorias y optativas». Empieza por Biología y
Geología. El Anexo I —horarios— está en la 40.

## 4. La buena noticia: los saberes SÍ tienen código oficial

`BYG.1.E.8`, `BYG.3.H.2`… 965 códigos solo en las primeras 70 páginas del
anexo, con prefijo por materia (BYG, DIG, ECE, EFI, EPV, VCE) y el segundo
campo tomando valores 1 a 4, que apunta a curso.

**Esto resuelve en Andalucía el problema que quedó abierto en Cataluña**, donde
el decreto identifica los bloques por nombre y hubo que ponerles un contador que
no está en el boletín. Aquí el código es del propio boletín y un docente lo
puede buscar.

Los criterios usan `N.M.` —1.1, 1.2…— igual que en Cataluña.

## 5. Estructura: dos columnas otra vez

El contenido va en **dos columnas** (x≈69 y x≈278), como el currículo catalán.
El extractor posicional de `extractor_xtec.py` sirve de base: leer por orden de
lectura mezclaría dos columnas, que es el fallo que allí habría producido «un
texto mezclado entre dos currículos distintos».

Queda por determinar **qué separa las dos columnas aquí** —en Cataluña era el
grupo de cursos, con cabecera propia— antes de escribir nada.


---

# ESTRUCTURA REAL (confirmada mirando el PDF, 15/08/2026)

Cada materia del Anexo II tiene **cinco bloques**, no uno. Con Biología y
Geología, páginas 55-67 del primer PDF:

| # | Qué | Formato |
|---|---|---|
| 1 | Nombre de la materia + introducción | texto corrido |
| 2 | «Saberes básicos de primer y tercer curso.» | tabla de **2 columnas**: `PRIMER CURSO` / `TERCER CURSO` |
| 3 | Competencias, criterios y saberes de 1.º y 3.º | tabla de **5 columnas**: Competencias · 1º(Criterios+Saberes) · 3º(Criterios+Saberes) |
| 4 | «Saberes básicos de cuarto curso.» | tabla de **1 columna** |
| 5 | Competencias, criterios y saberes de 4.º | tabla de **3 columnas**: Competencias · Criterios 4º · Saberes |

Y luego, sin salto de página ni tipografía especial, empieza la materia
siguiente con su nombre y su introducción.

## Lo que esto cambia respecto a Cataluña

**A favor, y es mucho:**

* Los saberes traen **código oficial del boletín** —`BYG.1.A.1`—, con el
  segundo campo indicando el curso. Adiós al contador inventado.
* La tabla de criterios trae una **columna de saberes con sus códigos**, o sea
  la relación criterio → saberes **explícita en la norma**. Eso no lo da ni el
  BOE ni el DOGC, y es exactamente lo que la conexión curricular necesita.
* El curso no hay que deducirlo del articulado: está en el código y en las
  cabeceras de columna.

**En contra:**

* **Dos maquetaciones por materia**, de 5 y de 3 columnas. El extractor catalán
  daba por hecho una sola.
* Los saberes aparecen **dos veces**: en su tabla propia con el texto completo,
  y citados por código en la tabla de criterios. Hay que decidir de cuál se
  toma el texto —de la tabla propia— y usar la otra solo para la relación.
* Una materia termina donde empieza la siguiente, sin marca. Habrá que
  reconocer el nombre contra una lista, que sale del articulado.

## Un falso positivo del que conviene no fiarse

Al copiar del visor aparecen cosas como «O bservación y c omparación d e m
uestras». **No está en el PDF**: es cómo el visor reconstruye el texto
justificado. Extrayendo con PyMuPDF: **cero palabras partidas** en las 70
páginas comprobadas, y lo mismo en el PDF de ADIDE.

Si alguien vuelve a ver esas letras sueltas, que compruebe con el extractor
antes de escribir una reparación que no hace falta.

## Pero SÍ hay palabras partidas, y no las parte el visor: las parte la tabla

Lo de arriba sigue siendo cierto —el **texto** del PDF está entero— y aun así,
durante tres semanas, 122 de los 737 criterios se cargaron mutilados. Lo que
los partía no era la extracción de texto sino **la detección de columnas**:
PyMuPDF encuentra en muchas páginas una columna de más, con la línea vertical
cayendo a mitad del párrafo, y `tabla.extract()` corta ahí.

```
col1: '1.2. Comenzar a incorpo\nprocesos de activación c\nporal, dosificación\n…'
col2: 'rar EFI.1.A.1.2.\nor- EFI.1.A.1.3.\ndel EFI.1.A.1.4.\n…'
```

El final de cada renglón acaba pegado a los códigos de saber de la celda de al
lado, y se pierde. Cuatro materias-curso estaban así **enteras**: Matemáticas
2.º, Lengua Castellana 1.º y Educación Física 1.º y 3.º.

**La moraleja es la del apartado anterior, del revés.** Allí se comprobó que el
texto estaba bien y se dio por buena toda la lectura; el texto estaba bien y la
lectura no. Lo que faltaba era compararlo con el boletín, que es lo que ahora
hace `test_los_criterios_estan_literalmente_en_el_boletin`.

## Y la causa era que el borde no estaba donde PyMuPDF decía (05/09, tarde)

Lo de arriba describe bien el síntoma y **se equivoca en el remedio**. La
reconstrucción por *huecos entre palabras* deja el problema a medias porque una
sola fila la estropea: la cabecera fusionada «Criterios de evaluación / Saberes
básicos» cruza la separación de columnas y la banda deja de estar libre.

La causa de verdad: **`find_tables()` agrupa las verticales con tolerancia** y
devuelve el borde lejos de la línea real.

```
Educación Física 1.º y 2.º, página 89 del primer PDF
  find_tables() dice          64,2  204,4  298,1  366,4  473,0  528,4
  el PDF DIBUJA la raya en    64,4  204,4  311,2  366,4  473,0  528,3
                                           ^^^^^ trece puntos
```

Trece puntos son dos o tres caracteres por renglón. Ahora los bordes salen de
`rayas_verticales()`, que lee `get_drawings()`: el hueco queda de plan B y los
bordes de PyMuPDF de último recurso.

**Quedan cinco**, de tres causas medidas y escritas en el test: dos con la
cabecera de la página siguiente dentro de la frase, uno con una palabra en
cursiva descolocada, y dos de Matemáticas 3.º con una palabra de menos.

### Y dos fallos más del maquetado estrecho

En Matemáticas caben tres cursos en la misma tabla, así que la columna mide
sesenta puntos, y eso trae dos cosas que no pasan en ninguna otra materia:

* El código se queda **solo en su renglón** —«2.1.»— porque no cabe con la
  primera palabra al lado. Matemáticas 1.º salía con 17 criterios en vez de 23.
* La palabra se parte **sin guion**: «conocimiento» cierra un renglón y «s
  necesarios,» abre el siguiente.

### Ojo con la comprobación, que también engañaba

El contraste «¿están los primeros sesenta caracteres del criterio seguidos en el
texto del boletín?» **sobrecontaba**: en una tabla de cinco columnas el orden de
lectura de PyMuPDF entrelaza las celdas vecinas, así que un criterio intacto
puede no aparecer seguido. De los 62 que señalaba, **48 estaban bien**.

Es la tercera vez que un detector de este fichero engaña —las otras dos son los
«1327 glifos rotos» y las «letras sueltas» de más arriba—. **Antes de creerse un
recuento alto, mirar tres casos concretos.**

## El Anexo III, cargado el 05/09

Las 19 materias que había salían todas del **Anexo II**. El **Anexo III** —las
optativas propias de Andalucía— no se había leído nunca, y no fue una decisión:
no estaba escrita en ninguna parte. Se descubrió contando los códigos de
criterio de los dos anexos y viendo cuáles llegaban a la salida.

Ya está dentro: **13 materias en 19 bloques, 370 criterios y 504 saberes**, con
lo que Andalucía queda en 32/60/1113/1461. Va en el segundo PDF del BOJA, de la
**página 16 a la 118** —el Anexo IV empieza en la 119—, y **su maquetación es la
misma que la del Anexo II**, así que se lee con los mismos tramos concatenados:

```
--pdf "...00289...pdf:49:"   --pdf "...00246...pdf:0:16"   --pdf "...00246...pdf:16:119"
```

La estimación previa de «321 criterios» era baja: salió de contar códigos
únicos, y el anexo repite códigos entre cursos.

Un detalle que conviene saber: el título del anexo, «Materias optativas propias
de la Comunidad Andaluza», se cuela como si fuera una materia. El extractor lo
descarta solo, porque viene sin criterios ni saberes, y hay un test que lo fija.

## Y el fallo que llevaba aquí desde el principio: los saberes

Todo lo de arriba es sobre criterios. Los saberes tenían el suyo y **no lo vio
nadie hasta el 05/09 por la tarde**, porque el recuento salía bien y el reparto
por bloques también.

Una materia acaba a media página y la siguiente empieza debajo, así que la
última página de su tramo trae las dos. El último saber es el que queda abierto
y se comía **la introducción entera de la materia siguiente**:

```
59 de los 957 saberes pasaban de 400 caracteres
el peor tenía 4238, con el texto de otra materia dentro
```

Lo destapó cargar el Anexo III, que puso una portada de anexo justo en la
costura: `TYD.3.E.2` —el último saber de Tecnología y Digitalización 3.º, que es
la última materia del Anexo II— llegó a la base con 4102 caracteres y la
introducción de Ampliación de Cultura Clásica dentro.

Tres correcciones, cada una con su medida:

| | máximo |
|---|---:|
| como estaba | 4513 |
| cortando por la altura del título siguiente | 1962 |
| + clasificando la tabla con las celdas reconstruidas | 1094 |
| + descartando la línea del título dentro de la tabla | 1094, y ninguno acaba con nombre de materia |

**Ojo con reconstruir de más.** Leer los saberes con las celdas reconstruidas
palabra a palabra *estropea* Geografía e Historia: sus columnas se leen enteras
de arriba abajo y reconstruir una tabla cuyo borde ya estaba bien entrelaza los
renglones de los dos cursos. Se reconstruye solo si el borde se movió más de
tres puntos.

Y un cuarto, aparte: `TYD.3.E.2` **repetía su última frase** porque el saber se
parte entre dos páginas y la segunda lo vuelve a imprimir en una tabla propia.
Ninguna de las cotas lo veía —el texto repetido es literal del boletín y mide
veinte caracteres—: se vio leyendo el PDF de una SdA. Se quita la cola que ya
está dicha justo antes, con un mínimo de treinta caracteres; medido sobre los
1461 saberes, con treinta salta ese y ninguno más.
