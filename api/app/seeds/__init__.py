"""Datos iniciales (seeds) para la base de datos.

Cada función ``seed_xxx`` es idempotente: vuelve a ejecutarse sin duplicar
registros. Se exponen como subcomandos del CLI ``flask seed``.
"""
from .seed_roles import seed_roles
from .seed_ods import seed_ods
from .seed_curriculo import seed_curriculo

__all__ = ["seed_roles", "seed_ods", "seed_curriculo"]
