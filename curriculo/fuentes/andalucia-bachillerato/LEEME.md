# Bachillerato de Andalucía — Orden de 30 de mayo de 2023

> **Estado: cargado y auditado el 17/09/2026.**
> **58 materias · 73 bloques · 422 competencias · 1105 criterios · 1727 saberes.**
> Las cifras de la auditoría están al final.

## La norma

* **Decreto 103/2023**, de 9 de mayo (BOJA 90, 15/05/2023): ordenación y
  currículo de Bachillerato. Es el hermano del 102/2023, que es el de la ESO.
* **Orden de 30 de mayo de 2023** (BOJA 104, de 2 de junio): **la que importa**,
  la que desarrolla el currículo.

Ojo con el nombre: **hay dos Órdenes de 30 de mayo de 2023** en el mismo
boletín, una para la ESO y otra para Bachillerato, y se distinguen por la
disposición y el CVE:

| Etapa | Disposición | CVE | Páginas |
|---|---|---|---|
| ESO | 9727 | 00284752 | 289 + 246 = 535 |
| **Bachillerato** | **9728** | **00284744** | **281 + 297 = 578** |

Por eso `comunidades.NORMAS` cita la de Bachillerato como «Orden de 30 de mayo
de 2023 **de Bachillerato**»: el título por sí solo no las separa. Sin el «de»
y entre paréntesis quedaba «Andalucía (Orden de 30 de mayo de 2023 (ESO))» en el
documento del docente, porque la procedencia ya va entre paréntesis.

## De dónde se descargan

```
https://www.juntadeandalucia.es/boja/2023/104/BOJA23-104-00281-9728-01_00284744.pdf
https://www.juntadeandalucia.es/boja/2023/104/BOJA23-104-00297-9728-02_00284744.pdf
```

Las URL salen del **índice oficial del boletín**
(<https://www.juntadeandalucia.es/boja/2023/104/s54.html>), donde cada
disposición lleva su «Descargar PDF (1 de 2)». No de un buscador: al pedirle
estos PDF a uno, devolvió los de la ESO con toda confianza.

Se bajan con `docs/scripts/descargar-andalucia.ps1 -Etapa bachillerato`.
**No se versionan**, como los de las demás comunidades.

## Lo que NO sirve, y ya está comprobado para la ESO

* **El HTML del BOJA.** La propia página avisa de que se han suprimido «todas
  las imágenes, ciertas tablas y algunos textos», y los anexos se van **sin
  dejar marcador**. Contraste: la Orden son 578 páginas y su cuerpo HTML unas
  40. Lo mismo que pasó con la ESO.
* **Los PDF de ADIDE** (`Orden30mayo2023Bachillerato-Anexo2.pdf` y compañía)
  valen para mirar, no para extraer: el texto que se carga tiene que salir del
  boletín, que es lo que un docente puede citar.

## Dónde está el currículo dentro de la Orden

Del artículo 2.2, leído en el HTML del articulado —que eso sí está completo—:

> b) En el **Anexo II** se formulan las competencias específicas, los criterios
> de evaluación y los saberes básicos para cada una de las materias comunes a
> todas las modalidades, así como de las materias específicas de cada modalidad.
>
> c) En el **Anexo III** se formulan […] para cada una de las **materias
> optativas propias de la Comunidad Andaluza**.

**Es exactamente el mismo reparto que en la ESO**, y por eso sirve el mismo
extractor. Y es también el mismo sitio donde se perdió el Anexo III andaluz
durante tres semanas: **se cargan los dos**.

## Las modalidades

Cuatro, del artículo 5.2: **Artes** —con dos vías, Artes Plásticas, Imagen y
Diseño, y Música y Artes Escénicas—, **Ciencias y Tecnología**, **General** y
**Humanidades y Ciencias Sociales**.

**No se modelan**, igual que en el País Vasco y por la misma razón: para
generar una SdA basta con curso y materia, y añadir un eje al esquema antes de
saber si hace falta es lo contrario de lo que se hizo con la etapa. Si un día
hiciera falta, la información está en los artículos 6 y 7.

## Materias según el articulado

Transcritas de los **artículos 6 y 7** de la Orden. Se anotaron antes de tener
los PDF, para saber qué buscar. Ver al final por qué no cuadran con las 58 que
salen, y por qué eso está bien.

**Primer curso — comunes (4)**: Educación Física · Filosofía · Lengua
Castellana y Literatura I · Primera Lengua Extranjera I.

**Primer curso — de modalidad (22 títulos distintos)**

| Modalidad o vía | Materias |
|---|---|
| Artes · Plásticas, Imagen y Diseño | Dibujo Artístico I · Cultura Audiovisual · Dibujo Técnico Aplicado a las Artes Plásticas y al Diseño I · Proyectos Artísticos · Volumen |
| Artes · Música y Artes Escénicas | Análisis Musical I · Artes Escénicas I · Coro y Técnica Vocal I · Lenguaje y Práctica Musical *(y Cultura Audiovisual, compartida con la otra vía)* |
| Ciencias y Tecnología | Matemáticas I · Biología, Geología y Ciencias Ambientales · Dibujo Técnico I · Física y Química · Tecnología e Ingeniería I |
| General | Matemáticas Generales · Economía, Emprendimiento y Actividad Empresarial |
| Humanidades y Ciencias Sociales | Latín I · Matemáticas Aplicadas a las Ciencias Sociales I · Economía · Griego I · Historia del Mundo Contemporáneo · Literatura Universal |

**Primer curso — optativas propias de Andalucía (8 nombradas)**: Anatomía
Aplicada · Antropología y Sociología · Creación Digital y Pensamiento
Computacional · Cultura Emprendedora y Empresarial · Educación para la
Convivencia Democrática I · Patrimonio Cultural y Artístico de Andalucía ·
Segunda Lengua Extranjera · Tecnologías de la Información y la Comunicación I.

**Segundo curso — comunes (4)**: Historia de España · Historia de la Filosofía ·
Lengua Castellana y Literatura II · Primera Lengua Extranjera II.

**Segundo curso — de modalidad (25 títulos distintos)**

| Modalidad o vía | Materias |
|---|---|
| Artes · Plásticas, Imagen y Diseño | Dibujo Artístico II · Dibujo Técnico Aplicado a las Artes Plásticas y al Diseño II · Diseño · Fundamentos Artísticos · Técnicas de Expresión Gráfico-Plástica |
| Artes · Música y Artes Escénicas | Análisis Musical II · Artes Escénicas II · Coro y Técnica Vocal II · Historia de la Música y de la Danza · Literatura Dramática |
| Ciencias y Tecnología | Matemáticas II · Biología · Dibujo Técnico II · Física · Geología y Ciencias Ambientales · Química · Tecnología e Ingeniería II |
| General | Ciencias Generales · Movimientos Culturales y Artísticos |
| Humanidades y Ciencias Sociales | Latín II · Matemáticas Aplicadas a las Ciencias Sociales II · Empresa y Diseño de Modelos de Negocio · Geografía · Griego II · Historia del Arte |

*(«Matemáticas Aplicadas a las Ciencias Sociales II» la comparten Ciencias y
Tecnología y Humanidades: cuenta una vez.)*

**Segundo curso — optativas propias de Andalucía (12 nombradas)**: Actividad
Física, Salud y Sociedad · Ciencias de la Tierra y del Medio Ambiente ·
Educación para la Convivencia Democrática II · Electrotecnia · Finanzas y
Economía · Fundamentos de Administración y Gestión · Imagen y Sonido ·
Mitología Clásica · Programación y Computación · Psicología · Segunda Lengua
Extranjera · Tecnologías de la Información y la Comunicación II.

### ⚠️ Estas cifras NO son la cota del extractor

Son **títulos del articulado**, y el anexo puede agruparlos de otra forma. Tres
motivos concretos por los que no cuadrarán tal cual, y ninguno es un fallo:

1. **«Materia de diseño propio» y «otras materias autorizadas»** salen en las
   dos listas de optativas y no tienen currículo en el anexo: las diseña el
   centro. No son extraíbles.
2. **La numeración romana puede no estar en el anexo.** En el País Vasco pasó
   exactamente eso: el articulado distingue «Matematika I» y «Matematika II»
   y el Anexo II las junta bajo un solo título con el curso dentro. Si el BOJA
   hace lo mismo, «Matemáticas I» y «Matemáticas II» saldrán como una sola
   materia con dos cursos — que es además como el extractor ya trata la ESO.
3. **«Segunda Lengua Extranjera»** aparece en los dos cursos con el mismo
   nombre. Será una materia con dos cursos, no dos materias.

La cota buena es la de siempre y hay que sacarla del PDF, no de aquí: **contar
los códigos de criterio del boletín y exigir que salgan todos**. Es lo que
encontró los 89 criterios catalanes y los 122 andaluces mutilados.

## Lo que salió, y lo que dijo la auditoría

Extraído el 17/09/2026 con `--etapa bachillerato` y estos tres tramos:

```
BOJA23-104-00281-9728-01_00284744.pdf:35:      Anexo II, primera parte
BOJA23-104-00297-9728-02_00284744.pdf:0:155    Anexo II, continuación
BOJA23-104-00297-9728-02_00284744.pdf:155:258  Anexo III
```

Las páginas **se miraron, no se supusieron**: en la ESO eran la 49 y la 16, y no
hay nada que obligue a que coincidan. El Anexo IV empieza en la 258 del segundo.

| | |
|---|---:|
| Materias | 58 |
| Bloques (materia + curso) | 73 |
| Competencias específicas | 422 |
| Criterios de evaluación | **1105** |
| Saberes básicos | **1727** |

Los cuatro contrastes, los mismos que se le pasaron a la ESO:

| Qué | Resultado |
|---|---|
| Códigos de saber del PDF que no se extraen | **0 reales** (ver más abajo) |
| Códigos extraídos que el PDF no tiene | **0** |
| Criterios que no se encuentran de una pieza | **0** de 1105 |
| Saberes que no se encuentran de una pieza | **2** de 1727, y son del boletín |
| Bloques sin competencias, criterios o saberes | **0** |

**El segundo campo del código es el curso y solo vale 1 o 2**, comprobado sobre
los 6109 códigos del anexo. Es lo que permite no transcribir a mano la tabla de
cursos, al revés que en Cataluña y el País Vasco.

### Los dos saberes que no salen de una pieza son del BOJA

`TICO.1.C.1` y `TICO.2.A.3`, las dos de Tecnologías de la Información y
Comunicación, dicen **«Sofwt are»**. Es la cursiva de *Software*, que el PDF
exporta con las letras cambiadas de orden. Aparece igual en la Guía LOMLOE
gallega, así que no es cosa de esta Orden ni del extractor.

### Y los dos códigos que «faltaban» tampoco faltan

Una auditoría por expresión regular dio dos: `MITO.2.A.4` y `EOG.2.A.4`.

* **`MITO.2.A.4` no existe.** El boletín numera los saberes de Mitología Clásica
  `A.1`, `A.2`, `A.3` y `A.5` —**salta el 4**— y luego lo cita en la columna de
  saberes de un criterio. Es una errata de la Orden, del mismo tipo que los dos
  criterios `8.3` del decreto vasco: se anota y no se inventa nada.
* **`EOG.2.A.4`** es `GEOG.2.A.4.3` con la `G` comida por el borde de la tabla,
  en la columna donde un criterio cita sus saberes. No pierde ningún saber
  —`GEOG.2.A.4` está extraído—; lo que se pierde es esa cita concreta.

### Un fallo que solo da esta Orden: el membrete como tabla

`find_tables()` detecta el membrete de la página —el logotipo «BOJA» y la
cabecera, que van en una banda con líneas— como si fuera una tabla, con un
`bbox` de (0, 39,2) a (595, 111,8). Su contenido se volcaba entre los saberes:
**55 de los 1727** llegaron con «… Arte digital. BOJA BOJA BOJA BOJA Andalucía
ju».

No lo paraba `RX_PIE`, y se intentó: el membrete sale como «BOJA BOJA», dos
palabras en el mismo renglón, y el patrón pide la línea exacta «BOJA». Se
descarta por la banda (`_ALTO_CABECERA`), que no depende de cómo agrupe las
palabras el lector. En la ESO no se notaba porque allí ninguna tabla llega tan
arriba.

### Sobre las cifras del articulado

Las materias listadas más arriba salen de los artículos 6 y 7 y **no cuadran
con las 58**, como estaba previsto: el anexo junta «Matemáticas I» y
«Matemáticas II» bajo un título con el curso dentro —igual que hace el BOPV—, y
«Materia de diseño propio» no tiene currículo porque la diseña el centro.
Sirvieron para saber qué buscar, no como cota.

## Si hay que volver a extraer

```powershell
cd api
python -m app.curriculo.extractor_boja --etapa bachillerato `
  --pdf "../curriculo/fuentes/andalucia-bachillerato/BOJA23-104-00281-9728-01_00284744.pdf:35:" `
  --pdf "../curriculo/fuentes/andalucia-bachillerato/BOJA23-104-00297-9728-02_00284744.pdf:0:155" `
  --pdf "../curriculo/fuentes/andalucia-bachillerato/BOJA23-104-00297-9728-02_00284744.pdf:155:258" `
  --salida ../curriculo/salida_andalucia_bachillerato
```

Tarda unos **dos minutos y medio**: son 504 páginas y el lector mira las rayas
que dibuja cada tabla.
