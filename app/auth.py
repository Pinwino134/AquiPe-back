import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .enums import EstadoUsuario
from .models import Usuario

_hasher = PasswordHasher()
_SECRET_KEY = os.getenv("SECRET_KEY", "aquipe-hackaton-2026-secret-key-segura").encode("utf-8")
_TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))

_header_user_id = APIKeyHeader(
    name="X-User-Id",
    auto_error=False,
    description="UUID del usuario (compatibilidad con Swagger / desarrollo)",
)
_bearer = HTTPBearer(
    auto_error=False,
    description="Token firmado devuelto por /auth/login o /auth/registro",
)

# Protección contra fuerza bruta en memoria (máx 8 intentos fallidos en 5 minutos)
_intentos_fallidos: dict[str, list[float]] = defaultdict(list)
_MAX_INTENTOS = 8
_VENTANA_SEGUNDOS = 300


def registrar_intento_login(clave: str, exitoso: bool) -> None:
    ahora = time.time()
    if exitoso:
        _intentos_fallidos.pop(clave, None)
        return
    recientes = [t for t in _intentos_fallidos[clave] if ahora - t < _VENTANA_SEGUNDOS]
    recientes.append(ahora)
    _intentos_fallidos[clave] = recientes


def verificar_bloqueo_login(clave: str) -> None:
    ahora = time.time()
    recientes = [t for t in _intentos_fallidos.get(clave, []) if ahora - t < _VENTANA_SEGUNDOS]
    if len(recientes) >= _MAX_INTENTOS:
        raise HTTPException(
            429,
            "Demasiados intentos fallidos de inicio de sesión. Espera unos minutos antes de reintentar.",
        )


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(texto: str) -> bytes:
    padding = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + padding)


def crear_access_token(usuario_id: uuid.UUID) -> str:
    """Genera un token estilo JWT firmado con HMAC-SHA256 sin dependencias externas."""
    header = _b64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    ahora = int(time.time())
    payload_bytes = json.dumps(
        {"sub": str(usuario_id), "iat": ahora, "exp": ahora + _TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    payload = _b64url_encode(payload_bytes)
    mensaje = f"{header}.{payload}".encode("ascii")
    firma = _b64url_encode(hmac.new(_SECRET_KEY, mensaje, hashlib.sha256).digest())
    return f"{header}.{payload}.{firma}"


def verificar_access_token(token: str) -> uuid.UUID:
    partes = token.split(".")
    if len(partes) != 3:
        raise HTTPException(401, "Token de sesión inválido")
    header, payload, firma_recibida = partes
    mensaje = f"{header}.{payload}".encode("ascii")
    firma_esperada = _b64url_encode(hmac.new(_SECRET_KEY, mensaje, hashlib.sha256).digest())
    if not hmac.compare_digest(firma_recibida, firma_esperada):
        raise HTTPException(401, "Firma de token inválida")
    try:
        datos = json.loads(_b64url_decode(payload).decode("utf-8"))
        exp = int(datos.get("exp", 0))
        if exp < int(time.time()):
            raise HTTPException(401, "La sesión ha expirado. Inicia sesión nuevamente.")
        return uuid.UUID(str(datos["sub"]))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Contenido de token inválido")


def get_current_user(
    credenciales: HTTPAuthorizationCredentials | None = Security(_bearer),
    x_user_id: str | None = Depends(_header_user_id),
    db: Session = Depends(get_db),
) -> Usuario:
    uid: uuid.UUID | None = None

    if credenciales and credenciales.credentials:
        uid = verificar_access_token(credenciales.credentials)
    elif x_user_id:
        try:
            uid = uuid.UUID(x_user_id)
        except ValueError:
            raise HTTPException(401, "X-User-Id no es un UUID válido")
    else:
        raise HTTPException(401, "Autenticación requerida (Bearer token o X-User-Id).")

    usuario = db.get(Usuario, uid)
    if usuario is None:
        raise HTTPException(401, "Usuario no encontrado")
    if usuario.estado != EstadoUsuario.ACTIVO:
        raise HTTPException(403, "La cuenta no está activa")
    return usuario

