/**
 * Comprueba que el JavaScript de las plantillas no llama a funciones que no
 * existen. Desde `api/`:
 *
 *     node tests/js/llamadas.test.js
 *
 * Como el resto de tests de JS hace falta Node, y el contenedor `api` no lo
 * tiene:
 *
 *     docker run --rm -v "$PWD:/app" -w /app node:22-alpine \
 *         node tests/js/llamadas.test.js
 *
 * POR QUÉ EXISTE
 * --------------
 * `node --check` valida la **sintaxis**, y llamar a una función inexistente es
 * sintaxis perfectamente válida: el error es de ejecución. Eso permitió que
 * `situaciones/detalle.html` llamara durante un día a `escapeHtml`, que en esa
 * plantilla no está definida — ahí la función se llama `escapar`; `escapeHtml`
 * es de `listar.html`, y se coló al traducir cadenas de una a otra.
 *
 * La consecuencia no fue pequeña: cada sección con la operación «traducir»
 * lanzaba `ReferenceError` al pintarse, así que **ninguna SdA mostraba su
 * contenido**. Y no lo detectó nada — el HTML se generaba, la sintaxis pasaba,
 * y los tests de Python no ejecutan JavaScript.
 *
 * CÓMO
 * ----
 * Se leen las plantillas en crudo (Node no renderiza Jinja: las expresiones
 * `{{ … }}` se sustituyen por un valor neutro, que para este análisis da igual)
 * y se buscan las llamadas «sueltas» —`foo(`, no `obj.foo(`—. Cada nombre debe
 * estar definido en el propio script, exportado por algún fichero de
 * `static/js`, o ser un global del navegador.
 *
 * Es análisis de texto, no un intérprete, así que tiene puntos ciegos: no ve
 * un método que no existe sobre un objeto, ni una función definida en tiempo
 * de ejecución. Cubre el caso que falló, que es el más probable: un nombre mal
 * escrito o traído de otra plantilla.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const PLANTILLAS = path.join(__dirname, '..', '..', 'app', 'templates');
const ESTATICOS = path.join(__dirname, '..', '..', 'app', 'static', 'js');

/** Palabras del lenguaje que van seguidas de paréntesis y no son llamadas. */
const PALABRAS = new Set([
  'if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof',
  'new', 'await', 'delete', 'void', 'in', 'of', 'do', 'else', 'try', 'throw',
  'yield', 'case', 'with', 'super', 'async',
]);

/** Lo que aporta el navegador. Se amplía cuando haga falta, no antes. */
const GLOBALES = new Set([
  'console', 'fetch', 'alert', 'confirm', 'prompt', 'setTimeout', 'clearTimeout',
  'setInterval', 'clearInterval', 'parseInt', 'parseFloat', 'isNaN', 'String',
  'Number', 'Boolean', 'Array', 'Object', 'JSON', 'Date', 'Math', 'Promise',
  'Error', 'Map', 'Set', 'RegExp', 'Symbol', 'encodeURIComponent',
  'decodeURIComponent', 'URLSearchParams', 'FormData', 'Option',
  'requestAnimationFrame', 'structuredClone', 'queueMicrotask', 'btoa', 'atob',
  'FileReader', 'Blob', 'Intl', 'WeakMap', 'TypeError',
  // Constructores usados con `new`.
  'Event', 'CustomEvent', 'URL', 'AbortController', 'Response', 'Request',
  'Headers', 'SpeechSynthesisUtterance', 'IntersectionObserver',
  'MutationObserver',
]);

/* ------------------------------------------------------------------------ */

/**
 * Deja solo el contenido de las interpolaciones de una plantilla de cadena.
 *
 * El texto literal puede contener paréntesis —«Usar el del sistema (…)»— y
 * parecería una llamada. Lo de dentro de `${…}` sí es código, y es justo donde
 * vivía el fallo, así que no vale con descartar la plantilla entera. Se
 * recorre a mano porque un regex no sabe contar llaves anidadas.
 */
function soloInterpolaciones(src) {
  let salida = '';
  let i = 0;
  while (i < src.length) {
    if (src[i] !== '`') { salida += src[i++]; continue; }
    i++;
    while (i < src.length && src[i] !== '`') {
      if (src[i] === '\\') { i += 2; continue; }
      if (src[i] === '$' && src[i + 1] === '{') {
        i += 2;
        let profundidad = 1;
        let expresion = '';
        while (i < src.length && profundidad > 0) {
          if (src[i] === '{') profundidad++;
          else if (src[i] === '}') { profundidad--; if (!profundidad) break; }
          expresion += src[i++];
        }
        salida += ` ${expresion} `;
        i++;
        continue;
      }
      i++;   // texto literal: se descarta
    }
    i++;
  }
  return salida;
}

/**
 * El ORDEN de estos pasos importa, y equivocarlo deja el test sin comprobar
 * nada. Una primera versión quitaba los literales entre comillas antes de
 * procesar las plantillas de cadena, y en
 *
 *     ` title="${escapeHtml(interpolar(...))}"`
 *
 * el par de comillas dobles se «cerraba» alrededor de la interpolación
 * entera: la llamada desaparecía y el test daba el visto bueno al fallo que
 * existe para detectar. Se comprobó reintroduciéndolo a propósito.
 *
 * Primero las plantillas de cadena, después las comillas.
 */
function limpiar(src) {
  const sinComentarios = src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
  return soloInterpolaciones(sinComentarios)
    .replace(/'(?:[^'\\\n]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\\n]|\\.)*"/g, '""');
}

/** Nombres que este trozo de código define. */
function definidos(src) {
  const d = new Set();
  const añade = (n) => { if (/^[A-Za-z_$][\w$]*$/.test(n)) d.add(n); };

  for (const m of src.matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)/g)) añade(m[1]);
  for (const m of src.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) añade(m[1]);
  for (const m of src.matchAll(/\b(?:const|let|var)\s*\{([^}]*)\}/g)) {
    m[1].split(',').forEach((p) => añade(p.split(':').pop().trim()));
  }
  // Parámetros: de función y de flecha, con y sin paréntesis.
  for (const m of src.matchAll(/\(([^()]*)\)\s*(?:=>|\{)/g)) {
    m[1].split(',').forEach((p) => añade(p.trim().split(/[=\s]/)[0].replace(/^\.\.\./, '')));
  }
  for (const m of src.matchAll(/([A-Za-z_$][\w$]*)\s*=>/g)) añade(m[1]);
  // Exportaciones a la ventana desde los ficheros de static/js.
  for (const m of src.matchAll(/\b(?:window|global)\.([A-Za-z_$][\w$]*)\s*=/g)) añade(m[1]);
  return d;
}

/** Llamadas «sueltas»: `foo(`, no `obj.foo(`. Devuelve nombre → línea. */
function llamadas(src) {
  const usos = new Map();
  for (const m of src.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/g)) {
    const nombre = m[2];
    if (PALABRAS.has(nombre) || usos.has(nombre)) continue;
    usos.set(nombre, (src.slice(0, m.index).match(/\n/g) || []).length + 1);
  }
  return usos;
}

/** Scripts en línea de una plantilla, con las expresiones Jinja neutralizadas. */
function scriptsDe(rutaPlantilla) {
  const html = fs.readFileSync(rutaPlantilla, 'utf8')
    // `{{ _('x')|tojson }}` es un valor; qué valor exactamente da igual aquí.
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

/* ------------------------------------------------------------------------ */

// Lo que exportan los ficheros de static/js está disponible en cualquier
// plantilla que los cargue. No se comprueba cuál carga cuál: sería más
// estricto, pero un falso positivo en este test cuesta más de lo que aporta.
const delProyecto = new Set();
for (const fichero of fs.readdirSync(ESTATICOS).filter((f) => f.endsWith('.js'))) {
  definidos(limpiar(fs.readFileSync(path.join(ESTATICOS, fichero), 'utf8')))
    .forEach((n) => delProyecto.add(n));
}

let fallos = 0;
console.log('\nLlamadas a funciones inexistentes');

for (const ruta of plantillas(PLANTILLAS).sort()) {
  const nombre = path.relative(PLANTILLAS, ruta).replace(/\\/g, '/');
  const scripts = scriptsDe(ruta);
  if (!scripts.length) continue;

  const src = limpiar(scripts.join('\n'));
  const disponibles = new Set([...definidos(src), ...delProyecto, ...GLOBALES]);
  const huerfanas = [...llamadas(src)].filter(([n]) => !disponibles.has(n));

  if (huerfanas.length === 0) {
    console.log(`  OK    ${nombre}`);
  } else {
    fallos += huerfanas.length;
    console.log(`  FALLA ${nombre}`);
    huerfanas.forEach(([n, l]) => console.log(`          línea ~${l}: ${n}(…) no está definida`));
  }
}

console.log(fallos === 0
  ? '\nTodo correcto.\n'
  : `\n${fallos} llamada(s) a funciones que no existen.\n`);
process.exit(fallos === 0 ? 0 : 1);
