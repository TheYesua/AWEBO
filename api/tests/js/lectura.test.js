/**
 * Tests de `textoLegible` (app/static/js/lectura.js).
 *
 * Se ejecutan con Node, sin navegador ni dependencias. Desde `api/`:
 *
 *     node tests/js/lectura.test.js
 *
 * El contenedor `api` es `python:3.12-slim` y NO tiene Node, así que sirve un
 * contenedor efímero:
 *
 *     docker run --rm -v "$PWD:/app" -w /app node:22-alpine \
 *         node tests/js/lectura.test.js
 *
 * Solo se prueba `textoLegible`, que es pura: recibe un árbol de elementos y
 * devuelve texto. La parte de voz (`Lector`) envuelve una API del navegador y
 * no se puede ejercitar aquí; lo que sí se puede —y es donde está la
 * dificultad de verdad— es que una tabla de rúbricas suene a algo.
 *
 * Origen: la lectura en voz alta extrae el texto de lo YA RENDERIZADO, no del
 * JSON de la sección. Eso evita seis conversores que dupliquen lo que
 * `render-secciones.js` ya sabe, pero traslada el problema a leer bien el DOM:
 * `textContent` a secas devuelve las palabras de dos párrafos pegadas y las
 * celdas de una tabla en fila, sin decir a qué columna pertenece cada una.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

/* ------------------------------------------------------------------------
   DOM mínimo
   ------------------------------------------------------------------------
   Lo justo que usa `textoLegible`: nodos de texto y de elemento, `matches`,
   `hasAttribute` y `querySelectorAll` para thead/tbody. Es bastante menos
   código que traerse una dependencia, y deja claro qué parte del DOM se está
   dando por supuesta.
   ------------------------------------------------------------------------ */

const NODO_ELEMENTO = 1;
const NODO_TEXTO = 3;

function texto(valor) {
  return { nodeType: NODO_TEXTO, nodeValue: valor };
}

function el(tagName, opciones = {}, hijos = []) {
  const atributos = opciones.attrs || {};
  const clases = (opciones.class || '').split(' ').filter(Boolean);

  const nodo = {
    nodeType: NODO_ELEMENTO,
    tagName: tagName.toUpperCase(),
    childNodes: hijos,
    hasAttribute: (nombre) => nombre in atributos,
    matches(selector) {
      // Solo los selectores que usa NO_LEER: etiquetas, `.clase` y
      // `[atributo="valor"]`, separados por comas.
      return selector.split(',').map((s) => s.trim()).some((sel) => {
        if (sel.startsWith('.')) return clases.includes(sel.slice(1));
        if (sel.startsWith('[')) {
          const [, nombre, valor] = sel.match(/\[([\w-]+)="([^"]*)"\]/) || [];
          return nombre ? atributos[nombre] === valor : false;
        }
        return this.tagName === sel.toUpperCase();
      });
    },
    querySelectorAll(selector) {
      const [padre, hijo] = selector.split(' ');
      const encontrados = [];
      (function buscar(n, dentroDePadre) {
        for (const c of n.childNodes || []) {
          if (c.nodeType !== NODO_ELEMENTO) continue;
          const esPadre = c.tagName === padre.toUpperCase();
          if (dentroDePadre && c.tagName === hijo.toUpperCase()) encontrados.push(c);
          buscar(c, dentroDePadre || esPadre);
        }
      })(nodo, false);
      return encontrados;
    },
    get children() {
      return nodo.childNodes.filter((c) => c.nodeType === NODO_ELEMENTO);
    },
    get textContent() {
      return nodo.childNodes.map((c) =>
        c.nodeType === NODO_TEXTO ? c.nodeValue : c.textContent
      ).join('');
    },
  };
  return nodo;
}

// Se carga el fichero REAL, no una copia.
const ruta = path.join(__dirname, '..', '..', 'app', 'static', 'js', 'lectura.js');
const contexto = { window: {} };
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(ruta, 'utf8'), contexto);
const { textoLegible } = contexto.window.Lectura;

let fallos = 0;
function check(nombre, condicion, extra) {
  if (condicion) {
    console.log(`  OK    ${nombre}`);
  } else {
    console.log(`  FALLA ${nombre}${extra ? `\n          ${extra}` : ''}`);
    fallos += 1;
  }
}

console.log('\ntextoLegible');

/* --- Separación entre bloques ----------------------------------------- */

check(
  'dos párrafos no se leen pegados',
  (() => {
    const raiz = el('div', {}, [
      el('p', {}, [texto('Primera idea.')]),
      el('p', {}, [texto('Segunda idea.')]),
    ]);
    const r = textoLegible(raiz);
    return r === 'Primera idea.\nSegunda idea.';
  })(),
  'sin separar, textContent devuelve «Primera idea.Segunda idea.»'
);

check(
  'los elementos de una lista se separan',
  (() => {
    const raiz = el('ul', {}, [
      el('li', {}, [texto('Uno')]),
      el('li', {}, [texto('Dos')]),
      el('li', {}, [texto('Tres')]),
    ]);
    return textoLegible(raiz) === 'Uno\nDos\nTres';
  })()
);

check(
  'el texto en línea NO se parte',
  (() => {
    const raiz = el('p', {}, [
      texto('Un objetivo '),
      el('strong', {}, [texto('importante')]),
      texto(' del curso.'),
    ]);
    return textoLegible(raiz) === 'Un objetivo importante del curso.';
  })(),
  'negritas y enlaces son parte de la frase, no una pausa'
);

/* --- Qué no se lee ----------------------------------------------------- */

check(
  'los botones de acción no se leen',
  (() => {
    const raiz = el('section', {}, [
      el('div', { class: 'seccion-gen__acciones' }, [
        el('button', {}, [texto('Regenerar')]),
        el('button', {}, [texto('Resumir')]),
      ]),
      el('p', {}, [texto('El contenido.')]),
    ]);
    return textoLegible(raiz) === 'El contenido.';
  })(),
  'oír «Regenerar Resumir» antes de cada sección sería insufrible'
);

check(
  'los iconos decorativos no se leen',
  (() => {
    const raiz = el('p', {}, [
      el('i', { attrs: { 'aria-hidden': 'true' } }, [texto('★')]),
      texto('Evaluación'),
    ]);
    return textoLegible(raiz) === 'Evaluación';
  })()
);

check(
  'lo oculto no se lee',
  (() => {
    const raiz = el('div', {}, [
      el('p', { attrs: { hidden: '' } }, [texto('Aviso oculto')]),
      el('p', {}, [texto('Visible')]),
    ]);
    return textoLegible(raiz) === 'Visible';
  })(),
  'si no está en pantalla, tampoco debe sonar'
);

check(
  'el texto solo para lectores de pantalla SÍ se lee',
  (() => {
    const raiz = el('p', {}, [
      el('span', { class: 'sr-only' }, [texto('(obligatorio) ')]),
      texto('Título'),
    ]);
    return textoLegible(raiz) === '(obligatorio) Título';
  })(),
  'ese texto existe justamente para quien no ve la pantalla'
);

/* --- Tablas ------------------------------------------------------------ */

check(
  'una tabla se lee como «encabezado: valor»',
  (() => {
    const tabla = el('table', {}, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', {}, [texto('Criterio')]),
          el('th', {}, [texto('Nivel alto')]),
        ]),
      ]),
      el('tbody', {}, [
        el('tr', {}, [
          el('td', {}, [texto('CE1')]),
          el('td', {}, [texto('Identifica con precisión')]),
        ]),
      ]),
    ]);
    const r = textoLegible(tabla);
    return r === 'Criterio: CE1. Nivel alto: Identifica con precisión';
  })(),
  'leída celda a celda —«CE1 Identifica con precisión»— no se sabe qué es cada cosa'
);

check(
  'cada fila de la tabla va en su propia pausa',
  (() => {
    const fila = (a, b) => el('tr', {}, [
      el('td', {}, [texto(a)]), el('td', {}, [texto(b)]),
    ]);
    const tabla = el('table', {}, [
      el('thead', {}, [el('tr', {}, [
        el('th', {}, [texto('Instrumento')]), el('th', {}, [texto('Peso')]),
      ])]),
      el('tbody', {}, [fila('Rúbrica', '40%'), fila('Portafolio', '60%')]),
    ]);
    const r = textoLegible(tabla);
    return r === 'Instrumento: Rúbrica. Peso: 40%\nInstrumento: Portafolio. Peso: 60%';
  })()
);

check(
  'una tabla sin encabezados lee las celdas a secas',
  (() => {
    const tabla = el('table', {}, [
      el('tbody', {}, [el('tr', {}, [
        el('td', {}, [texto('Alfa')]), el('td', {}, [texto('Beta')]),
      ])]),
    ]);
    return textoLegible(tabla) === 'Alfa. Beta';
  })(),
  'inventar un encabezado sería peor que no decir nada'
);

check(
  'las celdas vacías no dejan huecos',
  (() => {
    const tabla = el('table', {}, [
      el('thead', {}, [el('tr', {}, [
        el('th', {}, [texto('A')]), el('th', {}, [texto('B')]),
      ])]),
      el('tbody', {}, [el('tr', {}, [
        el('td', {}, [texto('valor')]), el('td', {}, [texto('')]),
      ])]),
    ]);
    return textoLegible(tabla) === 'A: valor';
  })(),
  'oír «B:» y silencio suena a error'
);

/* --- Casos límite ------------------------------------------------------ */

check('sin elemento devuelve cadena vacía', textoLegible(null) === '');

check(
  'los espacios sobrantes se colapsan',
  (() => {
    const raiz = el('div', {}, [
      el('p', {}, [texto('   Mucho    espacio   ')]),
      el('p', {}, [texto('')]),
      el('p', {}, [texto('Y otro')]),
    ]);
    return textoLegible(raiz) === 'Mucho espacio\nY otro';
  })(),
  'los saltos de línea de la plantilla no deben oírse como pausas'
);

console.log(fallos === 0
  ? '\nTodo correcto.\n'
  : `\n${fallos} comprobación(es) fallidas.\n`);
process.exit(fallos === 0 ? 0 : 1);
