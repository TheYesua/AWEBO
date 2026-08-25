# Currículo de Galicia — Decreto 156/2022

**Norma:** Decreto 156/2022, de 15 de septiembre (DOG núm. 183, 26/09/2022),
por el que se establecen la ordenación y el currículo de la ESO en Galicia.
Modificado por el Decreto 117/2023.

## De dónde se descarga, y por qué no del boletín

Los PDF de esta carpeta **no salen del DOG** sino de la Guía LOMLOE de la
Consellería:

<https://www.edu.xunta.gal/portal/guialomloe/secundaria>

Es el equivalente gallego a los PDF por materia de la XTEC: **un PDF por
materia**, con el currículo completo y el texto limpio. El DOG publica el
Anexo II entero en un solo documento, y ya se aprendió con Cataluña lo que
cuesta trocear eso — y lo que cuesta más aún cuando el PDF del boletín trae la
codificación de fuente rota.

Se descargan con `docs/scripts/descargar-galicia.ps1`, que les pone el nombre
de la materia: el portal los sirve con nombres de hash y bajarlos a mano deja
35 ficheros indistinguibles.

**No se versionan** (`.gitignore`), como los de las demás comunidades.

## Lo averiguado antes de escribir el extractor (16/08/2026)

Comprobado sobre `Bioloxia-e-Xeoloxia.pdf`, 23 páginas:

* **Texto limpio.** Se lee sin OCR y sin el problema de codificación del DOGC.
  El único artefacto visto es un `` donde va un guion de división de
  palabra («perse‑gue»), que hay que normalizar.
* **En gallego**, que es lo que interesa: la lengua propia de la comunidad,
  igual que Cataluña se cargó en catalán.

### Galicia usa otro vocabulario, y eso importa

| LOMLOE estándar | Galicia | Código |
|---|---|---|
| Competencias específicas | **Obxectivos** | `OBX1`, `OBX2`… |
| Criterios de evaluación | Criterios de avaliación | `CA1.1`, `CA1.2`… |
| Saberes básicos | **Contidos** | agrupados en `Bloque 1`, `Bloque 2`… |

No es un detalle de traducción: el decreto **no habla de competencias
específicas** en el currículo de cada materia. Lo que ocupa ese lugar son los
«obxectivos», con su propio código `OBX`.

### Estructura del documento

```
CURRÍCULO / Educación secundaria obrigatoria / <Materia>
1. <Materia>
   1.1 Introdución
   1.2 Obxectivos
        OBX1. …
   1.3 Criterios de avaliación e contidos
        Bloque 1. Proxecto científico
          Obxectivos | Criterios de avaliación     ← tabla
          OBX1       | CA1.1. Analizar e explicar…
```

**Los criterios se agrupan por bloque y cada uno referencia su `OBX`**, al
revés que en las demás comunidades, donde los criterios cuelgan de la
competencia. Y criterios y contenidos van en la **misma** sección (`1.3`), no
separados.

### Lo bueno, comparado con lo que ya se ha hecho

* **Todo lleva código oficial**: `OBX1`, `CA1.1`, y los bloques van numerados.
  Es lo que Andalucía tiene y Cataluña no — allí hubo que inventar un contador
  para los bloques de saberes.
* **Los cursos están en la web**, en la tabla de la Guía LOMLOE, materia por
  materia. No hay que deducirlos del articulado como en Cataluña.

### Los contidos, resueltos con los ficheros delante

Al investigar sin los PDF se anotó aquí que «Contidos» no aparecía suelto y que
igual iba en la misma tabla que los criterios. **Era falso, y el fallo fue de
la comprobación, no del documento**: se buscó sobre el texto que devolvió una
descarga parcial. Con los 35 ficheros delante, `Contidos` aparece como rótulo
en **los 35**.

La estructura completa de un bloque es esta:

```
1.3 Criterios de avaliación e contidos
    Primeiro curso
    Materia de Bioloxía e Xeoloxía
    1.º curso
    Bloque 1. Proxecto científico
        Criterios de avaliación | Obxectivos    ← cabeceras de tabla
        ▪ CA1.1. Analizar e explicar…
          OBX1
        ▪ CA1.2. …
          OBX2
        Contidos
        ▪ Estratexias para a elaboración do proxecto científico:   ← agrupador
          – Formulación de preguntas, hipóteses e conxecturas.     ← item
          – Recoñecemento e utilización de fontes fidedignas.
```

Dos detalles que decidirán el extractor:

* Los contidos van a **dos niveles**: un agrupador con `▪` que termina en `:`,
  y los items con `–`. Es el mismo problema de sangrado que en Cataluña, pero
  aquí lo marca el propio carácter de viñeta, no la posición.
* **Los contidos no llevan código propio**, a diferencia del BOJA. Lo que sí
  está numerado es el bloque (`Bloque 1`), y ese número **sí es del decreto**.
  Así que el código de un contido puede ser `1.3` —bloque 1, tercer contido—
  con la parte del bloque salida de la norma. Está entre Andalucía (código
  entero oficial) y Cataluña (contador nuestro de arriba abajo).

### Los cursos vienen dentro del PDF

En **32 de los 35**, con la forma `Primeiro curso` / `1.º curso` antes de cada
tanda de bloques. No hace falta la web ni el articulado.

Los **tres** que no los declaran son materias con un currículo único para
varios cursos, y la tabla de la Guía LOMLOE sí los dice:

| Materia | Cursos, según la Guía |
|---|---|
| Cultura Clásica | 3.º y 4.º |
| Oratoria | 3.º y 4.º |
| Proxecto Competencial | 1.º a 4.º |

Es el mismo caso que «Robòtica i Programació» en Cataluña, así que hay que
tratarlo igual: una tabla de excepciones documentada con su fuente, y no
inventarlos ni dejar la materia invisible.

## Recuento, para contrastar cuando se extraiga

Contado sobre los ficheros el 16/08/2026:

* **35 PDF**, 629 páginas, 5,8 MB.
* Todos empiezan por `%PDF` y todos traen `OBX`, `CA` y `Bloque`.
* Sumando por materia: **224 obxectivos**, **912 criterios** y **161 bloques**
  distintos.

Si el extractor sale muy por debajo de esas cifras, está perdiendo algo.

## Materias (35)

De la tabla de la Guía LOMLOE, con los cursos que allí figuran:

| Grupo | Materias |
|---|---|
| Obligatorias | 16, con los cursos indicados en la web (Bioloxía 1.º y 3.º, Educación Física 1.º–4.º, etc.) |
| Diversificación | 2 ámbitos, 3.º y 4.º |
| De opción | 10, todas de 4.º |
| Optativas | 7, entre 3.º y 4.º |
