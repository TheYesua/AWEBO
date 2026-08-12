# Commits pendientes

Fichero temporal de trabajo: **bórralo después de commitear**. Está en la raíz,
que es el repositorio público, así que no debe quedarse.

---

## Repositorio público (raíz)

Todo lo de `api/`, más `CLAUDE.md` (solo el puntero, sin reglas).

```
Tarea 13, deuda saldada y correos en el idioma de la interfaz

Tarea 13 — correo de respaldo y reclamación verificada
* Correo de respaldo opcional: se ofrece al registrarse y se gestiona
  desde el perfil. Cambiarlo exige confirmar desde el respaldo ANTERIOR,
  que es lo que impide que quien entre en una cuenta pueda apropiársela.
* La reclamación de contenido la autoriza el respaldo de la cuenta
  original, no la dirección en disputa. Sin respaldo decide el
  administrador, como hasta ahora.
* Restablecer la contraseña acepta también el correo de respaldo, sin
  romper la indistinguibilidad de la respuesta.
* La dirección se muestra enmascarada: es lo único que tener la sesión
  no da, así que enseñarla entera le daría a quien robe una sesión el
  siguiente objetivo.
* Migración d1a7f36c8b95.

Correos en el idioma de la interfaz
* Los cuatro correos salen en el idioma que tenga la página al pedirlos,
  asunto incluido. No hacía falta guardar el idioma por cuenta: el texto
  se compone en la petición y solo se entrega desde el worker.

Enlaces curriculares
* Las SdA se enlazan con las filas reales del catálogo al guardarse,
  filtrando por materia Y curso. Los códigos no son únicos.
* Los códigos que la IA se inventa quedan registrados aparte de las SdA
  cuya pareja (materia, curso) no existe en el catálogo: son causas
  distintas y confundirlas falsea la medida.
* Se retira la relación situacion_ods: ningún prompt pide ODS, así que
  era una consulta garantizada a vacío en cada carga. Tabla y catálogo
  se conservan.
* Nuevo comando: flask curriculo enlazar [--simular].

Acceso del administrador
* Puede leer cualquier contenido, y ahora va acompañado de las tres
  piezas con las que se aceptó: se dice en Ayuda, se advierte en el
  registro antes del botón, y cada acceso a contenido ajeno deja traza.

Traducciones
* Terminología curricular contrastada contra los decretos autonómicos en
  su propia lengua. Corregido en euskera: ikaskuntza-egoerak (con guion,
  77/2023 Dekretua) y aniztasunari erantzutea.
* 528 cadenas en es/ca/gl/eu, sin vacías ni fuzzy.

756 tests en verde.
```

---

## Repositorio privado (`docs/`)

```
Diario y hoja de ruta de la tarea 13, la deuda y dos reglas nuevas

* Tarea 13 cerrada en la hoja de ruta, con las tres dudas que quedaban
  abiertas resueltas y anotadas.
* Deuda: no queda ninguna entrada sin dueño. Se retira «la reclamación no
  verifica la identidad» de las aceptadas —la tarea 13 la resolvió— y se
  cierra la de las cuatro tablas de enlace.
* Se corrige la contradicción entre «gestión sin lectura» y la decisión
  del 10/08.
* Regla 11: «importa» no es «funciona». Un comando de CLI comprobado solo
  con `import` salió roto en la primera ejecución real.
* Regla 12: un síntoma observado no es una causa demostrada. El comando
  anunció 17 SdA como códigos inventados por el modelo; ninguna lo era.
* Estado actual del código medido, no estimado.
```

---

## Antes de commitear

* `powershell -ExecutionPolicy Bypass -File .\verificar.ps1` → 747 en verde.
* Los `.mo` van al commit: Flask-Babel lee `.mo`, no `.po`, y un catálogo sin
  recompilar deja la interfaz en castellano sin dar ningún error.
* `docs/` está en el `.gitignore` de la raíz, así que sus cambios solo entran
  en el repositorio privado. Comprobado.
* `scratch/dump.sql` sigue ignorado: lleva correos y hashes.

---

## Lo que queda pendiente de TU decisión

**17 de las 39 SdA están ancladas a parejas (materia, curso) que no existen en
el catálogo.** Son anteriores a que el formulario validara la pareja:

| Pareja | Por qué no existe | SdA |
|---|---|---|
| `Matemáticas · 4º ESO` | En 4º hay Matemáticas A y Matemáticas B | 13, 33, 34, 41, 42, 49, 50 |
| `Tecnología y Digitalización · 4º ESO` | Solo se imparte en 2º y 3º | 30, 37, 38, 46 |
| `Lengua Castellana y Literatura · 4º ESO` | En el catálogo la materia se llama `Lengua` | 31, 32, 39, 40, 47, 48 |

Ninguna tiene códigos inventados: con la pareja sin currículo, ningún código
puede casar. Las opciones son renombrar la materia, repartir las de Matemáticas
entre A y B, o dejarlas como están. Cambia lo que la aplicación le afirma a un
docente, así que lo decides tú.

Lo de `Lengua` lo comprobé antes de escribirlo: no es un recorte del extractor,
es un mapeo deliberado a la etiqueta histórica, documentado en
`_MATERIAS_ORDEN_754`. El catálogo está bien; lo que está desfasado es el
nombre guardado en esas seis SdA.
