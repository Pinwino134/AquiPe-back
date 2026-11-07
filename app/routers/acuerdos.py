import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..enums import DireccionPublicacion, EstadoAcuerdo, EstadoPublicacion, EstadoRespuesta
from ..models import Acuerdo, Resena, Respuesta, Usuario
from ..schemas import AcuerdoEstadoIn, AcuerdoOut, ResenaCreate, ResenaOut

router = APIRouter(prefix="/acuerdos", tags=["Acuerdos y reseñas"])

TRANSICIONES = {
    EstadoAcuerdo.PROGRAMADO: {EstadoAcuerdo.EN_CURSO, EstadoAcuerdo.COMPLETADO, EstadoAcuerdo.CANCELADO},
    EstadoAcuerdo.EN_CURSO: {EstadoAcuerdo.COMPLETADO, EstadoAcuerdo.CANCELADO},
}


def _cargar_participante(db: Session, acuerdo_id: uuid.UUID, yo: Usuario) -> Acuerdo:
    a = db.get(Acuerdo, acuerdo_id)
    if a is None:
        raise HTTPException(404, "Acuerdo no encontrado")
    if yo.id not in (a.solicitante_id, a.proveedor_id):
        raise HTTPException(403, "No participas en este acuerdo")
    return a


@router.get("/mios", response_model=list[AcuerdoOut])
def mis_acuerdos(
    estado: EstadoAcuerdo | None = None,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acuerdos en los que participo, como solicitante o como proveedor."""
    consulta = select(Acuerdo).where(or_(Acuerdo.solicitante_id == yo.id, Acuerdo.proveedor_id == yo.id))
    if estado is not None:
        consulta = consulta.where(Acuerdo.estado == estado)
    consulta = consulta.order_by(Acuerdo.created_at.desc())
    return db.scalars(consulta).unique().all()


@router.get("/{acuerdo_id}", response_model=AcuerdoOut)
def ver_acuerdo(acuerdo_id: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return _cargar_participante(db, acuerdo_id, yo)


@router.patch("/{acuerdo_id}/estado", response_model=AcuerdoOut)
def cambiar_estado(
    acuerdo_id: uuid.UUID,
    datos: AcuerdoEstadoIn,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cualquiera de las dos partes puede avanzar el acuerdo:
    PROGRAMADO -> EN_CURSO -> COMPLETADO, o CANCELADO en cualquier momento antes de completarse.
    Cancelar un acuerdo de una solicitud la vuelve a dejar ABIERTA."""
    a = _cargar_participante(db, acuerdo_id, yo)
    if datos.estado not in TRANSICIONES.get(a.estado, set()):
        raise HTTPException(409, f"No se puede pasar de {a.estado.value} a {datos.estado.value}")

    p = a.publicacion
    solicita = p.direccion == DireccionPublicacion.SOLICITA
    ahora = datetime.now(timezone.utc)
    a.estado = datos.estado
    if datos.estado == EstadoAcuerdo.EN_CURSO and solicita:
        p.estado = EstadoPublicacion.EN_CURSO
    elif datos.estado == EstadoAcuerdo.COMPLETADO:
        a.completado_at = ahora
        if solicita:
            p.estado = EstadoPublicacion.COMPLETADA
    elif datos.estado == EstadoAcuerdo.CANCELADO:
        a.cancelado_at = ahora
        a.motivo_cancelacion = datos.motivo
        if solicita:
            p.estado = EstadoPublicacion.ABIERTA
            r = db.get(Respuesta, a.respuesta_id)
            r.estado = EstadoRespuesta.RETIRADA
    db.commit()
    return a


@router.post("/{acuerdo_id}/resenas", response_model=ResenaOut, status_code=201)
def crear_resena(
    acuerdo_id: uuid.UUID,
    datos: ResenaCreate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reseña a la otra parte. Solo con el acuerdo COMPLETADO y una vez por persona
    (lo valida la base de datos). La calificación promedio del usuario se actualiza sola."""
    a = _cargar_participante(db, acuerdo_id, yo)
    destinatario = a.proveedor_id if yo.id == a.solicitante_id else a.solicitante_id
    resena = Resena(
        acuerdo_id=a.id,
        autor_id=yo.id,
        destinatario_id=destinatario,
        calificacion=datos.calificacion,
        comentario=datos.comentario,
    )
    db.add(resena)
    db.commit()
    db.refresh(resena)
    return ResenaOut.model_validate(resena)
