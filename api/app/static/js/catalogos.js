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

  const porTexto = (a, b) => a.localeCompare(b, 'es');

  /* "1º ESO" antes que "2º ESO"; numeric para que 10.º no fuese antes que 2.º.
     Y primero la etapa: con Bachillerato cargado, ordenar solo por número
     intercalaba las dos —«1º Bachillerato, 1º ESO, 2º Bachillerato, 2º ESO»—,
     que es un desplegable que nadie lee de un vistazo.

     Aquí SÍ se mira el texto del curso para saber la etapa, al revés que en el
     servidor. Es distinto: esto solo decide en qué orden se pintan unas
     opciones. Si mañana una etapa nueva no se reconoce, sus cursos salen al
     final agrupados, que es una fealdad y no un dato equivocado. */
  const ORDEN_ETAPAS = ['ESO', 'Bachillerato'];
  const etapaDelCurso = (curso) => {
    const i = ORDEN_ETAPAS.findIndex((e) => curso.includes(e));
    return i === -1 ? ORDEN_ETAPAS.length : i;
  };
  const porCurso = (a, b) =>
    etapaDelCurso(a) - etapaDelCurso(b) ||
    a.localeCompare(b, 'es', { numeric: true });

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
    /* Se acumulan TODAS las entradas de esa materia, no la primera.
       Desde que la cobertura viene partida por etapa hay materias con dos
       entradas —«Matematika» existe en la ESO y en Bachillerato del País
       Vasco—, y un `find` habría devuelto los cursos de una sola de las dos
       sin que nada fallara: el desplegable, simplemente, se dejaría cursos
       fuera. */
    const todos = new Set();
    for (const c of cobertura) {
      if (c.materia === materia) for (const curso of c.cursos) todos.add(curso);
    }
    return [...todos].sort(porCurso);
  }

  /**
   * Materias que se imparten en `curso`. Sin curso, todas las del catálogo.
   */
  function materiasDe(cobertura, curso) {
    const filtradas = curso
      ? cobertura.filter((c) => c.cursos.includes(curso))
      : cobertura;
    // Sin repetir: la misma materia puede venir en dos etapas.
    return [...new Set(filtradas.map((c) => c.materia))].sort(porTexto);
  }

  /* -------------------------------------------------------------------------
     La etapa
     -------------------------------------------------------------------------
     No es un tercer campo que se restrinja con los otros dos, como el curso y
     la materia entre sí: es un **filtro previo** que decide sobre qué catálogo
     trabajan los dos. Por eso no entra en `enlazar` con más ramas, sino que
     recorta la cobertura y se vuelve a enlazar con la recortada — el mismo
     mecanismo que ya usa el cambio de provincia, y que `enlazar` sabe deshacer.

     El orden es fijo y no alfabético: «Bachillerato» va detrás de «ESO» porque
     es lo que viene después, y ordenarlo por texto lo pondría delante.
     ---------------------------------------------------------------------- */

  /* `ORDEN_ETAPAS` se declara arriba, junto al comparador de cursos: las dos
     cosas dependen del mismo orden y tenerlo en dos sitios era la manera de
     que un día dijeran cosas distintas. */

  /** Etapas presentes en la cobertura, en orden educativo. */
  function etapasDe(cobertura) {
    const vistas = new Set(cobertura.map((c) => c.etapa).filter(Boolean));
    const conocidas = ORDEN_ETAPAS.filter((e) => vistas.has(e));
    // Lo que no esté en la lista va detrás, en orden estable: si mañana entra
    // FP, aparece en el desplegable en vez de desaparecer en silencio.
    const resto = [...vistas].filter((e) => !ORDEN_ETAPAS.includes(e)).sort(porTexto);
    return [...conocidas, ...resto];
  }

  /** La cobertura de una etapa. Sin etapa, la entera. */
  function soloDeLaEtapa(cobertura, etapa) {
    return etapa ? cobertura.filter((c) => c.etapa === etapa) : cobertura;
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
    /* SEGUNDA LLAMADA SOBRE LOS MISMOS <select>
       ------------------------------------------
       Al cambiar de provincia se vuelve a llamar aquí con la cobertura de la
       comunidad nueva, y eso obliga a deshacer dos cosas de la anterior.

       1) Los oyentes. `addEventListener` no sustituye: acumula. El de la
          llamada vieja sigue vivo y **captura la cobertura vieja** en su
          cierre, así que tocar el curso repintaba las materias con el catálogo
          de la provincia anterior. No da ningún error: ofrece materias de otra
          comunidad como si fueran las de esta.

       2) El valor que ya tuvieran. El `||` de abajo existe porque en la
          pantalla de edición los <select> llegan vacíos y lo que hay que
          poner viene del fetch. Pero en la segunda llamada lo que tienen es lo
          que pintamos nosotros la vez anterior, no lo que dijo el servidor:
          respetarlo dejaría elegida una materia de la comunidad de antes. */
    const rehecho = Boolean(selCurso._enlaceCobertura);
    if (rehecho) {
      selCurso.removeEventListener('change', selCurso._enlaceCobertura);
      selMateria.removeEventListener('change', selMateria._enlaceCobertura);
    }

    const cursoInicial = rehecho ? cursoActual : (selCurso.value || cursoActual);
    const materiaInicial = rehecho ? materiaActual : (selMateria.value || materiaActual);

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
    // Guardados para poder quitarlos si se vuelve a enlazar (ver arriba).
    selCurso._enlaceCobertura = alCambiarCurso;
    selMateria._enlaceCobertura = alCambiarMateria;

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

  function cargar(provincia) {
    /* La cobertura depende de la comunidad, y la comunidad de la provincia
       elegida en el formulario — que puede no ser la del perfil. Sin este
       parámetro el desplegable ofrecería las materias del perfil para una SdA
       que se va a generar contra otro currículo. */
    const url = provincia
      ? `/api/curriculo/cobertura?provincia=${encodeURIComponent(provincia)}`
      : '/api/curriculo/cobertura';
    return fetch(url)
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []);
  }

  /* -------------------------------------------------------------------------
     Provincias: el desplegable agrupado por comunidad
     -------------------------------------------------------------------------
     Se pide al servidor en vez de escribirlo aquí porque la marca de «tiene
     currículo cargado» sale de la base de datos. Una lista fija en este
     fichero se desincronizaría el día que se cargue una comunidad nueva, y
     seguiría avisando de que no hay currículo cuando ya lo hay.
     ---------------------------------------------------------------------- */

  function cargarProvincias() {
    return fetch('/api/curriculo/provincias')
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => []);
  }

  /**
   * Rellena un <select> con <optgroup> por comunidad.
   *
   * Las provincias sin currículo cargado se marcan en la etiqueta en vez de
   * ocultarse: un docente de Aragón existe aunque AWEBO no tenga su decreto, y
   * esconderle su provincia no la hace desaparecer — le deja sin entender qué
   * se espera que elija.
   */
  function pintarProvincias(sel, grupos, seleccionada, sinCurriculoTexto) {
    if (!sel) return;
    const previo = seleccionada || sel.value;
    // Se conserva el primer <option> si es el placeholder («Elige…»).
    const placeholder = sel.querySelector('option[value=""]');
    sel.innerHTML = '';
    if (placeholder) sel.appendChild(placeholder);

    grupos.forEach((grupo) => {
      const og = document.createElement('optgroup');
      og.label = grupo.comunidad;
      grupo.provincias.forEach((p) => {
        const op = document.createElement('option');
        op.value = p.codigo;
        op.textContent = p.tiene_curriculo
          ? p.nombre
          : `${p.nombre} ${sinCurriculoTexto || '(sin currículo)'}`;
        if (!p.tiene_curriculo) op.dataset.sinCurriculo = '1';
        og.appendChild(op);
      });
      sel.appendChild(og);
    });
    if (previo) sel.value = previo;
  }

  /**
   * Ata la provincia al curso y a la materia.
   *
   * Curso y materia llegan `disabled` desde la plantilla y solo se habilitan
   * cuando hay provincia. El aviso que explica por qué está bloqueado se
   * oculta al desbloquear: dejarlo puesto convertiría una instrucción útil en
   * ruido permanente.
   */
  function enlazarProvincia({ selProvincia, selCurso, selMateria, aviso, alCambiar }) {
    if (!selProvincia) return;

    const aplicar = () => {
      const hay = Boolean(selProvincia.value);
      [selCurso, selMateria].forEach((s) => {
        if (!s) return;
        s.disabled = !hay;
      });
      if (aviso) aviso.hidden = hay;
      if (hay && typeof alCambiar === 'function') alCambiar(selProvincia.value);
    };

    selProvincia.addEventListener('change', aplicar);
    aplicar();
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

  /**
   * Ata el <select> de etapa a los de curso y materia.
   *
   * Al cambiar la etapa se vuelve a enlazar con la cobertura recortada, así
   * que curso y materia pasan a ofrecer solo lo de esa etapa. Devuelve la
   * función de aplicación para que el llamante la dispare cuando quiera.
   *
   * POR QUÉ SE VACÍAN CURSO Y MATERIA AL CAMBIAR DE ETAPA
   * ------------------------------------------------------
   * Porque casi nunca sobreviven. «3º ESO» no existe en Bachillerato, y una
   * materia que exista en las dos —«Matematika»— tendría otros cursos. Dejar
   * el valor anterior puesto obligaría a comprobar en cada combinación si
   * sigue siendo válido, y el caso en que lo es no compensa: quien cambia de
   * etapa está eligiendo otra cosa, no matizando la que tenía.
   *
   * Lo que sí se hace es **decirlo**, en vez de borrarlo en silencio.
   */
  function enlazarEtapa({
    cobertura,
    selEtapa,
    selCurso,
    selMateria,
    aviso,
    placeholder = 'Todas',
    etapaActual = '',
    alCambiar,
  }) {
    if (!selEtapa) return () => {};

    const etapas = etapasDe(cobertura);
    global.rellenarSelect(selEtapa, etapas, {
      placeholder,
      valor: etapas.includes(etapaActual) ? etapaActual : undefined,
    });

    // Con una sola etapa cargada el desplegable no decide nada: se oculta en
    // vez de ofrecer una elección que no lo es. Vuelve solo si algún día se
    // carga otra, porque esto se recalcula con cada cobertura.
    const contenedor = selEtapa.closest('.field') || selEtapa.parentElement;
    if (contenedor) contenedor.hidden = etapas.length < 2;

    const aplicar = (limpiando) => {
      const etapa = selEtapa.value;
      if (limpiando) {
        selCurso.value = '';
        selMateria.value = '';
      }
      enlazar({
        cobertura: soloDeLaEtapa(cobertura, etapa),
        selCurso,
        selMateria,
        aviso,
        cursoActual: '',
        materiaActual: '',
      });
      if (typeof alCambiar === 'function') alCambiar(etapa);
    };

    if (selEtapa._enlaceEtapa) {
      selEtapa.removeEventListener('change', selEtapa._enlaceEtapa);
    }
    const alCambiarEtapa = () => aplicar(true);
    selEtapa.addEventListener('change', alCambiarEtapa);
    selEtapa._enlaceEtapa = alCambiarEtapa;

    return aplicar;
  }

  global.Cobertura = {
    cursosDe,
    materiasDe,
    etapasDe,
    soloDeLaEtapa,
    enlazar,
    enlazarEtapa,
    cargar,
    explicarMateria,
    enlazarExplicacion,
    cargarProvincias,
    pintarProvincias,
    enlazarProvincia,
  };
})(window);
