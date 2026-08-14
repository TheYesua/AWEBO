# Fuentes del currículo, una carpeta por comunidad

El nombre de cada carpeta es el **código canónico** de `app/curriculo/comunidades.py`
—`cataluna`, `ceuta`…—, no el nombre para mostrar. Ese código es el que va en la
columna `comunidad` de las tres tablas de currículo, así que la carpeta y la fila
de la base de datos se llaman igual y no hay que traducir entre las dos.

`estatal/` no es una comunidad: es el Real Decreto de enseñanzas mínimas, que no
desarrolla ningún currículo autonómico pero es del que cuelgan todos.

```
estatal/   rd_217_2022.xml            RD 217/2022, enseñanzas mínimas
ceuta/     orden_efp_754_2022.xml     Orden EFP/754/2022, Ceuta y Melilla
cataluna/  decret_175_2022.xml        Akoma Ntoso consolidado del Portal Jurídic.
                                      Trae el ARTICULADO, no el currículo.
           dogc/                      Boletines completos en PDF. Contienen los
                                      anexos, pero con la codificación de fuente
                                      rota: NO extraer de aquí. Ver LEEME de la
                                      carpeta.
           xtec/                      Un PDF por materia, publicados por la XTEC.
                                      **Esta es la fuente buena.**
```

Los PDF están en el `.gitignore` por tamaño. De dónde se bajan:
https://xtec.gencat.cat/ca/curriculum/eso/curriculum-175-2022/
