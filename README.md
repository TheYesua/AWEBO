# AWEBO — Aplicación WEB para dOcentes

Generador de **Situaciones de Aprendizaje LOMLOE** asistido por IA.

Permite al profesorado de Secundaria crear, editar y exportar Situaciones de
Aprendizaje (SA) conformes al Real Decreto 217/2022, con generación automática
de las seis secciones del currículo (descripción, objetivos, conexión
curricular, secuencia de sesiones, evaluación y atención a la diversidad)
mediante un LLM, anclando los criterios y saberes al catálogo oficial.

> **Origen**: este proyecto nace del Trabajo de Fin de Grado en Ingeniería
> Informática (Universidad de Granada) de Jesús José Cantero López. AWEBO es su
> continuación como proyecto personal: entorno independiente, historial de
> versiones propio y hoja de ruta abierta. El TFG entregado permanece
> congelado en <https://github.com/TheYesua/TFG>.

---

## Arquitectura

Despliegue mediante Docker Compose. Cinco servicios principales más uno
opcional para desarrollo:

| Servicio   | Puerto host           | Rol                                                       |
|------------|-----------------------|-----------------------------------------------------------|
| `nginx`    | `8090`                | Reverse proxy, único punto de entrada público             |
| `api`      | (interno)             | Flask + Gunicorn. Auth, CRUD, render Jinja                |
| `worker`   | (interno)             | Celery. Llamadas largas al LLM y exportaciones pesadas    |
| `postgres` | `5433`                | Persistencia                                              |
| `redis`    | (interno)             | Broker Celery + caché + sesiones server-side              |
| `adminer`  | `8091` (perfil `dev`) | Cliente web para inspeccionar PostgreSQL                  |

> Los puertos están desplazados respecto al TFG original (8080/8081/5432) para
> que ambos entornos puedan convivir y ejecutarse simultáneamente. El proyecto
> Compose se llama `awebo`, con contenedores `awebo-*` y volúmenes
> `awebo_postgres_data` / `awebo_redis_data`: no comparte ningún estado con
> `tfg-sa`.

### Decisiones técnicas clave

- **No SPA**: HTML renderizado en servidor con **Jinja2** + JavaScript "vanilla"
  para hidratación. Reduce superficie de ataque y simplifica el modelo mental.
- **Sesiones server-side** en Redis (Flask-Session) en lugar de JWT.
- **Rate limiting** con Flask-Limiter respaldado por Redis. Clave por usuario
  autenticado o por IP.
- **Logging estructurado** con `structlog` (JSON en producción, texto coloreado
  en desarrollo). Cada petición lleva `X-Request-ID` que se propaga también a
  las tareas Celery vía signals.
- **IA pluggable** por interfaz `LLMProvider`: implementaciones
  `OpenAIProvider` y `GeminiProvider` (reales, conectadas a las APIs de
  OpenAI y Google Gemini), más `FakeProvider` (determinista, sin red, para
  desarrollo y tests). El despliegue fija el proveedor por defecto con
  `AI_PROVIDER`, y **cada docente puede elegir el suyo** en el perfil. El
  catálogo de modelos ofrecidos sale del `.env` (`OPENAI_MODELOS` /
  `GEMINI_MODELOS`), no de una lista fija en el código: los nombres de modelo
  caducan y una lista incrustada caducaría en silencio.
- **Anclaje curricular obligatorio**: no se genera una SA cuyo par
  materia/curso no tenga currículo LOMLOE cargado. Sin criterios ni saberes a
  los que referirse, el modelo devolvería secciones vacías o códigos
  inventados. Los desplegables del formulario se restringen mutuamente contra
  la cobertura real (`GET /api/curriculo/cobertura`).
- **Tema claro, oscuro y automático**, resuelto en servidor para que no haya
  destello al navegar. Los contrastes de ambas paletas se verifican en tests.
- **Exportación**: PDF con WeasyPrint, DOCX con `python-docx`. Fuente fijada
  explícitamente (Calibri) en el OOXML para coherencia entre visualizadores.
- **Accesibilidad WCAG 2.1 AA**: paleta auditada (contraste AAA en texto
  principal), skip-link, foco visible, navegación por teclado, `prefers-
  reduced-motion`, marcado semántico con `aria-*`.

---

## Requisitos previos

- **Docker Desktop** (Windows/macOS) o **Docker Engine + Compose v2** (Linux).
- Clave de **OpenAI** (variable `OPENAI_API_KEY`) o de **Google Gemini**
  (variable `GEMINI_API_KEY`), según el proveedor seleccionado en
  `AI_PROVIDER`. Si solo quieres probar el flujo sin consumir tokens,
  fija `AI_PROVIDER=fake`.

---

## Puesta en marcha (primera vez)

1. **Configura variables de entorno**:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edita `.env` y rellena al menos:
   - `SECRET_KEY` (genera una con
     `python -c "import secrets; print(secrets.token_hex(32))"`).
   - `AI_PROVIDER` (`openai`, `gemini` o `fake`).
   - `OPENAI_API_KEY` (<https://platform.openai.com/api-keys>) si vas a
     usar OpenAI, o `GEMINI_API_KEY`
     (<https://aistudio.google.com/app/apikey>) si vas a usar Gemini.
   - `POSTGRES_PASSWORD` con algo razonable.

2. **Construye e inicia** los servicios (perfil `dev` añade Adminer):
   ```powershell
   docker compose build
   docker compose --profile dev up -d
   ```

3. **Aplica migraciones** y **carga semillas** del currículo LOMLOE:
   ```powershell
   docker compose exec api flask --app app db upgrade
   docker compose exec api flask --app app seed-roles
   docker compose exec api flask --app app seed-ods
   docker compose exec api flask --app app seed-curriculo
   ```

4. **Verifica el estado**:
   ```powershell
   curl http://localhost:8090/health
   ```
   Debe devolver:
   ```json
   {
     "app": "ok", "database": "ok", "redis": "ok",
     "ai_provider": "gemini", "model": "gemini-3.5-flash"
   }
   ```
   `ai_provider` informa del proveedor **realmente activo**, no del que se
   supone por configuración: así se ve si la aplicación ha caído al proveedor
   simulado por faltar una clave.

5. Abre la app en <http://localhost:8090>. Adminer queda en
   <http://localhost:8091> (sistema: PostgreSQL, servidor: `postgres`,
   credenciales del `.env`).

---

## Comandos habituales

```powershell
# Ver logs en vivo
docker compose logs -f api
docker compose logs -f worker

# Reiniciar un servicio tras cambios
docker compose restart api

# Shell dentro de un contenedor
docker compose exec api bash

# Ejecutar la suite de pruebas
docker compose exec api pytest -q

# ---- Cuentas de administración ----
# Ver si ya existe alguna (avisa de las que están dadas de baja)
docker compose exec api flask usuarios listar-admins

# Crear la primera. La contraseña se pide de forma interactiva y oculta:
# pasarla como argumento la dejaría en el historial de PowerShell.
docker compose exec -it api flask usuarios crear-admin

# Dar el rol a una cuenta que ya existe
docker compose exec api flask usuarios promover docente@ejemplo.com

# Tests de JavaScript (lógica de cobertura curricular). El contenedor api es
# python:3.12-slim y no lleva Node, así que se usa uno efímero.
docker run --rm -v "${PWD}/api:/app" -w /app node:22-alpine node tests/js/cobertura.test.js
docker run --rm -v "${PWD}/api:/app" -w /app node:22-alpine node tests/js/lectura.test.js
docker run --rm -v "${PWD}/api:/app" -w /app node:22-alpine node tests/js/llamadas.test.js
docker run --rm -v "${PWD}/api:/app" -w /app node:22-alpine node tests/js/traducibles.test.js

# O todo de una vez, que es lo que conviene antes de commitear:
.\verificar.ps1

# Recompilar los catálogos de traducción tras cambiar un .po
docker compose exec api pybabel compile -d app/translations

# Extraer cadenas nuevas y actualizar los catálogos.
# `--no-wrap` es la convención del proyecto: sin él, pybabel parte las cadenas
# largas en varias líneas y el diff de cambiar UNA traducción reescribe medio
# fichero.
docker compose exec api pybabel extract -F babel.cfg --no-wrap -o app/translations/messages.pot .
docker compose exec api pybabel update --no-wrap -i app/translations/messages.pot -d app/translations

# Tras `update`, revisar SIEMPRE las entradas marcadas `fuzzy`: son traducciones
# copiadas de otra cadena parecida, no traducciones. `pybabel compile` las salta,
# así que salen en castellano. Hay un test que falla si queda alguna.
docker compose exec api grep -c fuzzy app/translations/ca/LC_MESSAGES/messages.po

# Integración continua
# Cada push y cada pull request ejecutan la batería completa en GitHub Actions
# (.github/workflows/verificar.yml): pytest dentro de la imagen del proyecto,
# los cuatro tests de JavaScript, y el arnés de migración contra un Postgres
# real. Python corre en la imagen construida desde api/Dockerfile y no en un
# entorno montado a mano, para no mantener dos listas de dependencias del
# sistema que se desincronizarían.

# Probar la cola Celery
docker compose exec api python -c "from app.celery_worker import ping; print(ping.delay().get(timeout=5))"

# Crear una migración nueva tras modificar modelos
docker compose exec api flask --app app db migrate -m "descripcion del cambio"
docker compose exec api flask --app app db upgrade

# Parar todo
docker compose --profile dev down

# Parar y borrar volúmenes (¡destruye la BD!)
docker compose --profile dev down -v
```

---

## Estructura del proyecto

```
AWEBO/
├── docker-compose.yml
├── docker-compose.override.yml      # ajustes locales de desarrollo
├── .env.example
├── nginx/
│   └── nginx.conf
├── postgres/
│   └── init/                        # scripts de inicialización SQL
├── curriculo/
│   ├── fuentes/                     # los XML del BOE, para poder re-extraer
│   └── salida/                      # JSON LOMLOE precompilado (semillas)
└── api/
    ├── Dockerfile
    ├── requirements.txt
    ├── pytest.ini
    ├── migrations/                  # Alembic
    ├── tests/                       # unit + integration + js/
    └── app/
        ├── __init__.py              # factory create_app()
        ├── config.py                # Config / DevConfig / TestConfig
        ├── extensions.py            # db, login, session, redis, limiter
        ├── logging_config.py        # structlog + contextvars
        ├── middleware.py            # request-id, X-Request-ID
        ├── celery_app.py            # Celery + signals para request-id
        ├── celery_worker.py         # entrypoint del worker
        ├── errors.py                # handlers globales (JSON / HTML)
        ├── security.py              # hashing, helpers
        ├── cli.py                   # comandos flask (seeds, etc.)
        ├── ai/                      # LLMProvider + factory (openai/gemini/fake)
        ├── api/                     # blueprints REST (auth, me, situaciones…)
        ├── models/                  # SQLAlchemy: usuario, situacion, curriculo
        ├── schemas/                 # Pydantic (entrada/salida)
        ├── services/                # lógica de negocio (auth, situaciones, export)
        ├── tasks/                   # tareas Celery (generación IA)
        ├── prompts/                 # prompts por sección LOMLOE versionados
        ├── seeds/                   # carga inicial (roles, ODS, currículo)
        ├── curriculo/               # parser del catálogo LOMLOE
        ├── static/                  # css, js, imagenes, favicon
        └── templates/               # Jinja: páginas + exportación PDF
```

---

## Base heredada del TFG

Todo lo siguiente llegó completo desde el TFG y es el punto de partida:

- **Fase 0** — Andamiaje Docker, healthchecks, factory Flask
- **Fase 1** — Modelos SQLAlchemy + migraciones + seeds LOMLOE
- **Fase 2** — Auth con sesiones server-side y roles
- **Fase 3** — CRUD de situaciones de aprendizaje
- **Fase 4** — Generación con LLM vía Celery
- **Fase 5** — Adaptaciones curriculares (ACS / ACNS)
- **Fase 6** — Exportación PDF / DOCX
- **Fase 7** — Endurecimiento y observabilidad (rate limiting + logging)
- **Fase 8** — Frontend definitivo (paleta WCAG AA, páginas de soporte)

## Qué añade AWEBO sobre el TFG

Lo entregado hasta ahora como proyecto personal:

| Funcionalidad | Qué hace |
|---|---|
| **Sugerencia inicial de temática** | El docente describe en una frase lo que busca —o no describe nada— y recibe varias temáticas entre las que elegir. Resuelve la página en blanco: antes había que llegar con el tema ya pensado. |
| **Tema oscuro** | Claro, oscuro y automático, con selector en la cabecera. Se resuelve en servidor, así que no hay destello blanco al navegar. |
| **Proveedor y modelo por usuario** | Cada docente elige en su perfil qué modelo redacta sus situaciones. Sin elección, el del sistema. |
| **Operaciones por bloque** | Resumir, desarrollar y traducir cualquier sección de redacción libre, con deshacer. La conexión curricular queda excluida: es texto anclado al Real Decreto. |
| **Doble propuesta** | Pedir una segunda redacción de un bloque, ver las dos y quedarse con una. Cada elección se registra con la procedencia de ambas, para saber con el tiempo qué prompt redacta mejor. |
| **Anclaje curricular garantizado** | Ya no se pueden crear situaciones de materias y cursos sin currículo —«Matemáticas · 4º ESO» no existe—, que generaban secciones vacías en silencio. |

Y cinco defectos heredados del TFG corregidos por el camino: el logging
estructurado que nunca llegó a funcionar, `/health` informando del proveedor
equivocado, dos incumplimientos WCAG 2.1 en el tema claro y los reintentos
sobre errores `4xx` de la API de OpenAI.

---

## Hoja de ruta AWEBO

En resumen:

| #  | Tarea                                              | Esfuerzo |
|----|----------------------------------------------------|----------|
| ~~1~~ | ~~Sugerencia inicial de temática~~ ✅           | S        |
| ~~2~~ | ~~Tema oscuro~~ ✅                              | S–M      |
| ~~3~~ | ~~Proveedor y modelo elegibles por usuario~~ ✅ | M        |
| ~~4~~ | ~~Operaciones por bloque~~ ✅                   | M        |
| ~~5~~ | ~~Doble propuesta con elección del usuario~~ ✅ | M        |
| 🚧 6 | Internacionalización (i18n) — infraestructura lista | L        |
| 7  | Panel de administración                            | L        |
| 8  | Accesibilidad: texto a voz · audio/vídeo con IA    | S–M · XL |
| 9  | Ampliación: materias · etapas · comunidades        | S · M · XL |

Heredados del TFG como «mejora futura», sin prioridad asignada todavía:
backups automatizados de PostgreSQL, especificación OpenAPI y CI en GitHub
Actions.


---

## Seguridad y privacidad

- Las claves y contraseñas viven exclusivamente en `.env` (fuera del repo).
- `.env.example` se versiona con **placeholders**, nunca con valores reales.
- Las contraseñas de usuario se guardan con `bcrypt`.
- El contenido generado por IA queda asociado al usuario propietario; el
  acceso de **otro docente** devuelve `403`.
- **Los administradores sí acceden al contenido de cualquier situación** desde
  la aplicación normal. Se probó a cerrarlo y se descartó: quien administra
  dejaba de poder reproducir un problema que le reportan. Conviene decirlo
  aquí en lugar de prometer una privacidad que el código no sostiene.
- El **panel de administración** es otra cosa, y sigue mostrando solo
  metadatos: título, materia, curso, estado y fechas. No es una barrera —quien
  administra puede rodearla por la aplicación normal— sino una forma de que la
  gestión rutinaria (borrar una cuenta, revisar cuántas SA hay) no obligue a
  pasar por el contenido de nadie.
- Las cookies de sesión se emiten con `HttpOnly`, `Secure` (en producción)
  y `SameSite=Lax`.

---

## Accesibilidad

El proyecto apunta a **WCAG 2.1 nivel AA**. Detalles, limitaciones conocidas y
vía de contacto en la página `/accesibilidad` de la propia aplicación.

En curso como línea de mejora: tema oscuro (tarea 2) y lectura por voz
(tarea 8a).

---

## Licencia

Pendiente de definir antes de la publicación del repositorio.
