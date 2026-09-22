/* Pequeño script global: detecta sesión y oculta/muestra elementos
   con [data-auth="required"] o [data-auth="anonymous"]. También
   conecta el botón de logout. */

/* -------------------------------------------------------------------------
   FECHAS
   -------------------------------------------------------------------------
   Un único formateador para toda la aplicación. Antes había cinco, uno por
   plantilla, y **el de `/admin` estaba roto**: llamaba a
   `toLocaleDateString()` sin argumento de idioma, así que usaba el del
   NAVEGADOR. En un Chrome en inglés eso da 09/22/2026 — mes, día, año — en una
   aplicación para docentes españoles.

   POR QUÉ EL IDIOMA ESTÁ FIJADO Y NO SIGUE A LA INTERFAZ
   -------------------------------------------------------
   Parecería más fino usar el idioma elegido, pero no lo es. Catalán y gallego
   escriben la fecha igual que el castellano, y **el euskera no**: `eu` da
   2026/09/22. Cambiar el orden de la fecha según el idioma de la interfaz
   sorprendería a quien lee «22 de septiembre» en el documento y «2026/09/22»
   en el listado de al lado.

   La aplicación es para centros españoles y la fecha va en formato español,
   punto. Si algún día se ofrece fuera, esto es lo que hay que revisar, y está
   en un solo sitio.
   ------------------------------------------------------------------------- */
window.AWEBO = window.AWEBO || {};

/* Fijado, no `document.documentElement.lang` ni `undefined`. Ver arriba. */
window.AWEBO.LOCALE_FECHAS = 'es-ES';

/**
 * Una fecha ISO en formato español.
 *
 * @param {string} iso        Lo que devuelve el API.
 * @param {string} [precision]  `'minutos'` añade HH:MM; `'segundos'`, HH:MM:SS.
 *                              Sin ella, solo la fecha.
 * @returns {string} Cadena vacía si no hay valor, y el original tal cual si no
 *                   se puede interpretar — nunca «Invalid Date», que es lo que
 *                   sale por defecto y no dice nada a quien lo lee.
 */
window.AWEBO.fecha = function (iso, precision) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;

  const opciones = { day: '2-digit', month: '2-digit', year: 'numeric' };
  if (precision === 'minutos' || precision === 'segundos') {
    opciones.hour = '2-digit';
    opciones.minute = '2-digit';
  }
  if (precision === 'segundos') opciones.second = '2-digit';

  return d.toLocaleString(window.AWEBO.LOCALE_FECHAS, opciones);
};

/* -------------------------------------------------------------------------
   EL TOKEN CSRF VIAJA SOLO
   -------------------------------------------------------------------------
   Esto envuelve `window.fetch` para que añada la cabecera `X-CSRF-Token` a
   toda petición del propio origen que cambie estado.

   POR QUÉ ASÍ Y NO LLAMADA POR LLAMADA
   ------------------------------------
   Hay unas cuarenta llamadas a `fetch` repartidas por doce plantillas. Tocarlas
   una a una es trabajo mecánico con un fallo silencioso al final del camino:
   la que se olvide no da error al escribirla, da un botón que deja de
   funcionar en producción. Y la número cuarenta y uno, la que alguien escriba
   dentro de tres meses, no la cubre nadie.

   Envolviendo `fetch` no hay nada que recordar. Lo que se paga es que el
   mecanismo queda lejos de donde se usa, y de ahí este comentario.

   Va al principio del fichero, y `base.html` carga este fichero antes del
   bloque `scripts` de cada página: cuando alguien llama a `fetch`, ya está
   envuelto.
   ------------------------------------------------------------------------- */
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.getAttribute('content') : '';
  if (!token) return;

  /* La misma lista que el servidor (app/csrf.py). */
  const SEGUROS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE']);
  const original = window.fetch.bind(window);

  /* Solo al propio origen. Mandar el token a un tercero sería regalárselo, que
     es exactamente lo que esto intenta evitar. */
  const esPropio = (recurso) => {
    try {
      const url = new URL(
        typeof recurso === 'string' ? recurso : recurso.url,
        window.location.href
      );
      return url.origin === window.location.origin;
    } catch (e) {
      /* Si no se puede interpretar, no se manda. Callarse el token es un
         botón que falla; mandarlo a ciegas es una filtración. */
      return false;
    }
  };

  window.fetch = function (recurso, opciones) {
    const opts = opciones || {};
    const metodo = (
      opts.method || (recurso && recurso.method) || 'GET'
    ).toUpperCase();

    if (SEGUROS.has(metodo) || !esPropio(recurso)) {
      return original(recurso, opciones);
    }

    /* `Headers` y no un objeto plano: las llamadas de las plantillas pasan las
       cabeceras en las tres formas que admite fetch —objeto, array, Headers— y
       fusionarlas a mano se equivoca con alguna. */
    const cabeceras = new Headers(opts.headers || undefined);
    if (!cabeceras.has('X-CSRF-Token')) {
      cabeceras.set('X-CSRF-Token', token);
    }
    return original(recurso, Object.assign({}, opts, { headers: cabeceras }));
  };
})();

/* El selector de idioma se envía al cambiarlo. Vivía en un atributo
   `onchange` de `base.html`, y de ahí salió: una CSP con `nonce` prohíbe los
   atributos de evento en línea, porque no hay manera de firmar el código que
   va dentro de un atributo. El `<noscript>` de al lado sigue ofreciendo el
   botón «Cambiar» a quien no tenga JavaScript. */
(function () {
  const selector = document.getElementById('selector-idioma');
  if (selector && selector.form) {
    selector.addEventListener('change', () => selector.form.submit());
  }
})();

(async function () {
  const setAuthState = (usuario) => {
    const autenticado = !!usuario;
    document.querySelectorAll('[data-auth="required"]').forEach((el) => {
      el.hidden = !autenticado;
    });
    document.querySelectorAll('[data-auth="anonymous"]').forEach((el) => {
      el.hidden = autenticado;
    });
    /* Elementos que solo tienen sentido para un rol concreto. Esto es
       COSMÉTICO: oculta lo que no sirve, no protege nada. Quien escriba
       /admin a mano se topa con el decorador de permisos del servidor, que
       es donde vive la autorización de verdad.

       No se usa para encabezados que sean destino de un aria-labelledby: por
       esa vía el nombre accesible incluye el texto de los elementos con
       `hidden`, y se anunciarían las dos variantes seguidas. Para eso,
       cambiar el texto (ver index.html). */
    document.querySelectorAll('[data-rol]').forEach((el) => {
      el.hidden = !(usuario && usuario.rol === el.dataset.rol);
    });
  };

  let usuario = null;
  try {
    const res = await fetch('/me', { headers: { 'Accept': 'application/json' } });
    if (res.ok) usuario = await res.json();
  } catch (_) { /* offline o similar */ }

  setAuthState(usuario);

  // Mensaje en la página de inicio
  const estadoMsg = document.getElementById('estado-msg');
  if (estadoMsg) {
    estadoMsg.textContent = usuario
      ? `Sesión iniciada como ${usuario.nombre} (${usuario.correo}).`
      : 'No hay sesión iniciada.';
  }

  // Botón de logout
  const btn = document.getElementById('logout-btn');
  if (btn) {
    btn.addEventListener('click', async () => {
      await fetch('/auth/logout', { method: 'POST' });
      window.location.href = '/';
    });
  }
})();
