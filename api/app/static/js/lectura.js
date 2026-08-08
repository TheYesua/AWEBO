/**
 * Lectura en voz alta de las secciones de una SA (tarea 8a).
 *
 * Usa `SpeechSynthesis`, la API del propio navegador: gratuita, sin conexión,
 * sin proveedor y sin consumir tokens. Es el punto de partida sensato; solo si
 * se queda corta tiene sentido pagar por voces de proveedor.
 *
 * Dos piezas independientes, y a propósito:
 *
 *  - `textoLegible(elemento)` convierte un trozo de página en algo que se
 *    entienda al oírlo. Es una función pura sobre el DOM, sin nada de voz, y
 *    por eso se puede probar con Node sin navegador.
 *  - `Lector` envuelve la API de voz.
 *
 * Se extrae de lo **ya renderizado** y no del JSON de la sección. El contenido
 * tiene seis formas distintas —objetivos, conexión curricular, secuencia,
 * evaluación…— y convertir cada una por separado significaría seis funciones
 * que repiten lo que `render-secciones.js` ya sabe, y que se quedarían
 * desfasadas en cuanto una cambiara. Leyendo el DOM hay una sola función, y lo
 * que se escucha coincide con lo que se ve, que es justo lo que se espera de
 * una lectura en voz alta.
 */
(function (global) {
  'use strict';

  /* Elementos cuyo contenido no se lee. Los botones de acción no son parte de
     la sección, y un icono decorativo no tiene nada que decir.
     `.sr-only` NO está aquí: ese texto existe precisamente para quien no ve la
     pantalla, así que es el primero que hay que leer. */
  const NO_LEER = 'button, .seccion-gen__acciones, [aria-hidden="true"], script, style';

  /* Elementos que separan ideas. Al oírse, la diferencia entre un párrafo y el
     siguiente solo existe si hay una pausa: sin esto, `textContent` devuelve
     las palabras pegadas y se entiende la mitad. */
  const BLOQUE = new Set([
    'P', 'DIV', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER',
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'LI', 'UL', 'OL', 'DL', 'DT', 'DD', 'TR', 'BR', 'HR',
  ]);

  function _limpiar(texto) {
    return texto
      .replace(/[ \t ]+/g, ' ')
      // Varias pausas seguidas suenan como un silencio raro, no como énfasis.
      .replace(/\s*\n\s*/g, '\n')
      .replace(/\n{2,}/g, '\n')
      .replace(/\.\s*\./g, '.')
      .trim();
  }

  /**
   * Lee una tabla como pares «encabezado: valor».
   *
   * Una tabla leída celda a celda es ruido: «CE1 Identifica… Alto Medio Bajo
   * CE2…» no dice a qué corresponde cada cosa. Repetir el encabezado delante de
   * cada celda es lo que hacen los lectores de pantalla, y es la única forma de
   * que una rúbrica se entienda escuchándola.
   */
  function _tabla(tabla) {
    const encabezados = Array.from(tabla.querySelectorAll('thead th'))
      .map((th) => th.textContent.trim());

    const filas = Array.from(tabla.querySelectorAll('tbody tr'));
    return filas.map((fila) => {
      const celdas = Array.from(fila.children);
      return celdas.map((celda, i) => {
        const valor = celda.textContent.trim();
        if (!valor) return '';
        const cabecera = encabezados[i];
        // Sin encabezado (tabla sin thead) se lee la celda a secas: inventar
        // uno sería peor que no decir nada.
        return cabecera ? `${cabecera}: ${valor}` : valor;
      }).filter(Boolean).join('. ');
    }).filter(Boolean).join('\n');
  }

  /**
   * Devuelve el texto de `raiz` preparado para escucharse.
   *
   * @param {Element} raiz
   * @returns {string}
   */
  function textoLegible(raiz) {
    if (!raiz) return '';

    const partes = [];

    (function recorrer(nodo) {
      if (nodo.nodeType === 3) {           // texto
        partes.push(nodo.nodeValue);
        return;
      }
      if (nodo.nodeType !== 1) return;     // comentarios y demás

      if (nodo.matches && nodo.matches(NO_LEER)) return;
      // Un elemento oculto no está en pantalla; tampoco debe oírse.
      if (nodo.hasAttribute && nodo.hasAttribute('hidden')) return;

      if (nodo.tagName === 'TABLE') {
        partes.push('\n' + _tabla(nodo) + '\n');
        return;
      }

      const esBloque = BLOQUE.has(nodo.tagName);
      if (esBloque) partes.push('\n');
      Array.from(nodo.childNodes).forEach(recorrer);
      if (esBloque) partes.push('\n');
    })(raiz);

    return _limpiar(partes.join(''));
  }

  /* ------------------------------------------------------------------ */
  /* Voz                                                                 */
  /* ------------------------------------------------------------------ */

  const Lector = {
    /** Si el navegador trae la API. Los que no, simplemente no ofrecen nada. */
    get disponible() {
      return typeof global.speechSynthesis !== 'undefined'
        && typeof global.SpeechSynthesisUtterance !== 'undefined';
    },

    /**
     * Voces instaladas para un idioma.
     *
     * Chrome carga las voces de forma asíncrona y la primera llamada a
     * `getVoices()` suele devolver una lista vacía; por eso quien llama debe
     * esperar a `alListo`.
     */
    vocesPara(idioma) {
      if (!this.disponible) return [];
      const prefijo = String(idioma || '').slice(0, 2).toLowerCase();
      return global.speechSynthesis.getVoices()
        .filter((v) => v.lang.slice(0, 2).toLowerCase() === prefijo);
    },

    /**
     * Resuelve cuando la lista de voces está cargada.
     *
     * `voiceschanged` no se dispara en todos los navegadores —en Safari las
     * voces ya están listas— así que se resuelve también si `getVoices()` ya
     * devuelve algo, y hay un plazo máximo para no dejar la interfaz esperando
     * un evento que quizá no llegue nunca.
     */
    alListo(msMaximo = 2000) {
      return new Promise((resolver) => {
        if (!this.disponible) return resolver();
        if (global.speechSynthesis.getVoices().length) return resolver();

        const fin = () => {
          global.speechSynthesis.removeEventListener('voiceschanged', fin);
          clearTimeout(temporizador);
          resolver();
        };
        const temporizador = setTimeout(fin, msMaximo);
        global.speechSynthesis.addEventListener('voiceschanged', fin);
      });
    },

    /**
     * Lee `texto` en `idioma`. Corta cualquier lectura anterior.
     *
     * Solo una lectura a la vez: dos voces solapadas no se entienden, y es lo
     * que pasaría al pulsar el botón de otra sección sin parar la primera.
     */
    leer(texto, idioma, { alTerminar } = {}) {
      if (!this.disponible || !texto) return null;
      this.parar();

      const enunciado = new global.SpeechSynthesisUtterance(texto);
      enunciado.lang = idioma;
      const voz = this.vocesPara(idioma)[0];
      if (voz) enunciado.voice = voz;

      if (alTerminar) {
        enunciado.addEventListener('end', alTerminar);
        // También al cancelar o fallar: sin esto, el botón se queda en
        // «Parar» para siempre si la lectura se interrumpe.
        enunciado.addEventListener('error', alTerminar);
      }

      global.speechSynthesis.speak(enunciado);
      return enunciado;
    },

    parar() {
      if (this.disponible) global.speechSynthesis.cancel();
    },

    get leyendo() {
      return this.disponible && global.speechSynthesis.speaking;
    },
  };

  /* La voz sigue sonando al navegar a otra página: `speechSynthesis` vive en
     la ventana, no en el documento. Sin esto, salir del detalle deja una voz
     leyendo una sección que ya no está en pantalla. */
  if (typeof global.addEventListener === 'function') {
    global.addEventListener('pagehide', () => Lector.parar());
  }

  global.Lectura = { textoLegible, Lector };
})(typeof window !== 'undefined' ? window : globalThis);
