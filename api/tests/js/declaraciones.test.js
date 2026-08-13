/**
 * Que ningún <script> de una plantilla declare dos veces el mismo nombre.
 *
 * POR QUÉ EXISTE
 * --------------
 * El 13/08/2026, al añadir el selector de provincia, se escribió un segundo
 * `const T = {...}` en `situaciones/nueva.html` sin ver que ya había uno
 * treinta líneas más arriba. En JavaScript eso es
 *
 *     SyntaxError: Identifier 'T' has already been declared
 *
 * y no es un error corriente: **tumba el script entero antes de ejecutar la
 * primera línea**. La página cargaba, se veía bien, y el desplegable de
 * provincia se quedaba vacío sin ninguna pista. Ni un solo test lo detectó.
 *
 * POR QUÉ NO LO CAZABA `llamadas.test.js`
 * ----------------------------------------
 * Aquel busca llamadas a funciones que no existen. Una `const` duplicada no es
 * una llamada: es un error de *sintaxis*, y el analizador nunca llegó a mirar
 * si el nombre estaba declarado dos veces porque no era su trabajo.
 *
 * Aquí se comprueba de la forma más directa posible: pedirle a Node que
 * **parsee** el script. Si tiene cualquier error de sintaxis —una `const`
 * repetida, un paréntesis suelto, una coma de más en el sitio malo—, `new
 * Function` lanza y sabemos exactamente en qué plantilla.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PLANTILLAS = path.join(__dirname, '..', '..', 'app', 'templates');

/** Scripts en línea de una plantilla, con las expresiones Jinja neutralizadas. */
function scriptsDe(rutaPlantilla) {
  const html = fs
    .readFileSync(rutaPlantilla, 'utf8')
    // `{{ _('x')|tojson }}` es un valor; cuál exactamente da igual para parsear.
    .replace(/\{\{[\s\S]*?\}\}/g, 'null')
    .replace(/\{%[\s\S]*?%\}/g, '')
    .replace(/\{#[\s\S]*?#\}/g, '');
  return [...html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1]);
}

function plantillas(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const completa = path.join(dir, e.name);
    if (e.isDirectory()) return plantillas(completa);
    return e.name.endsWith('.html') ? [completa] : [];
  });
}

let fallos = 0;
console.log('\nErrores de sintaxis en los <script> de las plantillas');

for (const ruta of plantillas(PLANTILLAS).sort()) {
  const nombre = path.relative(PLANTILLAS, ruta).replace(/\\/g, '/');
  const scripts = scriptsDe(ruta);
  if (!scripts.length) continue;

  /* Todos los <script> de una plantilla juntos, que es como los ve el
     navegador: comparten ámbito global, y por eso una `const` en el primero
     choca con otra del segundo. Analizarlos por separado no habría visto el
     fallo que motivó este fichero. */
  const src = scripts.join('\n');

  try {
    // `vm.Script` solo compila; no ejecuta nada. Ni toca el DOM ni la red.
    new vm.Script(src, { filename: nombre });
    console.log(`  OK    ${nombre}`);
  } catch (err) {
    fallos += 1;
    console.log(`  FALLA ${nombre}`);
    console.log(`          ${err.message}`);
  }
}

console.log(
  fallos === 0
    ? '\nTodo correcto.\n'
    : `\n${fallos} plantilla(s) con JavaScript que no compila.\n`
);
process.exit(fallos === 0 ? 0 : 1);
