"""
Validaciones de seguridad reutilizables.

Todo identificador SQL o ruta que provenga de configuración, datos o CLI debe
pasar por aquí antes de usarse (defensa contra SQL injection y path traversal).
"""
from __future__ import annotations

import re

from .exceptions import UnsafeInputError

# Identificadores PostgreSQL: minúsculas, dígitos y '_', sin empezar por dígito, máx 63.
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# Claves de objeto: caracteres seguros, sin '..' ni rutas absolutas.
_OBJECT_KEY_RE = re.compile(r"^[A-Za-z0-9_\-./]{1,1024}$")


def validate_identifier(name: str) -> str:
    if not isinstance(name, str) or not _IDENTIFIER_RE.fullmatch(name):
        raise UnsafeInputError(f"Identificador SQL no permitido: {name!r}")
    return name


def validate_object_key(key: str) -> str:
    if (
        not isinstance(key, str)
        or not _OBJECT_KEY_RE.fullmatch(key)
        or key.startswith("/")
        or ".." in key.split("/")
    ):
        raise UnsafeInputError(f"Clave/ruta no permitida: {key!r}")
    return key
