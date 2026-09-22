/**
 * Que las fechas salgan en formato español, mire quien las mire.
 *
 * Se ejecutan con Node, sin navegador ni dependencias. Desde `api/`:
 *
 *     node tests/js/fechas.test.js
 *
 * EL FALLO QUE PUSO ESTO
 * ----------------------
 * `admin/panel.html` llamaba a `toLocaleDateString()` **sin argumento de
 * idioma**, y sin argumento se usa el del navegador. En un Chrome en inglés
 * eso da `09/22/2026` —mes, día, año— en una aplicación para docentes
 * españoles. Las otras cuatro pantallas pasaban `'es-ES'` cada una por su
 * cuenta, así que el fallo solo se veía en `/admin`.
 *
 * Lo que lo hace difícil de cazar es que **depende de la máquina que abre la
 * página**: en el portátil de quien lo escribió salía bien.
 *
 * POR QUÉ ESTE TEST ESTÁ EN JAVASCRIPT Y NO EN PYTHON
 * ----------------------------------------------------
 * Un test de Python podría comprobar que la cadena `toLocaleDateString()` ya
 * no aparece en las plantillas —y hay uno que lo hace—, pero no puede
 * comprobar **qué imprime** el formateador. Eso solo se sabe ejecutándolo, y
 * es lo único que distingue «la llamada tiene buena pinta» de «la fecha sale
 * bien».
 */
'use strict';

const assert = require('node:assert');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const RAIZ = path.resolve(__dirname, '..', '..');
const APP_JS = path.join(RAIZ, 'app', 'static', 'js', 'app.js');

/**
 * Carga `app.js` en un contexto mínimo y devuelve su objeto `AWEBO`.
 *
 * El fichero hace más cosas —el envoltorio de `fetch`, el estado de sesión—
 * que necesitan un DOM. Se le da uno de mentira con lo justo: lo que se está
 * probando es el formateador, y montar un navegador entero para eso sería
 * cambiar un test rápido por uno frágil.
 */
function cargarAwebo() {
  const codigo = fs.readFileSync(APP_JS, 'utf8');
  const nada = () => {};
  const contexto = {
    window: {},
    document: {
      querySelector: () => null,
      querySelectorAll: () => [],
      getElementById: () => null,
      addEventListener: nada,
    },
    console,
    fetch: nada,
    Headers: class {},
    URL,
    setTimeout,
  };
  contexto.window.fetch = nada;
  contexto.window.location = { href: 'http://localhost/', origin: 'http://localhost' };
  vm.createContext(contexto);
  vm.runInContext(codigo, contexto);
  return contexto.window.AWEBO;
}

const AWEBO = cargarAwebo();

//: Un instante fijo y en UTC. Con hora del mediodía para que ningún desfase
//: horario razonable mueva el día y haga que el test pase o falle según dónde
//: se ejecute — que es exactamente el fallo que este fichero persigue.
const ISO = '2026-09-22T12:00:00Z';

test('el formateador existe y está expuesto', () => {
  assert.equal(typeof AWEBO.fecha, 'function');
});

test('la fecha sale como DD/MM/AAAA', () => {
  assert.match(AWEBO.fecha(ISO), /^22\/09\/2026$/);
});

test('con minutos añade HH:MM y nada más', () => {
  assert.match(AWEBO.fecha(ISO, 'minutos'), /^22\/09\/2026,? \d{2}:\d{2}$/);
});

test('con segundos añade HH:MM:SS', () => {
  assert.match(AWEBO.fecha(ISO, 'segundos'), /^22\/09\/2026,? \d{2}:\d{2}:\d{2}$/);
});

test('el día va delante del mes, que es todo el asunto', () => {
  // Un día que no puede confundirse con un mes: si saliera MES/DÍA, el primer
  // número sería 09 y no 22. Con `2026-09-05` las dos lecturas serían
  // plausibles y el test no distinguiría nada.
  const [primero, segundo] = AWEBO.fecha(ISO).split('/');
  assert.equal(primero, '22');
  assert.equal(segundo, '09');
});

test('NO depende del idioma del sistema', () => {
  // La razón de ser del arreglo. `toLocaleDateString()` sin argumento habría
  // devuelto 09/22/2026 con este entorno; con el idioma fijado, da igual.
  const previo = process.env.LANG;
  process.env.LANG = 'en_US.UTF-8';
  try {
    assert.match(AWEBO.fecha(ISO), /^22\/09\/2026$/);
  } finally {
    if (previo === undefined) delete process.env.LANG;
    else process.env.LANG = previo;
  }
});

test('el idioma está fijado y no se toma del documento', () => {
  // Catalán y gallego escriben la fecha igual que el castellano, pero el
  // euskera da 2026/09/22. Seguir al idioma de la interfaz haría que el
  // listado y el documento se contradijeran.
  assert.equal(AWEBO.LOCALE_FECHAS, 'es-ES');
});

test('sin valor devuelve cadena vacía, no «Invalid Date»', () => {
  assert.equal(AWEBO.fecha(null), '');
  assert.equal(AWEBO.fecha(''), '');
  assert.equal(AWEBO.fecha(undefined), '');
});

test('lo que no se puede interpretar se devuelve tal cual', () => {
  // «Invalid Date» no le dice nada a quien lo lee; el valor original al menos
  // deja ver qué llegó.
  assert.equal(AWEBO.fecha('no es una fecha'), 'no es una fecha');
});

test('ninguna plantilla se formatea una fecha por su cuenta', () => {
  // La guarda de fondo: si alguien vuelve a llamar a `toLocaleDateString` en
  // una plantilla, reaparece el fallo original —y no en su máquina—.
  const plantillas = path.join(RAIZ, 'app', 'templates');
  const culpables = [];

  const recorrer = (dir) => {
    for (const entrada of fs.readdirSync(dir, { withFileTypes: true })) {
      const ruta = path.join(dir, entrada.name);
      if (entrada.isDirectory()) recorrer(ruta);
      else if (entrada.name.endsWith('.html')) {
        const texto = fs.readFileSync(ruta, 'utf8');
        if (/\.toLocale(Date|Time)?String\(/.test(texto)) {
          culpables.push(path.relative(plantillas, ruta));
        }
      }
    }
  };
  recorrer(plantillas);

  assert.deepEqual(
    culpables, [],
    `estas plantillas formatean fechas por su cuenta: ${culpables.join(', ')}. ` +
    'Usa AWEBO.fecha() de app.js.'
  );
});
