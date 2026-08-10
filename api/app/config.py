"""Configuración de la aplicación cargada desde variables de entorno."""
from __future__ import annotations

import os
from datetime import timedelta


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Config:
    """Configuración base. Todos los valores provienen del entorno."""

    # --- Flask ---
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-key-change-me")
    FLASK_ENV: str = os.environ.get("FLASK_ENV", "production")
    DEBUG: bool = _bool(os.environ.get("FLASK_DEBUG"), default=FLASK_ENV == "development")

    # --- Base de datos ---
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://awebo_user:awebo_password@postgres:5432/awebo"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    # --- Redis y sesiones server-side ---
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    SESSION_REDIS_URL: str = os.environ.get("SESSION_REDIS_URL", "redis://redis:6379/3")
    SESSION_TYPE: str = "redis"
    SESSION_PERMANENT: bool = True
    SESSION_USE_SIGNER: bool = True
    SESSION_KEY_PREFIX: str = "awebo:sess:"
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(hours=8)

    # Cookie de sesión: HttpOnly + SameSite=Lax. Secure en producción (HTTPS).
    SESSION_COOKIE_NAME: str = "awebo_session"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = FLASK_ENV != "development"

    # --- Celery ---
    CELERY_BROKER_URL: str = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
    CELERY_RESULT_BACKEND: str = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

    # --- Rate limiting (Flask-Limiter) ---
    # Activado por defecto en producción; desactivado en tests vía
    # ``TestConfig.RATELIMIT_ENABLED = False``.
    RATELIMIT_ENABLED: bool = _bool(os.environ.get("RATELIMIT_ENABLED"), default=True)
    RATELIMIT_STORAGE_URI: str = os.environ.get(
        "RATELIMIT_STORAGE_URI", "redis://redis:6379/4"
    )
    RATELIMIT_STRATEGY: str = "fixed-window"
    RATELIMIT_HEADERS_ENABLED: bool = True
    # Límite global por defecto (por IP). Endpoints sensibles tienen
    # @limiter.limit("...") propio (auth/login, generación IA, export).
    RATELIMIT_DEFAULT: str = os.environ.get("RATELIMIT_DEFAULT", "300 per minute")

    # --- CORS ---
    # En producción: lista de orígenes permitidos separada por comas.
    # En desarrollo: por defecto se permite localhost en cualquier puerto.
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
    ] or (
        ["http://localhost:8080", "http://127.0.0.1:8080"]
        if FLASK_ENV == "development"
        else []
    )

    # --- Logging ---
    # ``LOG_JSON=None`` ⇒ structlog elige automáticamente (JSON en
    # producción, consola legible en desarrollo).
    LOG_JSON: bool | None = (
        _bool(os.environ.get("LOG_JSON")) if os.environ.get("LOG_JSON") is not None else None
    )
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # -----------------------------------------------------------------
    # Correo electrónico
    # -----------------------------------------------------------------
    # Por defecto NO se envía: el proveedor de consola escribe el mensaje en
    # el registro. Ver app/correo/consola.py para el motivo.
    CORREO_PROVEEDOR: str = os.environ.get("CORREO_PROVEEDOR", "consola")
    CORREO_REMITENTE: str = os.environ.get("CORREO_REMITENTE", "")

    SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
    # `or` y no el segundo argumento de get(): una variable declarada y vacía
    # —`SMTP_PORT=` en el .env, que es como se deja lo que no se usa— sí está
    # en el entorno, así que get() devolvería la cadena vacía e int("") tumba
    # el arranque con un ValueError que no menciona el .env por ningún lado.
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT") or 587)
    SMTP_USER: str = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")
    SMTP_TIMEOUT: int = int(os.environ.get("SMTP_TIMEOUT") or 15)

    #: Renuncia explícita al cifrado. Existe por el buzón de pruebas local:
    #: Mailpit no ofrece STARTTLS salvo que se le den certificados, así que
    #: contra él el envío falla siempre.
    #:
    #: Es una variable aparte y no una detección automática a propósito. Lo
    #: cómodo sería intentar STARTTLS y seguir en claro si el servidor no lo
    #: ofrece, pero entonces un proveedor real mal configurado —o alguien en
    #: medio que borra la oferta de STARTTLS— degradaría el envío a texto
    #: plano sin que nadie se enterase. Con una variable, ir sin cifrar es
    #: siempre una decisión escrita.
    SMTP_SIN_TLS: bool = os.environ.get("SMTP_SIN_TLS", "").lower() in {
        "1", "true", "si", "sí", "yes"
    }

    # Base para los enlaces que viajan por correo. Tiene que ser absoluta:
    # un enlace relativo en un cliente de correo no lleva a ningún sitio.
    URL_BASE: str = os.environ.get("URL_BASE", "http://localhost:8090")

    # -----------------------------------------------------------------
    # Síntesis de voz (tarea 8b)
    # -----------------------------------------------------------------
    # Por defecto NO genera: la síntesis se factura por caracteres y un
    # entorno con una clave heredada no debe poder gastar sin querer. Ver
    # app/voz/nulo.py.
    VOZ_PROVEEDOR: str = os.environ.get("VOZ_PROVEEDOR", "nulo")
    VOZ_TIMEOUT: int = int(os.environ.get("VOZ_TIMEOUT") or 60)

    #: Raíz del repositorio de aHoTTS: dentro van el binario `ahotts/tts`, los
    #: diccionarios lingüísticos y las voces. No está en el repositorio —son
    #: 250 MB de terceros—, se monta como volumen. Ver docs/VOCES.md.
    VOZ_AHOTTS_DIR: str = os.environ.get("VOZ_AHOTTS_DIR", "/ahotts")

    #: Dónde se guardan los audios generados. Fuera de la base de datos: un
    #: audio de una SdA entera ronda el medio mega y meterlos en Postgres haría
    #: que cada volcado de respaldo pasara de kilobytes a cientos de megas, con
    #: lo que la restauración verificada dejaría de lanzarse por lenta. Ver
    #: app/services/audio.py.
    VOZ_AUDIO_DIR: str = os.environ.get("VOZ_AUDIO_DIR", "/audio")

    #: Solo los usa el proveedor de nube, que se conserva como alternativa.
    VOZ_MODELO: str = os.environ.get("VOZ_MODELO", "tts-1")
    VOZ_VOZ: str = os.environ.get("VOZ_VOZ", "alloy")

    # --- IA / LLM ---
    # "openai" (por defecto si hay API key), "fake" (sin red, para tests
    # y desarrollo local sin API key).
    AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "")
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "")
    OPENAI_TIMEOUT: int = int(os.environ.get("OPENAI_TIMEOUT", "120"))

    # --- Gemini ---
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    # Modelos adicionales ofrecidos al usuario en su perfil, separados por
    # comas. El catálogo (``app.ai.catalogo``) los lee de aquí en lugar de
    # llevar una lista fija en el código: los nombres de modelo cambian con el
    # tiempo y una lista incrustada quedaría obsoleta en silencio, dejando al
    # usuario elegir algo que ya no existe.
    OPENAI_MODELOS: str = os.environ.get("OPENAI_MODELOS", "")
    GEMINI_MODELOS: str = os.environ.get("GEMINI_MODELOS", "")
