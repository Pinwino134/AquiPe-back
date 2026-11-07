import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from .database import get_db
from .enums import EstadoUsuario
from .models import Usuario

_hasher = PasswordHasher()
_header = APIKeyHeader(
    name="X-User-Id",
    auto_error=False,
    description="UUID del usuario (lo devuelve /auth/login o /auth/registro)",
)


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def get_current_user(
    x_user_id: str | None = Depends(_header), db: Session = Depends(get_db)
) -> Usuario:
    if not x_user_id:
        raise HTTPException(401, "Falta el header X-User-Id. Inicia sesión primero.")
    try:
        uid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(401, "X-User-Id no es un UUID válido")
    usuario = db.get(Usuario, uid)
    if usuario is None:
        raise HTTPException(401, "Usuario no encontrado")
    if usuario.estado != EstadoUsuario.ACTIVO:
        raise HTTPException(403, "La cuenta no está activa")
    return usuario
