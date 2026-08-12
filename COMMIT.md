# Pendiente de commitear — tanda del 12/08

Fichero temporal: **bórralo después de commitear**. Está en la raíz, que es el
repositorio público.

---

## 1. La copia de seguridad

Ya has regenerado las 19, así que esta copia es la que merece la pena guardar:
es la primera con todas las SdA ancladas a un currículo correcto.

```powershell
powershell -ExecutionPolicy Bypass -File .\respaldar.ps1
```

Vuelca, **restaura la copia en una base de usar y tirar y compara los recuentos
de todas las tablas**. Si no cuadran, avisa en ese momento. Deja el fichero en
`..\AWEBO_backups`, fuera del árbol de git por construcción: lleva correos,
centros y hashes de contraseña. Conserva las 7 últimas.

Solo el volcado, sin verificar: `.\respaldar.ps1 -SinVerificar`. Hoy no lo
recomiendo.

---

## 2. Comprobación final

```powershell
docker compose exec api flask curriculo estado
docker compose exec api flask curriculo enlazar --simular
powershell -ExecutionPolicy Bypass -File .\verificar.ps1
```

Esperado: `RESUMEN generando=0 error=0 total=39`, ninguna «situación sin
currículo», y **825 tests en verde** (819 más los 6 de `rate_limit`).

El `enlazar --simular` de ahora sí da el dato que perseguíamos desde el
principio: **cuántos códigos se inventa GPT** con el currículo correcto
delante. Pásamelo cuando lo tengas.

---

## 3. Los commits

### Repositorio público (raíz)

```
Reasignación curricular, diagnóstico de proveedor y estado de las tareas

Reasignar las SdA ancladas a parejas curriculares inexistentes
* Las creadas antes de que el formulario validara la pareja quedaron con
  combinaciones que no existen. `flask curriculo reasignar` corrige las
  dos que tienen destino único y comprobable contra la Orden EFP/754
  —«Lengua Castellana y Literatura» a «Lengua», y «Tecnología y
  Digitalización · 4º ESO» a «Tecnología · 4º ESO»— y pregunta una por
  una las de «Matemáticas · 4º ESO»: A y B no son niveles de la misma
  asignatura sino itinerarios con currículos distintos.
* Guarda una Version con el estado anterior antes de tocar nada.
* --regenerar encola la regeneración; sin él avisa de que el contenido
  sigue citando el currículo anterior.

Seguimiento de un lote de generaciones
* `flask curriculo estado` cuenta por estado contra la base de datos, y
  `flask curriculo regenerar` relanza las que quedaron en error.
* `error_generacion` significa DOS cosas: la tarea marca ese estado y
  luego relanza para que autoretry_for la reintente. Mientras queden
  generaciones en curso el número es provisional, y regenerar entonces
  pondría dos generaciones sobre la misma SdA. El comando se planta.
* `estado` termina con una línea canónica «RESUMEN generando=N error=N
  total=N» para que los scripts no dependan de la prosa: esperar.ps1
  buscaba una frase literal y dejó de encontrarla al reescribirla.

Diagnóstico del proveedor de IA
* El proveedor sale de las preferencias del propietario de la SdA, y
  catalogo.validar cae al del sistema si el elegido no está disponible.
  Las dos vías son silenciosas y no había dónde mirarlas.
* `flask ia diagnostico` enseña, por cada SdA, su dueño, la preferencia
  guardada y el proveedor efectivo, marcando las que se ignoran.
* `flask usuarios proveedor` la cambia desde consola, que es lo único que
  sirve para cuentas heredadas cuya contraseña nadie recuerda. Valida
  contra el catálogo y avisa en vez de guardar algo que luego se ignora.

819 tests en verde.
```

### Repositorio privado (`docs/`)

```
Diario y hoja de ruta: reasignación curricular y las 19 regeneraciones

* Entrada del 12/08 con las tres parejas y por qué solo dos se deciden
  por regla.
* Entrada del desenlace: las dos causas del fallo de las 19 (cuota
  gratuita de Gemini y que esas SdA son de cuentas de prueba), y el
  estado `error_generacion` que significaba dos cosas — lo desmintieron
  los datos, no el código.
* Se marca como histórica la tabla de la tarea 11, que titulaba su
  columna «Estado hoy» y describía agosto: tres de sus cuatro filas ya
  estaban resueltas. Es el fallo que Ayuda tuvo dos veces.
* La deuda de traducciones se ajusta: la terminología curricular sí está
  contrastada desde el 11/08; las ~500 cadenas de interfaz no.
* Decisión cerrada: no se contratan traductores por ahora.
```

---

## 4. Lo que queda vivo, y no es mucho

**Una deuda real que ha quedado a la vista:** nadie verifica el correo
**principal** al registrarse. La asimetría canta ahora que el de respaldo sí se
verifica con enlace antes de contar para nada. La maquinaria de tokens ya
existe desde la tarea 11; lo que falta es decidir qué pasa mientras tanto
(¿puede usarse la cuenta sin verificar?, ¿cuánto tiempo?), y eso cambia lo que
la aplicación le exige a un docente el primer día. Es decisión tuya.

**Las ~500 cadenas de interfaz en ca/gl/eu**, que esperan a que puedas
enseñarle la plataforma a hablantes de esas lenguas. La terminología curricular
sí está contrastada contra los tres decretos y protegida por un test.

**Y las tareas 9b** (Bachillerato y FP) **y 9c** (Andalucía, Cataluña, Galicia
y País Vasco), que son lo siguiente de verdad.

Ninguna otra deuda sin dueño: lo comprobé recorriendo el código en busca de
TODO/FIXME y repasando las tres tablas de deuda de la hoja de ruta.
