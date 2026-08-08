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
 *     docker run --rm -v "E:\AWEBO\api:/app" -w /app node:22-alpine \
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

const { cursosDe, materiasDe, explicarMateria } = contexto.window.Cobertura;

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

console.log(fallos === 0 ? '\nTODO CORRECTO\n' : `\n${fallos} FALLOS\n`);
process.exit(fallos === 0 ? 0 : 1);
