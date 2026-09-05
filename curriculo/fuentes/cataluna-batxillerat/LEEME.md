# Bachillerato de Cataluña — Decret 171/2022, modificado por el 103/2026

Currículo LOMLOE de **batxillerat** en catalán. Carpeta aparte de `cataluna/`
por lo mismo que `pais-vasco-bachillerato/`: son **dos decretos distintos** y
mezclarlos haría imposible saber de cuál sale cada fichero.

| | ESO | Bachillerato |
|---|---|---|
| Norma | Decret **175**/2022 | Decret **171**/2022, de 20 de setembre |
| Modificación en vigor | — | **Decret 103/2026, de 7 de juliol** (desde 2026-2027) |
| Anexo con el currículo | Annex 3 | **Annex 2** |
| Carpeta | `cataluna/` | `cataluna-batxillerat/` (esta) |

## De dónde salen

De la **XTEC**, un PDF por materia, igual que la ESO:

<https://xtec.gencat.cat/ca/curriculum/batxillerat/curriculum-171-2022/>

Y por la misma razón que en la ESO: **los PDF del DOGC traen la codificación de
fuente rota** —pierden o sustituyen letras acentuadas sin que se pueda
detectar—, así que no se extrae de ahí.

Se bajan con `docs/scripts/descargar-cataluna-batxillerat.ps1`.

## El Decret 103/2026 cambia el reparto por curso, y eso importa aquí

El 22 de diciembre de 2025 el Departament anunció la modificación del Decret
171/2022, publicada como **Decret 103/2026, de 7 de juliol**. Lo que cambia y
afecta a esta carga:

* En **1.º** desaparecen «Biologia», «Física», «Química» y «Geologia i Ciències
  Ambientals» por separado: se unifican en **«Biologia, Geologia i Ciències
  Ambientals»** y **«Física i Química»**. Las cuatro sueltas quedan **solo en
  2.º**.
* Se renombra «Llengua i Cultura Llatines» como **«Llatí»** y «Llengua i
  Cultura Gregues» como **«Grec»**.

**Se aplica desde el curso 2026-2027**, que es el vigente. Por eso el reparto
por curso **no se toma del articulado del 171/2022** —que sigue publicado como
«text aprovat pel Govern» y da el reparto anterior— sino del documento del
Departament que concreta el currículo del curso en vigor:

> «Concreció i desenvolupament del currículum del batxillerat» (DOIGC),
> apartados 1.2, 1.3.1, 1.3.2, 1.3.3 y 1.3.4.
> <https://documents.espai.educacio.gencat.cat/IPCNormativa/DOIGC/CUR_Batxillerat.pdf>

La tabla transcrita vive en `api/app/curriculo/xtec_etapas.py`.

## Lo que hay: 79 PDF, 73 materias

El portal reparte las materias en diez páginas, que el script recorre:

| Sección | PDF |
|---|---:|
| Matèries comunes | 6 |
| Matèries obligatòries de modalitat | 8 |
| Modalitat · arts plàstiques, imatge i disseny | 7 |
| Modalitat · música i arts escèniques | 7 |
| Modalitat · ciències i tecnologia | 8 |
| Modalitat · general | 2 |
| Modalitat · humanitats i ciències socials | 11 |
| Optatives anuals de 1r | 15 |
| Optatives trimestrals de 1r | 13 |
| Optatives trimestrals de 2n | 2 |
| **Total** | **79** |

De 79 ficheros salen **73 materias**, y la cuenta es esta:

* **−6 por duplicados de sección.** Cinco materias sirven a más de una
  modalidad y el portal publica un PDF por sección: «Anàlisi Musical», «Arts
  Escèniques», «Cultura Audiovisual» y «Matemàtiques Aplicades a les Ciències
  Socials» van dos veces, y «Estada a l'Empresa» tres. Se comprobó con un
  diff: **los ficheros son idénticos byte a byte**, así que el extractor se
  queda con el primero y lo dice en el registro.
* **−1 por edición anterior.** «Llengua i Cultura Llatines» y «Llatí» son el
  mismo currículo con el nombre que cambió el Decret 103/2026 —difieren en 276
  caracteres, y todos son la sustitución del nombre dentro del texto—. Se carga
  con el nombre vigente. Ojo si se quita esa regla: por orden alfabético
  ganaría la versión vieja.
* **+1 porque un PDF trae dos materias.** «Llengua Castellana i Literatura» y
  «Llengua Catalana i Literatura» comparten un solo currículo y un solo
  fichero, con los dos títulos en la portada.

## Veintidós materias sin criterios ni saberes, y no es un fallo de lectura

Veintidós optativas traen **solo competencias específicas**. Su propio PDF lo
dice: «El professorat establirà els criteris d'avaluació per a cadascuna de les
competències específiques i seleccionarà els sabers…». Cargarlas así es lo
correcto; inventarles criterios, no. La lista está fijada entera en
`test_las_que_no_traen_criterios_son_las_que_el_decreto_deja_abiertas`, para que
si mañana una materia con currículo completo se queda sin criterios, salte.

## Cuatro rarezas del portal, y ninguna es un error nuestro

1. **Doble extensión.** Ocho ficheros se sirven como `Biologia.pdf.pdf` y cinco
   con la extensión del original de Word, `Psicologia.docx.pdf`. Las URL son
   esas: «arreglarlas» da 404. El script las respeta y limpia solo el nombre
   con el que guarda.
2. **Un fichero fechado.** «Funcionament de l'Empresa i Disseny de Models de
   Negoci» se sirve como `20230504_Funcionament-…`, con la fecha de una
   revisión delante. Solo ese.
3. **Programaciones mezcladas con el currículo.** Ocho PDF de «Programació de
   situacions d'aprenentatge» cuelgan de las mismas páginas que las optativas.
   Son ejemplos de programación didáctica, **no currículo**, y el script los
   descarta: cargarlos daría materias que no existen.
4. **Dos maquetaciones conviviendo.** Los doce PDF reeditados tras el Decret
   103/2026 —las diez de ciencias, Grec y Llatí— llevan otra plantilla: sin pie
   con el decreto, con el epígrafe «Sabers» en negrita del mismo cuerpo que el
   texto, con la viñeta de cada saber pegada al renglón en vez de sangrada, y
   con la negrita derramada sobre la primera línea de cada bloque. El extractor
   los reconoce; está explicado en `extractor_xtec._extraer_saberes`.
5. **Las tablas de criterios cruzan de página sin repetir la cabecera.** No es
   raro en sí, pero es lo que más criterios costó: el extractor cortaba el
   cuerpo de la tabla comparando solo la coordenada vertical, y en la página
   siguiente esa coordenada vuelve a empezar por arriba. **67 criterios de
   Bachillerato** —y 18 de la ESO— se quedaban fuera sin dar ningún error. Se
   detectó contando en el PDF las líneas que empiezan por un código de criterio
   y comparándolas con las extraídas; ahora hay un test que lo exige fichero a
   fichero.
6. **«Química» sangra al revés que todas.** Su subbloque va **más a la
   derecha** que el saber: el título del subbloque a x≈103 y los saberes al
   margen, a x≈85. Si se da por hecho que el nivel más profundo es el del
   saber, se cargan los doce títulos de subbloque como si fueran los saberes y
   se pierden los cuarenta y cinco de verdad. Lo que los distingue es la marca:
   el saber lleva guion y el subbloque, «•».

## Las optativas trimestrales son un caso nuevo

Cataluña tiene optativas **de un trimestre**, que ninguna otra comunidad
cargada tiene. En el modelo no cambian nada —siguen siendo materia y curso—,
pero conviene saberlo antes de extrañarse de que «Robòtica» tenga un currículo
tan corto comparado con una materia anual.

Las tres optativas de ODS de 2.º —«Entorn Sostenible», «Població i Prosperitat»
y «Pau, Justícia i Corresponsabilitat»— **no son tres materias**: el decreto
publica un solo currículo, «Objectius de Desenvolupament Sostenible (ODS)», con
esas tres como bloques temáticos. Se carga como una.

## Los PDF no están en el repositorio

Pesan y van en el `.gitignore` del repositorio público; los versiona el privado
de fuentes. Sin ellos, los tests del extractor se saltan en vez de fallar.
