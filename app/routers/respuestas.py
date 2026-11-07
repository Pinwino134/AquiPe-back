import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..enums import DireccionPublicacion, EstadoPublicacion, EstadoRespuesta
from ..models import Acuerdo, Publicacion, Respuesta, Usuario
from ..schemas import (
    AceptarIn,
    AcuerdoOut,
    RespuestaCreate,
    RespuestaMiaOut,
    RespuestaOut,
)

router = APIRouter(tags=["Respuestas"])


def _respuesta(db: Session, rid: uuid.UUID) -> Respuesta:
    r = db.get(Respuesta, rid)
    if r is None:
        raise HTTPException(404, "Respuesta no encontrada")
    return r


@router.post(
    "/publicaciones/{pub_id}/respuestas", response_model=RespuestaOut, status_code=201
)
def responder(
    pub_id: uuid.UUID,
    datos: RespuestaCreate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Responder a una publicación: postularse a una solicitud de trabajo, contratar un
    servicio ofrecido, ofrecer ayuda en un favor o pedir contacto.
    Las reglas (no responder a lo propio, publicación abierta, una respuesta por usuario)
    las valida la base de datos y se devuelven como 409."""
    p = db.scalar(select(Publicacion).where(Publicacion.id == pub_id, Publicacion.deleted_at.is_(None)))
    if p is None:
        raise HTTPException(404, "Publicación no encontrada")
    r = Respuesta(
        publicacion_id=pub_id,
        usuario_id=yo.id,
        mensaje=datos.mensaje.strip(),
        precio_propuesto=datos.precio_propuesto,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return RespuestaOut.model_validate(r)


@router.get("/publicaciones/{pub_id}/respuestas", response_model=list[RespuestaOut])
def respuestas_de_publicacion(
    pub_id: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Las respuestas que recibió una publicación (solo las ve su autor)."""
    p = db.scalar(select(Publicacion).where(Publicacion.id == pub_id, Publicacion.deleted_at.is_(None)))
    if p is None:
        raise HTTPException(404, "Publicación no encontrada")
    if p.autor_id != yo.id:
        raise HTTPException(403, "Solo el autor ve las respuestas de su publicación")
    consulta = (
        select(Respuesta).where(Respuesta.publicacion_id == pub_id).order_by(Respuesta.created_at)
    )
    return db.scalars(consulta).unique().all()


@router.get("/respuestas/mias", response_model=list[RespuestaMiaOut])
def mis_respuestas(
    estado: EstadoRespuesta | None = None,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Las postulaciones / respuestas que yo envié."""
    consulta = select(Respuesta).where(Respuesta.usuario_id == yo.id)
    if estado is not None:
        consulta = consulta.where(Respuesta.estado == estado)
    consulta = consulta.order_by(Respuesta.created_at.desc())
    return db.scalars(consulta).unique().all()


@router.post("/respuestas/{rid}/retirar", response_model=RespuestaOut)
def retirar(rid: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _respuesta(db, rid)
    if r.usuario_id != yo.id:
        raise HTTPException(403, "Solo quien respondió puede retirar su respuesta")
    if r.estado != EstadoRespuesta.ENVIADA:
        raise HTTPException(409, f"No se puede retirar una respuesta {r.estado.value}")
    r.estado = EstadoRespuesta.RETIRADA
    db.commit()
    return RespuestaOut.model_validate(r)


@router.post("/respuestas/{rid}/rechazar", response_model=RespuestaOut)
def rechazar(rid: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _respuesta(db, rid)
    if r.publicacion.autor_id != yo.id:
        raise HTTPException(403, "Solo el autor de la publicación puede rechazar")
    if r.estado != EstadoRespuesta.ENVIADA:
        raise HTTPException(409, f"No se puede rechazar una respuesta {r.estado.value}")
    r.estado = EstadoRespuesta.RECHAZADA
    db.commit()
    return RespuestaOut.model_validate(r)


@router.post("/respuestas/{rid}/aceptar", response_model=AcuerdoOut, status_code=201)
def aceptar(
    rid: uuid.UUID,
    datos: AceptarIn | None = Body(None),
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """El autor acepta una respuesta y se crea el acuerdo.

    - Si la publicación SOLICITA (trabajo/favor): quien publicó es el solicitante, quien respondió es
      el proveedor; la publicación pasa a ASIGNADA y las demás respuestas se rechazan.
    - Si la publicación OFRECE: quien publicó es el proveedor y quien respondió el solicitante;
      la publicación sigue ABIERTA para atender a más personas.
    """
    r = _respuesta(db, rid)
    # Bloquea la publicación para que dos aceptaciones simultáneas no choquen
    p = db.scalar(
        select(Publicacion)
        .where(Publicacion.id == r.publicacion_id)
        .with_for_update(of=Publicacion)
        .execution_options(populate_existing=True)
    )
    if p.autor_id != yo.id:
        raise HTTPException(403, "Solo el autor de la publicación puede aceptar respuestas")
    if p.estado != EstadoPublicacion.ABIERTA:
        raise HTTPException(409, f"La publicación está {p.estado.value}, no admite más acuerdos")
    if r.estado != EstadoRespuesta.ENVIADA:
        raise HTTPException(409, f"La respuesta ya está {r.estado.value}")

    r.estado = EstadoRespuesta.ACEPTADA
    db.flush()  # el trigger valida que no haya otra respuesta aceptada en una solicitud

    solicita = p.direccion == DireccionPublicacion.SOLICITA
    precio = r.precio_propuesto
    if precio is None and not solicita and p.servicio is not None:
        precio = p.servicio.monto
    acuerdo = Acuerdo(
        publicacion_id=p.id,
        respuesta_id=r.id,
        solicitante_id=p.autor_id if solicita else r.usuario_id,
        proveedor_id=r.usuario_id if solicita else p.autor_id,
        precio_acordado=precio,
        fecha_programada=datos.fecha_programada if datos else None,
    )
    db.add(acuerdo)
    if solicita:
        p.estado = EstadoPublicacion.ASIGNADA
        db.execute(
            update(Respuesta)
            .where(
                Respuesta.publicacion_id == p.id,
                Respuesta.estado == EstadoRespuesta.ENVIADA,
                Respuesta.id != r.id,
            )
            .values(estado=EstadoRespuesta.RECHAZADA),
            execution_options={"synchronize_session": False},
        )
    db.commit()
    db.refresh(acuerdo)
    return AcuerdoOut.model_validate(acuerdo)
