/**
 * Render legible de las 6 secciones LOMLOE de una SA.
 * Cada función recibe el JSON de la sección y devuelve un string HTML.
 *
 * Esquema esperado (ver app/prompts/secciones/*_v1.py):
 *  - descripcion:        {texto, pregunta_guia, producto_final}
 *  - objetivos:          {objetivos: [{texto, competencias: []}]}
 *  - conexion_curricular:{competencias[], criterios[], saberes[]}
 *  - secuencia_sesiones: {sesiones: [{numero, titulo, fase, duracion_minutos,
 *                                     recursos[], criterios[], actividades[]}]}
 *  - evaluacion:         {instrumentos: [{nombre, peso, momento}],
 *                          rubricas: [{criterio, niveles: {...}}]}
 *  - atencion_diversidad:{principios_dua[], ajustes_significativos[],
 *                          ajustes_no_significativos[]}
 *
 * Las funciones son DEFENSIVAS: si falta una clave o el formato no es
 * el esperado, no rompen — muestran lo que tengan o un aviso suave.
 */
(function (global) {
  'use strict';

  function escapar(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;',
      '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function ul(items, opciones = {}) {
    if (!Array.isArray(items) || items.length === 0) return '';
    const li = items.map((i) => `<li>${escapar(i)}</li>`).join('');
    return `<ul${opciones.clase ? ` class="${opciones.clase}"` : ''}>${li}</ul>`;
  }

  function chip(texto, clase = '') {
    return `<span class="chip ${clase}">${escapar(texto)}</span>`;
  }

  // ---------------------------------------------------------------------
  // 1. Descripción
  // ---------------------------------------------------------------------
  function renderDescripcion(d) {
    const partes = [];
    if (d.texto) {
      partes.push(`<p class="seccion-parrafo">${escapar(d.texto)}</p>`);
    }
    if (d.pregunta_guia) {
      partes.push(`
        <div class="callout callout--pregunta">
          <span class="callout__label">Pregunta guía</span>
          <p>${escapar(d.pregunta_guia)}</p>
        </div>`);
    }
    if (d.producto_final) {
      partes.push(`
        <div class="callout callout--producto">
          <span class="callout__label">Producto final</span>
          <p>${escapar(d.producto_final)}</p>
        </div>`);
    }
    return partes.join('') || renderFallback(d);
  }

  // ---------------------------------------------------------------------
  // 2. Objetivos
  // ---------------------------------------------------------------------
  function renderObjetivos(d) {
    const lista = Array.isArray(d.objetivos) ? d.objetivos : [];
    if (lista.length === 0) return renderVacio(MOTIVO_SIN_CURRICULO);

    const items = lista.map((o, idx) => {
      const comps = Array.isArray(o.competencias) && o.competencias.length
        ? `<div class="objetivo__chips">${o.competencias.map((c) => chip(c, 'chip--competencia')).join('')}</div>`
        : '';
      return `
        <li class="objetivo">
          <span class="objetivo__num">${idx + 1}</span>
          <div class="objetivo__cuerpo">
            <p>${escapar(o.texto)}</p>
            ${comps}
          </div>
        </li>`;
    }).join('');
    return `<ol class="lista-objetivos">${items}</ol>`;
  }

  // ---------------------------------------------------------------------
  // 3. Conexión curricular
  // ---------------------------------------------------------------------
  function renderConexionCurricular(d) {
    const bloques = [];

    const tablaJustif = (titulo, items, columnas) => {
      if (!Array.isArray(items) || !items.length) return '';
      const thead = columnas.map((c) => `<th>${escapar(c[1])}</th>`).join('');
      const tbody = items.map((it) => {
        const tds = columnas.map((c) => {
          const v = it[c[0]];
          return `<td>${escapar(v ?? '—')}</td>`;
        }).join('');
        return `<tr>${tds}</tr>`;
      }).join('');
      return `
        <div class="curr-bloque">
          <h4>${escapar(titulo)}</h4>
          <div class="tabla-responsiva">
            <table class="tabla-curr">
              <thead><tr>${thead}</tr></thead>
              <tbody>${tbody}</tbody>
            </table>
          </div>
        </div>`;
    };

    bloques.push(tablaJustif('Competencias específicas', d.competencias, [
      ['codigo', 'Código'], ['justificacion', 'Justificación'],
    ]));
    bloques.push(tablaJustif('Criterios de evaluación', d.criterios, [
      ['codigo', 'Código'], ['competencia', 'Comp.'], ['justificacion', 'Justificación'],
    ]));
    bloques.push(tablaJustif('Saberes básicos', d.saberes, [
      ['codigo', 'Código'], ['justificacion', 'Justificación'],
    ]));

    return bloques.filter(Boolean).join('') || renderVacio(MOTIVO_SIN_CURRICULO);
  }

  // ---------------------------------------------------------------------
  // 4. Secuencia de sesiones
  // ---------------------------------------------------------------------
  function renderSecuenciaSesiones(d) {
    const sesiones = Array.isArray(d.sesiones) ? d.sesiones : [];
    if (!sesiones.length) return renderFallback(d);

    return sesiones.map((s) => {
      const recursos = Array.isArray(s.recursos) && s.recursos.length
        ? `<div class="sesion-bloque">
             <h5>Recursos</h5>
             ${ul(s.recursos)}
           </div>`
        : '';
      const criterios = Array.isArray(s.criterios) && s.criterios.length
        ? `<div class="sesion-bloque">
             <h5>Criterios trabajados</h5>
             <div class="chips-row">
               ${s.criterios.map((c) => chip(c, 'chip--criterio')).join('')}
             </div>
           </div>`
        : '';
      const actividades = Array.isArray(s.actividades) && s.actividades.length
        ? `<div class="sesion-bloque">
             <h5>Actividades</h5>
             <ol class="lista-actividades">
               ${s.actividades.map((a) => {
                 const txt = typeof a === 'string' ? a : (a.descripcion ?? '');
                 return `<li>${escapar(txt)}</li>`;
               }).join('')}
             </ol>
           </div>`
        : '';

      return `
        <article class="sesion">
          <header class="sesion__head">
            <span class="sesion__num">Sesión ${escapar(s.numero ?? '?')}</span>
            <h4 class="sesion__titulo">${escapar(s.titulo ?? '')}</h4>
            <div class="sesion__meta">
              ${s.fase ? chip(s.fase, 'chip--fase') : ''}
              ${s.duracion_minutos ? `<span class="sesion__dur">${escapar(s.duracion_minutos)} min</span>` : ''}
            </div>
          </header>
          ${actividades}
          ${recursos}
          ${criterios}
        </article>`;
    }).join('');
  }

  // ---------------------------------------------------------------------
  // 5. Evaluación
  // ---------------------------------------------------------------------
  function renderEvaluacion(d) {
    const partes = [];

    if (Array.isArray(d.instrumentos) && d.instrumentos.length) {
      const filas = d.instrumentos.map((i) => `
        <tr>
          <td>${escapar(i.nombre)}</td>
          <td>${escapar(i.momento ?? '—')}</td>
          <td class="num">${escapar(i.peso ?? '—')}${i.peso != null ? '%' : ''}</td>
        </tr>`).join('');
      partes.push(`
        <div class="eval-bloque">
          <h4>Instrumentos de evaluación</h4>
          <div class="tabla-responsiva">
            <table class="tabla-eval">
              <thead><tr><th>Instrumento</th><th>Momento</th><th>Peso</th></tr></thead>
              <tbody>${filas}</tbody>
            </table>
          </div>
        </div>`);
    }

    if (Array.isArray(d.rubricas) && d.rubricas.length) {
      const NIVELES = [
        ['excelente', 'Excelente'],
        ['logrado', 'Logrado'],
        ['en_proceso', 'En proceso'],
        ['iniciado', 'Iniciado'],
      ];
      const rubricasHtml = d.rubricas.map((r) => {
        const filas = NIVELES.map(([k, lab]) => {
          const val = (r.niveles && r.niveles[k]) || '—';
          return `<tr><th>${lab}</th><td>${escapar(val)}</td></tr>`;
        }).join('');
        return `
          <details class="rubrica" open>
            <summary>
              <strong>Criterio ${escapar(r.criterio ?? '—')}</strong>
            </summary>
            <div class="tabla-responsiva">
              <table class="tabla-rubrica">
                <tbody>${filas}</tbody>
              </table>
            </div>
          </details>`;
      }).join('');
      partes.push(`
        <div class="eval-bloque">
          <h4>Rúbricas por criterio</h4>
          ${rubricasHtml}
        </div>`);
    }

    return partes.join('') || renderFallback(d);
  }

  // ---------------------------------------------------------------------
  // 6. Atención a la diversidad (DUA)
  //
  // Si la página detalle expone window.SA_ADAPTACION = {tipo: ...}
  // ocultamos el bloque del tipo opuesto a la adaptación, por si el LLM
  // ignora la instrucción de devolver lista vacía.
  // ---------------------------------------------------------------------
  function renderAtencionDiversidad(d) {
    const bloque = (titulo, items, clase) => {
      if (!Array.isArray(items) || !items.length) return '';
      return `
        <div class="dua-bloque ${clase}">
          <h4>${escapar(titulo)}</h4>
          ${ul(items, { clase: 'lista-dua' })}
        </div>`;
    };

    const adapt = global.SA_ADAPTACION || {};
    const ocultarACS  = adapt.tipo === 'no_significativa';
    const ocultarACNS = adapt.tipo === 'significativa';

    const html =
      bloque('Principios DUA aplicados', d.principios_dua, 'dua-bloque--dua') +
      (ocultarACNS ? '' : bloque('Ajustes no significativos', d.ajustes_no_significativos, 'dua-bloque--acns')) +
      (ocultarACS  ? '' : bloque('Ajustes significativos', d.ajustes_significativos, 'dua-bloque--acs'));
    return html || renderFallback(d);
  }

  // ---------------------------------------------------------------------
  // Fallback: si no reconocemos el formato, mostramos JSON formateado
  // ---------------------------------------------------------------------
  /* Volcado en bruto. Último recurso: solo para contenido con una forma que
     no sabemos interpretar, donde enseñar el dato crudo es mejor que ocultarlo. */
  function renderFallback(d) {
    return `<pre class="seccion-json">${escapar(JSON.stringify(d, null, 2))}</pre>`;
  }

  /* Sección sin contenido. Es distinto de "no sé pintar esto": aquí sabemos
     exactamente qué pasó y podemos decir qué hacer. Un `{"objetivos": []}`
     delante de un docente no explica nada y parece una avería. */
  function renderVacio(motivo) {
    return `
      <div class="seccion-vacia">
        <p><strong>Esta sección se ha generado vacía.</strong></p>
        <p>${escapar(motivo)}</p>
      </div>`;
  }

  const MOTIVO_SIN_CURRICULO =
    'Suele ocurrir cuando la materia y el curso de la situación no tienen ' +
    'currículo LOMLOE cargado: el modelo no puede citar criterios ni saberes ' +
    'que no existen, y tiene prohibido inventarlos. Comprueba la materia en ' +
    'los datos de la situación —en 4.º de la ESO, por ejemplo, Matemáticas ' +
    'se desdobla en Matemáticas A y Matemáticas B— y vuelve a generar.';

  // ---------------------------------------------------------------------
  // API pública
  // ---------------------------------------------------------------------
  const RENDERS = {
    descripcion: renderDescripcion,
    objetivos: renderObjetivos,
    conexion_curricular: renderConexionCurricular,
    secuencia_sesiones: renderSecuenciaSesiones,
    evaluacion: renderEvaluacion,
    atencion_diversidad: renderAtencionDiversidad,
  };

  global.renderSeccion = function (clave, datos) {
    const fn = RENDERS[clave];
    if (typeof fn !== 'function') return renderFallback(datos);
    try {
      return fn(datos);
    } catch (err) {
      console.error(`Error renderizando sección «${clave}»:`, err);
      return renderFallback(datos);
    }
  };
})(window);
