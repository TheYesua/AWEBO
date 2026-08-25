/**
 * Auditoría de accesibilidad sobre las páginas ya renderizadas.
 *
 * QUÉ APORTA SOBRE LO QUE YA HABÍA
 * ---------------------------------
 * `tests/unit/test_temas.py` comprueba el contraste de los **tokens** del
 * sistema de diseño: la paleta en abstracto. No abre ninguna página, así que
 * no ve un `alt` que falte, un `<label>` sin asociar, un salto de `h2` a `h4`
 * ni un `aria-*` mal puesto. Este script sí: carga el HTML en un navegador de
 * verdad y le pasa axe-core, que son unas noventa reglas WCAG 2.1.
 *
 * `docs/ACCESIBILIDAD.md` lo proponía desde el principio del proyecto y nunca
 * se hizo. Se anotó como pendiente real el 16/08/2026 y se monta aquí.
 *
 * ALCANCE, DICHO CLARO
 * ---------------------
 * **Solo páginas públicas.** Son las que ve cualquiera sin cuenta y las que la
 * declaración de accesibilidad compromete de forma más directa. Las que exigen
 * sesión —el editor de situaciones, el panel— quedan fuera: haría falta un
 * inicio de sesión programático y datos sembrados, y es un paso más que
 * conviene dar aparte para que este no nazca frágil.
 *
 * No se presenta esto como «la aplicación es accesible». Es una red que caza
 * una clase concreta de fallos, y hay defectos de accesibilidad reales que
 * ninguna herramienta automática detecta: el orden de tabulación con sentido,
 * un texto alternativo que describa la imagen en vez de repetir el nombre del
 * fichero, o que un mensaje de error se anuncie a tiempo.
 *
 * POR QUÉ NO FALLA CON TODO
 * --------------------------
 * axe clasifica en minor / moderate / serious / critical. Este script **falla
 * con serious y critical** y deja las otras dos como aviso. No es indulgencia:
 * es que un flujo que se pone rojo por algo menor deja de mirarse, y lo que
 * interesa es que las dos categorías graves se queden en cero y se note el día
 * que dejen de estarlo.
 */
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const BASE = process.env.A11Y_BASE_URL || 'http://localhost:8090';

/**
 * Páginas sin sesión. Cada una entra por un motivo, no por completitud:
 * las tres primeras son la puerta de la aplicación y las tres siguientes son
 * las que la propia declaración de accesibilidad promete.
 */
const RUTAS = [
  ['/login', 'Inicio de sesión'],
  ['/register', 'Registro'],
  ['/restablecer-contrasena', 'Restablecer contraseña'],
  ['/accesibilidad', 'Declaración de accesibilidad'],
  ['/ayuda', 'Ayuda'],
  ['/mapa-web', 'Mapa web'],
];

/** Los dos temas se pintan con paletas distintas: auditar uno solo deja el
 *  otro sin comprobar, y el contraste es justo lo que cambia entre ambos. */
const TEMAS = ['claro', 'oscuro'];

const GRAVES = new Set(['serious', 'critical']);

async function auditar(pagina, ruta, tema) {
  await pagina.context().addCookies([
    { name: 'tema', value: tema, url: BASE },
  ]);
  const respuesta = await pagina.goto(`${BASE}${ruta}`, { waitUntil: 'networkidle' });

  if (!respuesta || respuesta.status() >= 400) {
    // Una ruta que ya no existe tiene que dar la cara. Si se dejara pasar, el
    // flujo seguiría en verde auditando cinco páginas en vez de seis y nadie
    // lo notaría.
    throw new Error(`${ruta} devolvió ${respuesta ? respuesta.status() : 'nada'}`);
  }

  const { violations } = await new AxeBuilder({ page: pagina })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  return violations;
}

function describir(v, ruta, tema) {
  const nodos = v.nodes.slice(0, 3).map((n) => `        ${n.target.join(' ')}`);
  const mas = v.nodes.length > 3 ? `\n        …y ${v.nodes.length - 3} más` : '';
  return (
    `  [${v.impact}] ${ruta} (${tema}) · ${v.id}\n` +
    `      ${v.help}\n` +
    `      ${v.helpUrl}\n` +
    nodos.join('\n') + mas
  );
}

const navegador = await chromium.launch();
const contexto = await navegador.newContext();
const pagina = await contexto.newPage();

const graves = [];
const leves = [];

for (const [ruta, nombre] of RUTAS) {
  for (const tema of TEMAS) {
    const violaciones = await auditar(pagina, ruta, tema);
    for (const v of violaciones) {
      (GRAVES.has(v.impact) ? graves : leves).push(describir(v, ruta, tema));
    }
    const marca = violaciones.length ? `${violaciones.length} aviso(s)` : 'limpio';
    console.log(`  ${tema.padEnd(7)} ${nombre.padEnd(30)} ${marca}`);
  }
}

await navegador.close();

if (leves.length) {
  console.log(`\nAvisos menores (${leves.length}), no bloquean:\n`);
  console.log(leves.join('\n\n'));
}

if (graves.length) {
  console.log(`\n${graves.length} problema(s) grave(s):\n`);
  console.log(graves.join('\n\n'));
  console.log(
    '\nSon de impacto «serious» o «critical». Si alguno resulta ser un falso ' +
    'positivo, no se silencia a mano: se corrige el marcado o se documenta ' +
    'aquí por qué la regla no aplica.'
  );
  process.exit(1);
}

console.log(`\nSin problemas graves en ${RUTAS.length * TEMAS.length} páginas.`);
