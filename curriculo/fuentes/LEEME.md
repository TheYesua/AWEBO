# Fuentes del currículo, una carpeta por comunidad y etapa

El nombre de cada carpeta es el **código canónico** de
`app/curriculo/comunidades.py` —`cataluna`, `ceuta`…—, no el nombre para
mostrar. Ese código es el que va en la columna `comunidad` de las tres tablas de
currículo, así que la carpeta y la fila de la base de datos se llaman igual y no
hay que traducir entre las dos. Las de Bachillerato llevan el sufijo de la etapa.

`estatal/` no es una comunidad: es el Real Decreto de enseñanzas mínimas, que no
desarrolla ningún currículo autonómico pero es del que cuelgan todos.

## Dónde están los ficheros, y dónde no

| Qué | Dónde vive | Por qué |
|---|---|---|
| Los **XML** (4 ficheros, pequeños) | en el repositorio público, aquí | pesan poco y sin ellos no se puede reproducir la carga de Ceuta ni la del estatal |
| Los **PDF** (292, 148 MB) | en el repositorio privado **`awebo_fuentes`**, clonado en esta misma carpeta | no caben en el público, y GitHub rechaza ficheros de más de 100 MB |
| Los `LEEME.md` de cada carpeta | en el repositorio público | dicen de dónde descargar cada boletín, que es justo lo que necesita quien clone sin acceso al privado |

**No pongas aquí un `.gitignore` ni un `.gitattributes`.** Un fichero de
configuración de git en esta carpeta lo lee **también** AWEBO, que la contiene, y
sus reglas se aplican a los dos repositorios a la vez. Ha roto cosas en los dos
sentidos: el 16/08/2026 un `!*.pdf` expuso los PDF al repositorio público, y
hasta el 23/09/2026 un `*.pdf` impidió añadir 56 boletines a `awebo_fuentes`,
que existe exactamente para guardarlos. Lo que quiera excluir solo uno de los dos
va en su `.git/info/exclude`, que es local. Lo vigila
`test_las_fuentes_no_llevan_configuracion_de_git_propia`.

## El mapa

```
estatal/                  rd_217_2022.xml          RD 217/2022, enseñanzas mínimas

ceuta/                    orden_efp_754_2022.xml   Orden EFP/754/2022, ESO
ceuta-bachillerato/       orden_efp_755_2022.xml   Orden EFP/755/2022, Bachillerato.
                                                   Hermana de la anterior —consecutivas
                                                   y del mismo día— y aun así con el
                                                   Anexo II maquetado de otra forma.
                                                   Viene de la API de consolidada, así
                                                   que trae otro envoltorio.

cataluna/                 decret_175_2022.xml      Akoma Ntoso del Portal Jurídic.
                                                   Trae el ARTICULADO, no el currículo.
          dogc/           2 PDF                    Boletines completos: contienen los
                                                   anexos, pero con la codificación de
                                                   fuente rota. NO extraer de aquí.
                                                   Ver el LEEME de la carpeta.
          xtec/           24 PDF                   Un PDF por materia, de la XTEC.
                                                   **Esta es la fuente buena de la ESO.**
cataluna-batxillerat/     79 PDF                   XTEC, Bachillerato. Decret 171/2022
                                                   con la modificación del 103/2026.

andalucia/                4 PDF                    BOJA núm. 104, Orden de 30/05/2023,
                                                   ESO. Anexos II y III.
andalucia-bachillerato/   2 PDF                    La otra Orden de 30/05/2023, la de
                                                   Bachillerato.

galicia/                  35 PDF                   Decreto 156/2022, un PDF por materia
                                                   de la Guía LOMLOE de la Xunta.
galicia-bachillerato/     54 PDF                   Decreto 157/2022, hermano del anterior
                                                   y del mismo día. Misma maquetación,
                                                   así que mismo extractor con --etapa.

pais-vasco/               33 PDF                   Decreto 77/2023 (BOPV), ESO.
pais-vasco-bachillerato/  59 PDF                   Decreto 76/2023 (BOPV), Bachillerato.
```

**De dónde se baja cada uno está en el `LEEME.md` de su propia carpeta**, con la
URL y las particularidades del boletín. Aquí no se repite: una lista de URLs en
dos sitios se desfasa en uno de los dos, y este fichero ya se quedó una vez
describiendo tres comunidades cuando había cinco.

Los guiones de descarga están en `docs/scripts/`, dentro del repositorio privado
`awebo_docs`.
