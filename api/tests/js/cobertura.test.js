/**
 * Tests de la lógica de cobertura curricular (app/static/js/catalogos.js).
 *
 * Se ejecutan con Node, sin navegador ni dependencias. Desde `api/`:
 *
 *     node tests/js/cobertura.test.js
 *
 * El contenedor `api` es `python:3.12-slim` y NO tiene Node, así que
 * `docker compose exec api node ...` no funciona. Si no hay Node en el
 * anfitrión, sirve un contenedor efímero:
 *
 *     docker run --rm -v "$PWD:/app" -w /app node:22-alpine \
 *         node tests/js/cobertura.test.js
 *
 * Se prefiere eso a instalar Node en la imagen del proyecto: engordaría una
 * imagen de producción para ejecutar un test.
 *
 * Cubren solo las dos funciones puras — `cursosDe` y `materiasDe` —, que son
 * las que deciden qué se puede elegir. `enlazar` toca el DOM y queda fuera.
 *
 * Origen: los desplegables de curso y materia eran independientes y permitían
 * «Matemáticas · 4º ESO», combinación que no existe porque en 4.º la materia
 * se desdobla en los itinerarios A y B.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Se carga el fichero REAL, no una copia: si alguien cambia la lógica y no
// los tests, esto debe enterarse.
const ruta = path.join(__dirname, '..', '..', 'app', 'static', 'js', 'catalogos.js');
const contexto = { window: {}, document: { createElement: () => ({}) } };
contexto.window.document = contexto.document;
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(ruta, 'utf8'), contexto);

const { cursosDe, materiasDe, explicarMateria, enlazarProvincia, enlazar } = contexto.window.Cobertura;

/** Cobertura real del despliegue, tal y como la devuelve /api/curriculo/cobertura. */
const COBERTURA = [
  { materia: 'Inglés', cursos: ['1º ESO', '2º ESO', '3º ESO', '4º ESO'] },
  { materia: 'Lengua', cursos: ['1º ESO', '2º ESO', '3º ESO', '4º ESO'] },
  { materia: 'Matemáticas', cursos: ['1º ESO', '2º ESO', '3º ESO'] },
  { materia: 'Matemáticas A', cursos: ['4º ESO'] },
  { materia: 'Matemáticas B', cursos: ['4º ESO'] },
  { materia: 'Tecnología y Digitalización', cursos: ['2º ESO', '3º ESO'] },
  { materia: 'Tecnología', cursos: ['4º ESO'] },
];

let fallos = 0;
function check(nombre, condicion, extra) {
  if (condicion) {
    console.log(`  OK    ${nombre}`);
  } else {
    console.log(`  FALLA ${nombre}${extra ? `  [${extra}]` : ''}`);
    fallos += 1;
  }
}
const iguales = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log('\n--- materias por curso ---');
check('4º ESO no ofrece «Matemáticas»',
  !materiasDe(COBERTURA, '4º ESO').includes('Matemáticas'),
  materiasDe(COBERTURA, '4º ESO').join(', '));
check('4º ESO ofrece los dos itinerarios',
  materiasDe(COBERTURA, '4º ESO').includes('Matemáticas A') &&
  materiasDe(COBERTURA, '4º ESO').includes('Matemáticas B'));
check('3º ESO sí ofrece «Matemáticas»',
  materiasDe(COBERTURA, '3º ESO').includes('Matemáticas'));
check('1º ESO no ofrece «Tecnología»',
  !materiasDe(COBERTURA, '1º ESO').includes('Tecnología'),
  materiasDe(COBERTURA, '1º ESO').join(', '));
check('sin curso se ofrecen todas',
  materiasDe(COBERTURA, '').length === COBERTURA.length,
  `${materiasDe(COBERTURA, '').length} de ${COBERTURA.length}`);
check('las materias salen ordenadas',
  iguales(materiasDe(COBERTURA, '4º ESO'),
    ['Inglés', 'Lengua', 'Matemáticas A', 'Matemáticas B', 'Tecnología']),
  materiasDe(COBERTURA, '4º ESO').join(', '));

console.log('\n--- cursos por materia (el sentido inverso) ---');
check('«Matemáticas» llega solo hasta 3º',
  iguales(cursosDe(COBERTURA, 'Matemáticas'), ['1º ESO', '2º ESO', '3º ESO']),
  cursosDe(COBERTURA, 'Matemáticas').join(', '));
check('«Matemáticas A» solo existe en 4º',
  iguales(cursosDe(COBERTURA, 'Matemáticas A'), ['4º ESO']));
check('«Tecnología» no llega a 1º',
  !cursosDe(COBERTURA, 'Tecnología').includes('1º ESO'),
  cursosDe(COBERTURA, 'Tecnología').join(', '));
check('sin materia se ofrecen los cuatro cursos',
  iguales(cursosDe(COBERTURA, ''), ['1º ESO', '2º ESO', '3º ESO', '4º ESO']),
  cursosDe(COBERTURA, '').join(', '));
check('los cursos salen en orden numérico, no alfabético',
  cursosDe(COBERTURA, '')[0] === '1º ESO');
check('una materia inexistente no ofrece cursos',
  iguales(cursosDe(COBERTURA, 'Filosofía Cuántica'), []));

console.log('\n--- coherencia en ambos sentidos ---');
let incoherentes = [];
for (const { materia, cursos } of COBERTURA) {
  for (const curso of cursos) {
    const okIda = materiasDe(COBERTURA, curso).includes(materia);
    const okVuelta = cursosDe(COBERTURA, materia).includes(curso);
    if (!okIda || !okVuelta) incoherentes.push(`${materia}/${curso}`);
  }
}
check('toda pareja válida se alcanza por los dos caminos',
  incoherentes.length === 0, incoherentes.join(', '));

check('«Matemáticas · 4º ESO» es inalcanzable por ambos caminos',
  !materiasDe(COBERTURA, '4º ESO').includes('Matemáticas') &&
  !cursosDe(COBERTURA, 'Matemáticas').includes('4º ESO'));

console.log('\n--- las dos Tecnologías son materias distintas ---');
/* Compartieron etiqueta hasta el 7/8/2026, y el seed acababa mezclando sus
   competencias. Si alguien vuelve a fusionarlas, esto lo dice. */
check('2º ESO ofrece Tecnología y Digitalización, no Tecnología',
  materiasDe(COBERTURA, '2º ESO').includes('Tecnología y Digitalización') &&
  !materiasDe(COBERTURA, '2º ESO').includes('Tecnología'));
check('4º ESO ofrece Tecnología, no Tecnología y Digitalización',
  materiasDe(COBERTURA, '4º ESO').includes('Tecnología') &&
  !materiasDe(COBERTURA, '4º ESO').includes('Tecnología y Digitalización'));

console.log('\n--- explicación de materias ambiguas ---');
/* El nombre «Matemáticas A» no dice qué es, y la duda razonable —¿ciencias o
   letras?— no la resuelve el desplegable. */
const TEXTOS = { matematicasA: 'texto de A', matematicasB: 'texto de B' };
check('Matemáticas A y B tienen explicación, y son distintas',
  explicarMateria('Matemáticas A', TEXTOS) === 'texto de A' &&
  explicarMateria('Matemáticas B', TEXTOS) === 'texto de B');
check('una materia corriente no la tiene',
  explicarMateria('Lengua', TEXTOS) === '' &&
  explicarMateria('Matemáticas', TEXTOS) === '');
check('sin selección tampoco',
  explicarMateria('', TEXTOS) === '' && explicarMateria(undefined, TEXTOS) === '');
check('faltando los textos devuelve cadena, no undefined',
  explicarMateria('Matemáticas A', {}) === '');

console.log('\n--- catálogo vacío ---');
check('no revienta sin datos',
  iguales(materiasDe([], '1º ESO'), []) && iguales(cursosDe([], 'Lengua'), []));

console.log('\n--- el enganche de la provincia ---');
/* `enlazar` toca el DOM y por eso quedó fuera de este fichero. `enlazarProvincia`
   también, pero su contrato lo usan CUATRO plantillas para decidir cuándo
   recargar el catálogo, y la página de detalle además lo usa para saber si es
   la primera pintada o un cambio de verdad —de eso depende que se conserve o
   se borre la materia elegida—. Un fallo aquí no da error: deja la SdA con una
   materia que no existe en la comunidad nueva. Se le da un DOM de mentira, que
   es todo lo que necesita: `value`, `disabled`, `hidden` y `addEventListener`. */
function selectFalso(valor) {
  return {
    value: valor,
    disabled: false,
    hidden: false,
    // Visibles a propósito: contar oyentes es la mitad de lo que hay que
    // comprobar cuando `enlazar` se llama más de una vez.
    _oyentes: [],
    addEventListener(_, f) { this._oyentes.push(f); },
    cambiarA(nuevo) { this.value = nuevo; this._oyentes.slice().forEach((f) => f()); },
  };
}

let avisadas = [];
const selProv = selectFalso('ceuta');
const selC = selectFalso('1º ESO');
const selM = selectFalso('Lengua');
const avisoBloqueo = { hidden: true };
enlazarProvincia({
  selProvincia: selProv, selCurso: selC, selMateria: selM,
  aviso: avisoBloqueo, alCambiar: (p) => avisadas.push(p),
});

check('con provincia ya puesta avisa una vez al enlazar',
  iguales(avisadas, ['ceuta']), avisadas.join(','));
check('y deja curso y materia utilizables',
  selC.disabled === false && selM.disabled === false && avisoBloqueo.hidden === true);

selProv.cambiarA('sevilla');
check('cambiar de provincia avisa con la nueva',
  iguales(avisadas, ['ceuta', 'sevilla']), avisadas.join(','));

/* Que la segunda llamada sea distinguible de la primera es justo lo que la
   página de detalle necesita: en la primera conserva el curso y la materia que
   ya tenía la SdA, y en las siguientes NO, porque el currículo es otro. */
check('el aviso llega dos veces, no una: la primera pintada es distinguible',
  avisadas.length === 2);

selProv.cambiarA('');
check('sin provincia se bloquean curso y materia',
  selC.disabled === true && selM.disabled === true);
check('y se explica por qué, que el gris solo no lo dice (WCAG 1.4.1)',
  avisoBloqueo.hidden === false);
check('quedarse sin provincia no dispara una recarga de catálogo',
  avisadas.length === 2, avisadas.join(','));

console.log('\n--- volver a enlazar con otra cobertura ---');
/* EL FALLO QUE ESTO PROTEGE
   -------------------------
   `enlazar` se llama UNA VEZ por carga de página... hasta que el selector de
   provincia lo hizo llamarse otra vez por cada cambio. `addEventListener` no
   sustituye, acumula: el oyente de la llamada anterior seguía vivo y con la
   cobertura vieja atrapada en su cierre. Resultado: cambias de Ceuta a
   Sevilla, tocas el curso, y el desplegable de materias se rellena con las de
   Ceuta. Sin error, sin aviso, y con la SdA generándose contra un currículo
   que no es el suyo.

   No lo cazaba nada: `cobertura.test.js` solo probaba las funciones puras y
   `declaraciones.test.js` solo mira que el JavaScript compile. */
function selectConOpciones(valor) {
  const s = selectFalso(valor);
  s.options = [];
  s.removeEventListener = (_, f) => {
    const i = s._oyentes.indexOf(f);
    if (i >= 0) s._oyentes.splice(i, 1);
  };
  return s;
}

const COB_A = [{ materia: 'Solo de A', cursos: ['1º ESO'] }];
const COB_B = [{ materia: 'Solo de B', cursos: ['1º ESO'] }];

/* `rellenarSelect` es global de la página, no de este módulo. Se sustituye por
   uno que solo apunta qué se le pidió pintar: es exactamente lo que hay que
   observar. */
let pintados = [];
contexto.window.rellenarSelect = (sel, opciones, { valor } = {}) => {
  pintados.push(opciones.slice());
  sel.value = opciones.includes(valor) ? valor : (valor || '');
};

const cursoE = selectConOpciones('');
const materiaE = selectConOpciones('');

enlazar({ cobertura: COB_A, selCurso: cursoE, selMateria: materiaE, aviso: null });
enlazar({ cobertura: COB_B, selCurso: cursoE, selMateria: materiaE, aviso: null });

check('al reenlazar queda UN oyente en cada select, no dos',
  cursoE._oyentes.length === 1 && materiaE._oyentes.length === 1,
  `curso=${cursoE._oyentes.length} materia=${materiaE._oyentes.length}`);

pintados = [];
cursoE.cambiarA('1º ESO');
const materiasOfrecidas = pintados.flat();
check('y las materias que ofrece son las de la cobertura NUEVA',
  materiasOfrecidas.includes('Solo de B') && !materiasOfrecidas.includes('Solo de A'),
  materiasOfrecidas.join(','));

/* La otra mitad del mismo fallo: lo que el <select> ya tuviera puesto es de la
   provincia anterior, no del servidor, así que no se puede respetar. */
const cursoH = selectConOpciones('');
const materiaH = selectConOpciones('');
enlazar({ cobertura: COB_A, selCurso: cursoH, selMateria: materiaH,
          aviso: null, preservar: true, materiaActual: 'Solo de A' });
check('la primera vez sí conserva lo que traía la SdA',
  materiaH.value === 'Solo de A', materiaH.value);
pintados = [];
enlazar({ cobertura: COB_B, selCurso: cursoH, selMateria: materiaH, aviso: null });
check('al cambiar de provincia NO arrastra la materia de la anterior',
  materiaH.value !== 'Solo de A', materiaH.value);
/* El síntoma concreto: los cursos se acotan por la materia que se dé por
   inicial. Si se arrastra «Solo de A», que no existe en la cobertura nueva, la
   lista de cursos sale VACÍA y el docente ve dos desplegables sin nada que
   elegir sin ninguna explicación. */
check('y el desplegable de curso no se queda vacío por acotarlo con ella',
  pintados[0].length > 0, `cursos ofrecidos: [${pintados[0].join(',')}]`);

console.log(fallos === 0 ? '\nTODO CORRECTO\n' : `\n${fallos} FALLOS\n`);
process.exit(fallos === 0 ? 0 : 1);
