import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Acuerdo, PerfilProveedor, Resena, Usuario, Zona
from ..schemas import (
    PerfilProveedorIn,
    PerfilProveedorOut,
    ResenaOut,
    UsuarioOut,
    UsuarioPublico,
    UsuarioUpdate,
)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/me", response_model=UsuarioOut)
def mi_perfil(yo: Usuario = Depends(get_current_user)):
    return yo


@router.patch("/me", response_model=UsuarioOut)
def actualizar_mi_perfil(
    datos: UsuarioUpdate, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)
):
    cambios = datos.model_dump(exclude_unset=True)
    if "zona_id" in cambios and cambios["zona_id"] is not None:
        if db.get(Zona, cambios["zona_id"]) is None:
            raise HTTPException(422, "zona_id no existe")
    if "telefono" in cambios and cambios["telefono"] is None:
        cambios.pop("telefono")
    if "nombre_completo" in cambios and cambios["nombre_completo"] is None:
        cambios.pop("nombre_completo")
    for campo, valor in cambios.items():
        setattr(yo, campo, valor)
    db.commit()
    db.refresh(yo)
    return yo


@router.put("/me/proveedor", response_model=PerfilProveedorOut)
def activar_perfil_proveedor(
    datos: PerfilProveedorIn,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea o actualiza el perfil de quien ofrece servicios (biografía, experiencia, horario)."""
    perfil = db.get(PerfilProveedor, yo.id)
    if perfil is None:
        perfil = PerfilProveedor(usuario_id=yo.id)
        db.add(perfil)
    for campo, valor in datos.model_dump().items():
        setattr(perfil, campo, valor)
    db.commit()
    db.refresh(perfil)
    return perfil


@router.get("/{usuario_id}", response_model=UsuarioPublico)
def ver_usuario(
    usuario_id: uuid.UUID,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado")
    salida = UsuarioPublico.model_validate(u)
    # El teléfono se muestra si el perfil es público o si hay un acuerdo entre ambos
    tienen_acuerdo = db.scalar(
        select(Acuerdo.id)
        .where(
            or_(
                (Acuerdo.solicitante_id == yo.id) & (Acuerdo.proveedor_id == u.id),
                (Acuerdo.solicitante_id == u.id) & (Acuerdo.proveedor_id == yo.id),
            )
        )
        .limit(1)
    )
    if u.id == yo.id or u.perfil_publico or tienen_acuerdo:
        salida.telefono = u.telefono
    return salida


@router.get("/{usuario_id}/resenas", response_model=list[ResenaOut])
def resenas_de_usuario(
    usuario_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    consulta = (
        select(Resena)
        .where(Resena.destinatario_id == usuario_id)
        .order_by(Resena.created_at.desc())
        .limit(min(limit, 100))
        .offset(offset)
    )
    return db.scalars(consulta).unique().all()
