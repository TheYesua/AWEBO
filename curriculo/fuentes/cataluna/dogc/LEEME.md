# No extraigas de estos PDF

Son los boletines completos del DOGC y contienen los anexos, así que la
tentación es usarlos. **La fuente tiene el mapa de caracteres desplazado 29
posiciones** en parte del texto:

* Poppler (`pdftotext`) **borra** el glifo que no sabe traducir: «efica i
  creati a» donde el decreto dice «eficaç i creativa».
* PyMuPDF lo **sustituye** por la letra equivocada: `Y`→`v`, `M`→`j`, `Z`→`w`,
  `\x11`→`.`. Comprobado, exacto, y verificable cruzando cada palabra rota con
  las que el propio documento escribe bien: `Y→v` sale 421 veces de 428.

Lo que impide repararlo con una tabla: **los acentuados no siguen la regla**.
`ò` se lee `z` y `ç` se lee `o`, o sea que `pròpies` sale `przpies` y `eficaç`
sale `eficao`. Son minúsculas dentro de palabras que parecen palabras: no se
detectan solas y no se pueden contar. Una reparación arreglaría lo visible y
dejaría dentro lo que no se ve.

Los PDF de `../xtec/` son otra generación del mismo texto y **no tienen el
fallo**. Se extrae de ahí.

Estos se conservan solo como respaldo de la fuente oficial.
