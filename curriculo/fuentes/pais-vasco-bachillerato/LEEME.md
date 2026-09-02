# Bachillerato del País Vasco — Decreto 76/2023

**Norma:** Decreto 76/2023, de 30 de mayo (BOPV núm. 109, 09/06/2023), de
establecimiento del currículo de **Bachillerato** e implantación en la
Comunidad Autónoma de Euskadi. Con **corrección de errores** del 24/07/2023.

Es el decreto hermano del 77/2023, que es el de Educación Básica y del que sale
el currículo de ESO en `../pais-vasco/`.

## En euskera, por lo mismo

Misma decisión que en la ESO: se carga la versión en euskera porque es la que
el docente vasco cita en su programación. En los ficheros de Berrigasteiz el
sufijo `_e` es *euskaraz* y `_c` castellano.

## De dónde se descarga

De **Berrigasteiz**, con el mismo script que la ESO:

```powershell
docs\scripts\descargar-pais-vasco.cmd -Etapa bachillerato
```

<https://www.berrigasteiz.com/monografikoak/ec22/etapa_batxilergoa/>

Y por las mismas dos razones: publica **un PDF por materia** y su copia del
decreto lleva **la corrección de errores ya incorporada** (`_ZUZENDUTA`).

**No se versionan** (`.gitignore`), como los de las demás comunidades.

## Comprobado sobre el decreto (28/08/2026)

* **493 páginas** y **monolingüe en euskera**: ninguna con cabecera castellana.
* **El Anexo II ocupa de la página 40 a la 488** — 449 páginas — y es el del
  currículo por materia. Ojo: en la ESO era el **III**; aquí es el **II**.
* Los anexos van así: I perfil de salida (p27), **II currículo** (p40),
  III situaciones de aprendizaje (p489), IV (p492), V horarios (p493).
* **65 materias**, más del doble que las 30 de la ESO. Contadas y
  contrastadas: ver más abajo.
* Estructura idéntica a la de la ESO: título de materia en mayúsculas, y
  dentro `KONPETENTZIA ESPEZIFIKOAK`, `EBALUAZIO-IRIZPIDEAK` y
  `OINARRIZKO JAKINTZAK`.
* **Menos tablas**: 56 de 449 páginas, frente a 69 de 226 en la ESO. La mayor
  parte va en texto corrido.
* La única cabecera de curso que aparece es «**Bigarren maila**», en 42
  páginas: son las materias que se dan en los dos cursos y separan el currículo
  del segundo. Los cursos del resto habrá que sacarlos del articulado
  (artículos 11 a 15), como en Cataluña.

## Los PDF por materia van por modalidad

El portal los reparte en carpetas, una por bloque del articulado:

| Carpeta | Qué lleva |
|---|---|
| `jakitzagaiak_amankomunak/` | Materias comunes (art. 11) |
| `jakitzagaiak_orokorra/` | Modalidad General (art. 14) |
| `jakitzagaiak_giza/` | Humanidades y Ciencias Sociales (art. 15) |
| `jakitzagaiak_aukerakoak/` | Optativas |

**`jakitzagaiak` va sin la «n»**, y es del portal, no una errata de este
documento. Corregirlo en el script deja el filtro sin encontrar ni un fichero.

Los nombres son del tipo `1.1.batxi_matematika_orokorrak_e.pdf`: empiezan por
un número de orden, al revés que en la ESO —`DBH8_natur_zientziak_e.pdf`—.

## El contraste, y cuadra al dígito (29/08/2026)

**65 materias en el Anexo II y 65 con fichero.** Así sale la cuenta, y las dos
correcciones importan tanto como el resultado:

```
72 títulos en mayúsculas encontrados en el Anexo II
 −6  bloques de saberes de «Kultura Zientifikoa» (ver abajo)
 −1  «EGUNGO MUNDUAREN GATAZKAK…» va partido en dos líneas y contaba doble
 =65

58 PDF descargados
 +7 con el enlace roto en el portal, que sí son materias del anexo
 =65
```

**Siete enlaces del portal están rotos** —devuelven 404— y sus materias sí
están en el decreto: Mekanika, Euskal Herriko Historia, Kultura Zientifikoa,
Elektronika, Laborategiko Teknikak, Anatomia Aplikatua y Lurraren eta
Ingurumenaren Zientziak. **No importa para extraer**, porque se extrae del
decreto completo; solo importaba para este contraste, y por eso se cuentan.

*(El octavo fallo, `_BATXI_ikaskuntza_zerbitzua_e.pdf`, no es una materia:
es aprendizaje-servicio.)*

## Una sexta forma de marcar los bloques de saberes

En «Kultura Zientifikoa» (p438) los bloques van **en MAYÚSCULAS y sin letra ni
número** delante:

```
OINARRIZKO JAKINTZAK
Kultura Zientifikoa
ZER JATEN DUGU?
    Elikagai funtzionalak: Omega 3, bifidus, lactobacillus…
ZAHARTZEA
    ...
```

Son seis: `ZER JATEN DUGU?`, `ZAHARTZEA`, `INGENIARITZA GENETIKOA`, `OSASUNA
ETA MEDIKAMENTUAK`, `MUNDU JASANGARRIAGO BAT: MUNDU HOBEA?` y `ERRONKA
ZIENTIFIKOAK ETA ETORKIZUNERAKO LEHENTASUNAK`.

**El extractor los tomaría por materias**, que es como se descubrieron: sin
letra ni número no casan con ninguna de las cinco formas conocidas, y en
mayúsculas se parecen a un título. Y no se distinguen de una materia por el
texto —`ZAHARTZEA` es una palabra suelta como `BOLUMENA`, que sí lo es—, así
que habrá que distinguirlos por el estado: dentro de `OINARRIZKO JAKINTZAK` un
título en mayúsculas no puede ser una materia nueva.

## Seis ficheros que NO son currículo

El primer rastreo se los trajo, y conviene tenerlos identificados:

```
batxilergoa_5_art_printzipio_orokorrak_e.pdf     artículo 5
batxilergoa_6_art_printzipio_pedagogikoak_e.pdf  artículo 6
batxilergoa_8_art_hizkuntza_markoa_e.pdf         artículo 8
batxilergoa_25_art_tutoretza_orientazioa_e.pdf   artículo 25
batxilergoa_SARRERA_ildo_estrategikoak_e.pdf     introducción
batxilergoa_eranskin_I_erronkak_e.pdf            Anexo I
```

Son extractos del articulado y del Anexo I, útiles para leer pero no currículo.
**Se pueden borrar.** El script ya no los baja: el filtro pasó a mirar la
carpeta en vez del prefijo del nombre, que es lo que de verdad los distingue.

## Lo que queda por comprobar

Nada de esto está verificado todavía:

1. **De dónde salen los cursos** de las materias que no declaran «Bigarren
   maila». Los artículos 11 a 15 reparten las materias en comunes y por
   modalidad, pero está por ver si dicen el curso.
2. **Si las modalidades hacen falta en el modelo.** De momento no se guardan:
   para generar una SdA bastan curso y materia. La carpeta del portal las
   distingue, así que el dato estaría disponible si luego hiciera falta.
3. ~~Si hay **materias con el título partido en dos líneas**.~~ **Sí hay una**,
   confirmada al contrastar: «EGUNGO MUNDUAREN GATAZKAK ETA ERREALITATEAK, ETA
   KOMUNIKABIDEEKIN ETA SARE SOZIALEKIN DUTEN ERLAZIOA» (p399). Es el mismo
   caso que los ámbitos de Galicia, donde el título partido hizo que se
   cargaran con el nombre «obrigatoria».
