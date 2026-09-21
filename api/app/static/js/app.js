/* Pequeño script global: detecta sesión y oculta/muestra elementos
   con [data-auth="required"] o [data-auth="anonymous"]. También
   conecta el botón de logout. */

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
