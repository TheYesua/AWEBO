# ESO de Cataluña — Decret 175/2022, un PDF por materia

**Esta es la fuente buena del currículo catalán de ESO**, y esta nota faltaba: la
carpeta llevaba 24 PDF sin decir de dónde salían, mientras que `../dogc/` —que es
la fuente *mala*— sí lo explicaba. Lo detectó
`test_cada_carpeta_con_pdf_dice_de_donde_bajarlos` el 24/09/2026.

Importa porque los PDF **no están en el repositorio público**: sin esta URL,
quien clone sin acceso a `awebo_fuentes` no puede reproducir esta carga.

## De dónde salen

De la **XTEC**, el portal de la Generalitat, un PDF por materia:

<https://xtec.gencat.cat/ca/curriculum/eso/curriculum-175-2022/>

## Por qué no se extrae del DOGC, que también trae los anexos

Porque sus PDF tienen **el mapa de caracteres desplazado** y pierden o sustituyen
letras sin que se pueda detectar. Está medido y explicado en
[`../dogc/LEEME.md`](../dogc/LEEME.md), que merece leerse antes de tener la idea
de «usar el boletín oficial, que es más fiable». Estos de la XTEC son otra
generación del mismo texto y no tienen el fallo.

## Lo que hay

24 PDF. El articulado va aparte, en `../decret_175_2022.xml`: el Akoma Ntoso del
Portal Jurídic trae la norma pero **no el currículo**, que está en el Annex 3.

| | ESO | Bachillerato |
|---|---|---|
| Norma | Decret **175**/2022 | Decret **171**/2022 (+ 103/2026) |
| Anexo con el currículo | **Annex 3** | Annex 2 |
| Carpeta | `cataluna/xtec/` (esta) | `cataluna-batxillerat/` |

## Dos cosas que costaron criterios, y las dos están vigiladas

* **Los saberes de nueve materias se cargaban duplicados.** Su epígrafe viene
  partido por curso y los dos tramos se llevaban los dos juegos. Salió al volver
  al extractor para el Bachillerato, semanas después de la carga inicial.
* **Las tablas de criterios cruzan de página sin repetir la cabecera**, y el
  extractor cortaba el cuerpo comparando solo la coordenada vertical —que en la
  página siguiente vuelve a empezar por arriba—. Se perdían **18 criterios de la
  ESO** (y 67 de Bachillerato) sin ningún error. Ahora hay un test que cuenta en
  cada PDF las líneas que empiezan por un código de criterio y las compara con
  las extraídas.

## Los PDF no están en el repositorio público

Pesan, y van en el `.gitignore` de la raíz; los versiona el privado
`awebo_fuentes`. Sin ellos, los tests del extractor **se saltan** en lugar de
fallar.
