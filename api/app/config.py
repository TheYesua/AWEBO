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
