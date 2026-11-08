import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Recurso, Usuario
from ..schemas import RecursoCreate, RecursoOut, RecursoUpdate

router = APIRouter(prefix="/recursos", tags=["Recursos personales"])


@router.get("/mios", response_model=list[RecursoOut])
def mis_recursos(
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    consulta = (
        select(Recurso)
        .where(Recurso.usuario_id == yo.id)
        .order_by(Recurso.created_at.desc())
    )
    return db.scalars(consulta).unique().all()


@router.post("", response_model=RecursoOut, status_code=201)
def crear_recurso(
    datos: RecursoCreate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recurso = Recurso(
        usuario_id=yo.id,
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion.strip() if datos.descripcion else None,
        cantidad=datos.cantidad,
        unidad=datos.unidad.strip() if datos.unidad else "unidad",
        disponible=datos.disponible,
    )
    db.add(recurso)
    db.commit()
    db.refresh(recurso)
    return recurso


@router.patch("/{recurso_id}", response_model=RecursoOut)
def actualizar_recurso(
    recurso_id: uuid.UUID,
    datos: RecursoUpdate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(Recurso, recurso_id)
    if r is None:
        raise HTTPException(404, "Recurso no encontrado")
    if r.usuario_id != yo.id:
        raise HTTPException(403, "Solo el propietario puede modificar este recurso")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(r, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{recurso_id}", status_code=204)
def eliminar_recurso(
    recurso_id: uuid.UUID,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(Recurso, recurso_id)
    if r is None:
        raise HTTPException(404, "Recurso no encontrado")
    if r.usuario_id != yo.id:
        raise HTTPException(403, "Solo el propietario puede eliminar este recurso")
    db.delete(r)
    db.commit()
    return Response(status_code=204)
