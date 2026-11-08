from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import (
    crear_access_token,
    hashear_password,
    registrar_intento_login,
    verificar_bloqueo_login,
    verificar_password,
)
from ..database import get_db
from ..enums import EstadoUsuario
from ..models import Usuario, Zona
from ..schemas import LoginIn, RegistroIn, UsuarioOut

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioOut, status_code=201)
def registro(datos: RegistroIn, db: Session = Depends(get_db)):
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.correo) == datos.correo.lower())):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    if db.scalar(select(Usuario.id).where(Usuario.telefono == datos.telefono)):
        raise HTTPException(409, "Ya existe una cuenta con ese teléfono")
    zona = None
    if datos.zona_id is not None:
        zona = db.get(Zona, datos.zona_id)
        if zona is None:
            raise HTTPException(422, "zona_id no existe")

    usuario = Usuario(
        nombre_completo=datos.nombre_completo.strip(),
        correo=datos.correo.lower(),
        telefono=datos.telefono,
        password_hash=hashear_password(datos.password),
        zona_id=datos.zona_id,
        # Ubicación inicial aproximada: el centro de su zona (luego puede ajustarla con el GPS)
        latitud=zona.latitud if zona else None,
        longitud=zona.longitud if zona else None,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    salida = UsuarioOut.model_validate(usuario)
    salida.access_token = crear_access_token(usuario.id)
    return salida


@router.post("/login", response_model=UsuarioOut)
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    """Valida correo y contraseña y devuelve el usuario con su `access_token` firmado."""
    ip = request.client.host if request.client else "local"
    clave_intento = f"{ip}:{datos.correo.lower()}"
    verificar_bloqueo_login(clave_intento)

    usuario = db.scalar(select(Usuario).where(func.lower(Usuario.correo) == datos.correo.lower()))
    if usuario is None or not verificar_password(datos.password, usuario.password_hash):
        registrar_intento_login(clave_intento, exitoso=False)
        raise HTTPException(401, "Correo o contraseña incorrectos")
    if usuario.estado != EstadoUsuario.ACTIVO:
        raise HTTPException(403, "La cuenta no está activa")

    registrar_intento_login(clave_intento, exitoso=True)
    salida = UsuarioOut.model_validate(usuario)
    salida.access_token = crear_access_token(usuario.id)
    return salida
