/* Catálogos de valores controlados para los desplegables del frontend.
   Coherentes con los descritos en el documento (cap. 4 y 5).             */

window.CATALOGOS = {
  cursos: ['1º ESO', '2º ESO', '3º ESO', '4º ESO'],

  // Matemáticas A y B son los dos itinerarios oficiales de 4.º ESO
  // según el RD 217/2022 y la Orden EFP/754/2022. Para 1.º a 3.º se
  // usa "Matemáticas" sin sufijo.
  materias: ['Tecnología', 'Lengua', 'Matemáticas', 'Matemáticas A', 'Matemáticas B', 'Inglés'],

  metodologias: [
    'Aprendizaje basado en proyectos (ABP)',
    'Aprendizaje cooperativo',
    'Flipped classroom',
    'Aprendizaje basado en retos',
    'Gamificación',
    'Aprendizaje-servicio',
    'Trabajo por proyectos',
    'Clase magistral participativa',
  ],
};

/**
 * Rellena un <select> con las opciones del catálogo indicado.
 * @param {HTMLSelectElement} sel
 * @param {string[]} opciones
 * @param {{placeholder?: string, valor?: string}} opts
 */
window.rellenarSelect = function (sel, opciones, opts = {}) {
  if (!sel) return;
  sel.innerHTML = '';
  if (opts.placeholder) {
    const op = document.createElement('option');
    op.value = '';
    op.textContent = opts.placeholder;
    sel.appendChild(op);
  }
  for (const v of opciones) {
    const op = document.createElement('option');
    op.value = v;
    op.textContent = v;
    sel.appendChild(op);
  }
  // Si el valor preexistente no está en la lista, lo añadimos para no
  // perderlo (situaciones antiguas creadas con texto libre).
  if (opts.valor && !opciones.includes(opts.valor)) {
    const op = document.createElement('option');
    op.value = opts.valor;
    op.textContent = opts.valor + ' (heredado)';
    sel.appendChild(op);
  }
  if (opts.valor) sel.value = opts.valor;
};


/* =============================================================================
   Cobertura curricular: qué materias existen en cada curso, y al revés.
   -----------------------------------------------------------------------------
   Vive aquí y no en una plantilla porque la usan dos pantallas —crear y editar
   una situación— y porque las dos funciones puras se pueden probar sin
   navegador (ver tests/js/cobertura.test.js).

   El problema que resuelve: los desplegables de curso y materia eran
   independientes, así que se podía elegir "Matemáticas · 4º ESO", combinación
   que no existe —en 4.º la materia se desdobla en los itinerarios A y B—. La
   situación se generaba sin currículo al que anclarse y salían los objetivos y
   la conexión curricular vacíos.
   ============================================================================= */
(function (global) {
  'use strict';

  /* "1º ESO" antes que "2º ESO"; numeric para que 10.º no fuese antes que 2.º */
  const porCurso = (a, b) => a.localeCompare(b, 'es', { numeric: true });
  const porTexto = (a, b) => a.localeCompare(b, 'es');

  /**
   * Cursos en los que se imparte `materia`. Sin materia, todos los cursos
   * que aparezcan en el catálogo.
   * @param {{materia: string, cursos: string[]}[]} cobertura
   */
  function cursosDe(cobertura, materia) {
    if (!materia) {
      const todos = new Set();
      for (const c of cobertura) for (const curso of c.cursos) todos.add(curso);
      return [...todos].sort(porCurso);
    }
    const entrada = cobertura.find((c) => c.materia === materia);
    return entrada ? [...entrada.cursos].sort(porCurso) : [];
  }

  /**
   * Materias que se imparten en `curso`. Sin curso, todas las del catálogo.
   */
  function materiasDe(cobertura, curso) {
    const filtradas = curso
      ? cobertura.filter((c) => c.cursos.includes(curso))
      : cobertura;
    return filtradas.map((c) => c.materia).sort(porTexto);
  }

  /**
   * Enlaza dos <select> para que cada uno restrinja al otro, en ambos
   * sentidos: al elegir curso se acotan las materias, y al elegir materia se
   * acotan los cursos.
   *
   * No hay riesgo de bucle: cambiar el valor de un <select> desde JavaScript
   * no dispara su evento `change`. Y cada repintado parte SIEMPRE de la
   * cobertura completa filtrada por el otro campo, nunca de la lista ya
   * filtrada, que iría estrechándose sin poder volver atrás.
   */
  function enlazar({
    cobertura,
    selCurso,
    selMateria,
    aviso,
    preservar = false,
    cursoActual = '',
    materiaActual = '',
  }) {
    // En la pantalla de edición los <select> llegan vacíos y los valores
    // vienen de la SA cargada por fetch, así que se pasan explícitamente.
    const cursoInicial = selCurso.value || cursoActual;
    const materiaInicial = selMateria.value || materiaActual;

    const avisar = (texto) => {
      if (!aviso) return;
      aviso.textContent = texto || '';
      aviso.hidden = !texto;
    };

    function repintar(sel, opciones, deseado, placeholder) {
      const valido = opciones.includes(deseado);
      global.rellenarSelect(sel, opciones, {
        placeholder,
        // `preservar` mantiene un valor fuera de catálogo marcándolo como
        // heredado: en una SA ya creada no se puede borrar en silencio lo que
        // el docente eligió, aunque hoy sepamos que no era válido.
        valor: valido ? deseado : (preservar && deseado ? deseado : undefined),
      });
      return valido;
    }

    function alCambiarCurso() {
      const curso = selCurso.value;
      const materias = materiasDe(cobertura, curso);
      const previa = selMateria.value;
      const seguia = repintar(selMateria, materias, previa, 'Selecciona una materia…');
      avisar(
        previa && !seguia
          ? `«${previa}» no se imparte en ${curso}. Elige una de las materias disponibles.`
          : ''
      );
    }

    function alCambiarMateria() {
      const materia = selMateria.value;
      const cursos = cursosDe(cobertura, materia);
      const previo = selCurso.value;
      const seguia = repintar(selCurso, cursos, previo, 'Selecciona un curso…');
      avisar(
        previo && !seguia
          ? `«${materia}» no se imparte en ${previo}. Elige uno de los cursos disponibles.`
          : ''
      );
    }

    selCurso.addEventListener('change', alCambiarCurso);
    selMateria.addEventListener('change', alCambiarMateria);

    // Pintado inicial: cada lista acotada por lo que ya tenga el otro campo.
    repintar(selCurso, cursosDe(cobertura, materiaInicial), cursoInicial, 'Selecciona un curso…');
    repintar(selMateria, materiasDe(cobertura, cursoInicial), materiaInicial, 'Selecciona una materia…');

    // Una SA antigua puede arrastrar una combinación que hoy sabemos inválida.
    if (preservar && cursoInicial && materiaInicial &&
        !cursosDe(cobertura, materiaInicial).includes(cursoInicial)) {
      avisar(
        `«${materiaInicial}» no tiene currículo en ${cursoInicial}. ` +
        `Esta situación no se podrá generar hasta que lo corrijas.`
      );
    }
  }

  function cargar() {
    return fetch('/api/curriculo/cobertura')
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []);
  }

  /* ---------------------------------------------------------------------
     Materias cuyo nombre no basta para saber qué son
     ---------------------------------------------------------------------
     Hoy solo Matemáticas A y B. Aparecen en el desplegable como dos entradas
     sin más señas, y la duda razonable —¿es ciencias contra letras?, ¿es una
     continuación de la otra?— no la resuelve el nombre.

     Los textos no viven aquí sino en las plantillas, porque este fichero es
     estático y no pasa por Jinja: sin `_()` las explicaciones se quedarían en
     castellano en las otras tres lenguas.
     ------------------------------------------------------------------ */

  /** Devuelve la explicación de `materia`, o cadena vacía si no tiene. */
  function explicarMateria(materia, textos) {
    if (materia === 'Matemáticas A') return textos.matematicasA || '';
    if (materia === 'Matemáticas B') return textos.matematicasB || '';
    return '';
  }

  /**
   * Enlaza un <select> de materia con el párrafo donde mostrar su explicación.
   * Devuelve la función de pintado para que el llamante la dispare cuando el
   * <select> ya tenga valor: al enlazar suele estar vacío porque la cobertura
   * llega por fetch.
   */
  function enlazarExplicacion(selMateria, destino, textos) {
    if (!selMateria || !destino) return () => {};
    const pintar = () => {
      const texto = explicarMateria(selMateria.value, textos);
      destino.textContent = texto;
      destino.hidden = !texto;
    };
    selMateria.addEventListener('change', pintar);
    return pintar;
  }

  global.Cobertura = {
    cursosDe,
    materiasDe,
    enlazar,
    cargar,
    explicarMateria,
    enlazarExplicacion,
  };
})(window);
