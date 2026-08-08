/* Pequeño script global: detecta sesión y oculta/muestra elementos
   con [data-auth="required"] o [data-auth="anonymous"]. También
   conecta el botón de logout. */

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
