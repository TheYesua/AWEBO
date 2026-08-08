/**
 * Comprueba que el JavaScript de las plantillas no tiene texto en castellano
 * sin marcar para traducción. Desde `api/`:
 *
 *     node tests/js/traducibles.test.js
 *
 * Como el resto de tests de JS hace falta Node, y el contenedor `api` no lo
 * tiene:
 *
 *     docker run --rm -v "E:\AWEBO\api:/app" -w /app node:22-alpine \
 *         node tests/js/traducibles.test.js
 *
 * POR QUÉ EXISTE
 * --------------
 * La tarea 6 se dio por cerrada diciendo que la aplicación estaba «traducida
 * al 100 %». No lo estaba. `pybabel extract` recorre las plantillas buscando
 * `_()`, así que una cadena escrita a pelo dentro de un `<script>` no aparece
 * en el `.pot`: no es que falte su traducción, es que **nadie sabe que existe
 * esa cadena**. No hay ningún aviso, ni al extraer, ni al compilar, ni al
 * renderizar.
 *
 * Se descubrió el 7/8/2026 documentando el centro de ayuda, al ir a describir
 * los botones «Resumir», «Desarrollar» y «Traducir» y encontrarlos escritos en
 * castellano dentro del JavaScript. Con la interfaz en euskera, la pantalla de
 * detalle enseñaba esos botones y toda la comparación de propuestas en
 * castellano.
 *
 * CÓMO
 * ----
 * Se leen las plantillas en crudo. Todo lo que pasa por Jinja —`{{ … }}`— se
 * da por bueno, porque ahí es donde vive `_()`. De lo que queda se recogen los
 * literales de cadena y el texto literal de las plantillas de cadena, y se
 * marca lo que parece prosa castellana.
 *
 * Es una heurística, no un detector de idioma: busca acentos, signos de
 * apertura y palabras funcionales del castellano. Se equivoca por los dos
 * lados, y para eso está `EXCEPCIONES`, que exige justificar cada perdón.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const PLANTILLAS = path.join(__dirname, '..', '..', 'app', 'templates');

/**
 * Cadenas que parecen castellano pero no lo son, o que no las ve un usuario.
 * Cada entrada lleva su motivo: sin él, esto se convierte en el sitio donde se
 * esconde lo que no apetece arreglar.
 */
const EXCEPCIONES = new Map([
  ['generacion', 'nombre de estado en la API, no texto de pantalla'],
  ['error_generacion', 'nombre de estado en la API'],
  ['no_significativa', 'valor del campo tipo_adaptacion'],
  ['significativa', 'valor del campo tipo_adaptacion'],
  ['situacion', 'clave de datos, no visible'],
  ['seccion', 'clave de datos, no visible'],
  ['descripcion', 'nombre de campo del formulario'],
  ['comparacion', 'nombre de clase CSS'],
  ['propuesta-col', 'nombre de clase CSS'],
  ['propuesta-col--nueva', 'nombre de clase CSS'],
  ['comparacion__aviso', 'nombre de clase CSS'],
  ['comparacion__columnas', 'nombre de clase CSS'],
  ['propuesta-col__cuerpo', 'nombre de clase CSS'],
]);

/** Palabras funcionales del castellano: si aparece alguna suelta, es prosa. */
const FUNCIONALES = new RegExp(
  '\\b(el|la|los|las|un|una|unos|unas|de|del|al|que|con|por|para|sin|sobre|' +
  'como|pero|si|no|se|te|tu|su|sus|esta|este|estos|estas|más|menos|ya|' +
  'hay|ha|han|está|están|puede|pueden|debe|deben|tiene|tienen|hacer|' +
  'antes|después|cuando|donde|porque|aunque|desde|hasta|entre|cada|todo|' +
  'todos|todas|otra|otro|misma|mismo)\\b',
  'i'
);

/** Acentos y signos que en la práctica solo aparecen en texto para leer. */
const ORTOGRAFIA = /[áéíóúÁÉÍÓÚñÑ¿¡«»]/;

/**
 * Palabras que son castellano y también inglés o jerga técnica. Contarlas
 * llenaría el informe de ruido: `error`, `total` o `digital` aparecen en
 * nombres de campo y de clase por todas partes.
 */
const HOMOGRAFAS = new Set([
  'error', 'total', 'digital', 'normal', 'general', 'final', 'natural',
  'central', 'personal', 'real', 'original', 'local', 'base', 'texto',
  'nombre', 'valor', 'estado', 'lista', 'items', 'modelo', 'perfil',
  'formal', 'inicial', 'principal', 'especial', 'material',
]);

/**
 * Léxico castellano sacado del propio catálogo de traducción.
 *
 * La idea: cualquier palabra que ya aparezca en una cadena marcada es, por
 * definición, castellano de esta interfaz. Así el detector se afina solo cada
 * vez que se marca una cadena nueva, en lugar de depender de una lista que
 * alguien tendría que mantener.
 *
 * Hacía falta porque la heurística de acentos y palabras funcionales tiene un
 * agujero grande: no ve etiquetas cortas. «Resumir», «Traducir» y «Proponer
 * alternativa» —las tres que motivaron este test— no llevan acento ni ninguna
 * palabra funcional, así que pasaban limpias.
 *
 * Punto ciego que queda, y conviene tenerlo presente: una palabra castellana
 * que no esté en ninguna cadena ya marcada es invisible para esto. El test
 * detecta regresiones, no demuestra ausencia.
 */
function lexicoDelCatalogo() {
  const pot = path.join(
    __dirname, '..', '..', 'app', 'translations', 'messages.pot'
  );
  if (!fs.existsSync(pot)) return new Set();
  const palabras = new Set();
  for (const m of fs.readFileSync(pot, 'utf8').matchAll(/"((?:[^"\\]|\\.)*)"/g)) {
    const limpio = m[1].replace(/<[^>]*>|\{\w+\}|\\[nt]/g, ' ');
    for (const p of limpio.matchAll(/[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}/g)) {
      const w = p[0].toLowerCase();
      if (!HOMOGRAFAS.has(w)) palabras.add(w);
    }
  }
  return palabras;
}

const LEXICO = lexicoDelCatalogo();

/* ------------------------------------------------------------------------ */

/** Los `<script>` de una plantilla, concatenados. */
function scripts(html) {
  const trozos = [];
  const rx = /<script\b[^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = rx.exec(html)) !== null) trozos.push(m[1]);
  return trozos.join('\n');
}

/**
 * Sustituye las expresiones de Jinja por un hueco.
 *
 * Es el paso que define el test: todo lo que sale de `{{ … }}` ya ha pasado
 * por `_()` o es un dato, y en cualquier caso no es una cadena escrita a pelo.
 * Se sustituye por comillas vacías para no romper la sintaxis de alrededor.
 */
function sinJinja(src) {
  return src
    .replace(/\{\{[\s\S]*?\}\}/g, '""')
    .replace(/\{%[\s\S]*?%\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
}

/**
 * Recoge el texto que un usuario podría llegar a leer.
 *
 * Dos fuentes distintas y las dos hacen falta:
 *
 *  1. Los literales `'…'` y `"…"`, que es la forma corriente.
 *  2. El texto **literal** de las plantillas de cadena, sin lo interpolado.
 *     Es donde se escondía la comparación de propuestas: un bloque de HTML de
 *     veinte líneas con la prosa incrustada entre etiquetas. Mirar solo los
 *     literales con comillas no habría visto ni una.
 */
function textos(src) {
  const encontrados = [];

  /** Texto visible de un trozo de HTML: nodos de texto y atributos que se leen. */
  function deHtml(html) {
    for (const attr of html.matchAll(
      /\b(?:title|aria-label|placeholder|alt)\s*=\s*"([^"]*)"/g
    )) encontrados.push(attr[1]);
    encontrados.push(...html.replace(/<[^>]*>/g, '\n').split('\n'));
  }

  /*
   * Se recorre el código UNA vez en lugar de pasar tres expresiones regulares.
   * El motivo es que las plantillas de cadena llevan comillas dentro:
   *
   *     `<h4 id="prop-actual-${clave}">`
   *
   * Buscando `"…"` por separado se captura `prop-actual-${clave}` como si
   * fuera una cadena de texto, y el informe se llena de fragmentos de atributo
   * que nadie va a leer nunca. Saltándose cada literal entero al encontrarlo,
   * eso no puede pasar.
   */
  let i = 0;
  while (i < src.length) {
    const c = src[i];

    if (c === "'" || c === '"') {
      i++;
      let literal = '';
      while (i < src.length && src[i] !== c && src[i] !== '\n') {
        if (src[i] === '\\') { i += 2; continue; }
        literal += src[i++];
      }
      i++;
      if (/<[a-z][^>]*>/i.test(literal)) deHtml(literal);
      else encontrados.push(literal);
      continue;
    }

    if (c === '`') {
      i++;
      let literal = '';
      while (i < src.length && src[i] !== '`') {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === '$' && src[i + 1] === '{') {
          i += 2;
          let profundidad = 1;
          while (i < src.length && profundidad > 0) {
            if (src[i] === '{') profundidad++;
            else if (src[i] === '}') profundidad--;
            i++;
          }
          literal += ' ';      // lo interpolado es código: no se mira
          continue;
        }
        literal += src[i++];
      }
      i++;
      // Casi siempre son bloques de HTML —la comparación de propuestas ocupa
      // veinte líneas— y ahí lo que se lee son los nodos de texto.
      if (/<[a-z][^>]*>/i.test(literal)) deHtml(literal);
      else encontrados.push(literal);
      continue;
    }

    i++;
  }

  return encontrados;
}

/** ¿Esto es prosa castellana que un usuario va a leer? */
function esProsa(texto) {
  const limpio = texto.trim();
  if (limpio.length < 4) return false;
  if (EXCEPCIONES.has(limpio)) return false;
  // Rutas, URLs y formatos.
  if (/^[./#?&]|^https?:|^[a-z]+:\/\//.test(limpio)) return false;
  // Identificadores: minúsculas con guiones o puntos y sin espacios.
  if (/^[a-z][\w.-]*$/.test(limpio)) return false;
  // Selectores CSS y consultas de medios: llevan puntuación que no aparece en
  // prosa. `header.topbar nav a`, `[data-elegir]`, `(prefers-color-scheme: dark)`.
  if (/[[\]{}>*]|^\(|::|\.\w/.test(limpio)) return false;
  // Cabeceras HTTP y nombres con guion en mayúsculas: `Content-Type`.
  if (/^[A-Z][a-z]+-[A-Z]/.test(limpio)) return false;
  // Atributo cuyo valor era una interpolación entera: `title=" "`. Ya se mira
  // lo que hay dentro de la interpolación por su cuenta.
  if (/^[\w-]+="\s*"$/.test(limpio)) return false;
  if (ORTOGRAFIA.test(limpio)) return true;
  if (/\s/.test(limpio) && FUNCIONALES.test(limpio)) return true;
  // Y por último el léxico, que es lo único que ve las etiquetas cortas.
  return [...limpio.matchAll(/[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}/g)]
    .some((p) => LEXICO.has(p[0].toLowerCase()));
}

/* ------------------------------------------------------------------------ */

function plantillas(dir) {
  const salida = [];
  for (const entrada of fs.readdirSync(dir, { withFileTypes: true })) {
    const completo = path.join(dir, entrada.name);
    if (entrada.isDirectory()) salida.push(...plantillas(completo));
    else if (entrada.name.endsWith('.html')) salida.push(completo);
  }
  return salida;
}

let fallos = 0;
console.log('\n--- texto sin marcar en los <script> de las plantillas ---\n');

for (const ruta of plantillas(PLANTILLAS).sort()) {
  const codigo = sinJinja(scripts(fs.readFileSync(ruta, 'utf8')));
  const sospechosas = [...new Set(textos(codigo).filter(esProsa))];
  if (!sospechosas.length) continue;
  fallos += sospechosas.length;
  console.log(`  ${path.relative(PLANTILLAS, ruta)}`);
  for (const s of sospechosas) console.log(`     · ${s.trim().slice(0, 78)}`);
  console.log('');
}

if (fallos === 0) {
  console.log('  Ninguna. Todo el texto de los scripts pasa por _().\n');
} else {
  console.log(
    `\n${fallos} cadenas sin marcar. Cada una es una pantalla que se queda en\n` +
    `castellano para quien tenga la interfaz en catalán, gallego o euskera.\n` +
    `Márcalas con {{ _('…')|tojson }} en un diccionario del script, como hacen\n` +
    `el resto de plantillas, o justifícalas en EXCEPCIONES.\n`
  );
}
process.exit(fallos === 0 ? 0 : 1);
