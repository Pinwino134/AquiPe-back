import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Numeric, cast, func, or_, select, text
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..enums import DireccionPublicacion, EstadoPublicacion, TipoPublicacion
from ..models import (
    Categoria,
    DetalleEmergencia,
    DetalleServicio,
    Publicacion,
    Usuario,
    Zona,
)
from ..schemas import PublicacionCreate, PublicacionOut, PublicacionUpdate

router = APIRouter(prefix="/publicaciones", tags=["Publicaciones"])

ESTADOS_EDITABLES = {
    EstadoPublicacion.ABIERTA,
    EstadoPublicacion.PAUSADA,
    EstadoPublicacion.CANCELADA,
}


def _a_salida(p: Publicacion, km: float | None = None) -> PublicacionOut:
    salida = PublicacionOut.model_validate(p)
    salida.distancia_km = round(float(km), 2) if km is not None else None
    return salida


def _cargar(db: Session, pub_id: uuid.UUID) -> Publicacion:
    p = db.scalar(select(Publicacion).where(Publicacion.id == pub_id, Publicacion.deleted_at.is_(None)))
    if p is None:
        raise HTTPException(404, "Publicación no encontrada")
    return p


@router.post("", response_model=PublicacionOut, status_code=201)
def crear_publicacion(
    datos: PublicacionCreate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea una publicación. Ejemplos de uso:

    - **Ofrecer un servicio**: `tipo=SERVICIO`, `direccion=OFRECE`, con `servicio` (precio, modalidad…).
    - **Solicitud de trabajo**: `tipo=SERVICIO`, `direccion=SOLICITA`, con `servicio` (presupuesto, fecha…).
    - **Favor**: `tipo=FAVOR`. **Emergencia**: `tipo=EMERGENCIA` (requiere latitud/longitud).

    Si no envías latitud/longitud se usa la ubicación del usuario y, si no tiene, el centro de la zona.
    """
    if datos.categoria_id is not None:
        fila = db.execute(
            text("SELECT aplica_a::text[] AS aplica_a FROM categoria WHERE id = :i AND activa"),
            {"i": datos.categoria_id},
        ).first()
        if fila is None:
            raise HTTPException(422, "categoria_id no existe")
        if datos.tipo.value not in fila.aplica_a:
            raise HTTPException(422, f"Esa categoría no aplica a publicaciones de tipo {datos.tipo.value}")

    zona_id = datos.zona_id if datos.zona_id is not None else yo.zona_id
    zona = db.get(Zona, zona_id) if zona_id is not None else None
    if datos.zona_id is not None and zona is None:
        raise HTTPException(422, "zona_id no existe")

    lat, lng = datos.latitud, datos.longitud
    if lat is None:
        if yo.latitud is not None:
            lat, lng = yo.latitud, yo.longitud
        elif zona is not None:
            lat, lng = zona.latitud, zona.longitud

    p = Publicacion(
        autor_id=yo.id,
        tipo=datos.tipo,
        direccion=datos.direccion,
        categoria_id=datos.categoria_id,
        titulo=datos.titulo.strip(),
        descripcion=datos.descripcion.strip(),
        zona_id=zona_id,
        latitud=lat,
        longitud=lng,
        expira_at=datos.expira_at,
    )
    if datos.servicio is not None:
        p.servicio = DetalleServicio(**datos.servicio.model_dump())
    if datos.emergencia is not None:
        p.emergencia = DetalleEmergencia(**datos.emergencia.model_dump())
    db.add(p)
    db.commit()
    return _a_salida(_recargar(db, p.id))


def _recargar(db: Session, pub_id: uuid.UUID) -> Publicacion:
    db.expire_all()
    return _cargar(db, pub_id)


@router.get("", response_model=list[PublicacionOut])
def listar_publicaciones(
    tipo: TipoPublicacion | None = None,
    direccion: DireccionPublicacion | None = None,
    categoria_id: int | None = None,
    zona_id: int | None = None,
    estado: EstadoPublicacion | None = EstadoPublicacion.ABIERTA,
    q: str | None = Query(None, description="Busca en título y descripción"),
    autor_id: uuid.UUID | None = None,
    lat: float | None = Query(None, ge=-90, le=90, description="Tu latitud (para ordenar por cercanía)"),
    lng: float | None = Query(None, ge=-180, le=180),
    radio_km: float | None = Query(None, gt=0, le=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Feed y mapa. Con `lat`+`lng` ordena por cercanía y devuelve `distancia_km`;
    con `radio_km` además filtra por distancia."""
    if (lat is None) != (lng is None):
        raise HTTPException(422, "lat y lng se envían juntas")
    if radio_km is not None and lat is None:
        raise HTTPException(422, "radio_km requiere lat y lng")

    columnas = [Publicacion]
    km = None
    if lat is not None:
        km = func.distancia_km(
            cast(lat, Numeric), cast(lng, Numeric), Publicacion.latitud, Publicacion.longitud
        ).label("km")
        columnas.append(km)

    consulta = select(*columnas).where(Publicacion.deleted_at.is_(None))
    if estado is not None:
        consulta = consulta.where(Publicacion.estado == estado)
    if tipo is not None:
        consulta = consulta.where(Publicacion.tipo == tipo)
    if direccion is not None:
        consulta = consulta.where(Publicacion.direccion == direccion)
    if categoria_id is not None:
        consulta = consulta.where(Publicacion.categoria_id == categoria_id)
    if zona_id is not None:
        consulta = consulta.where(Publicacion.zona_id == zona_id)
    if autor_id is not None:
        consulta = consulta.where(Publicacion.autor_id == autor_id)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(
            or_(Publicacion.titulo.ilike(patron), Publicacion.descripcion.ilike(patron))
        )
    if radio_km is not None:
        # Caja envolvente (aprovecha el índice) + distancia exacta
        d_lat = radio_km / 111.0
        d_lng = radio_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        consulta = consulta.where(
            Publicacion.latitud.between(lat - d_lat, lat + d_lat),
            Publicacion.longitud.between(lng - d_lng, lng + d_lng),
            km <= radio_km,
        )

    if km is not None:
        consulta = consulta.order_by(km.asc().nulls_last(), Publicacion.created_at.desc())
    else:
        consulta = consulta.order_by(Publicacion.created_at.desc())
    consulta = consulta.limit(limit).offset(offset)

    filas = db.execute(consulta).unique().all()
    if km is not None:
        return [_a_salida(p, k) for p, k in filas]
    return [_a_salida(p) for (p,) in filas]


@router.get("/mias", response_model=list[PublicacionOut])
def mis_publicaciones(
    estado: EstadoPublicacion | None = None,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Todas mis publicaciones (cualquier estado)."""
    consulta = select(Publicacion).where(
        Publicacion.autor_id == yo.id, Publicacion.deleted_at.is_(None)
    )
    if estado is not None:
        consulta = consulta.where(Publicacion.estado == estado)
    consulta = consulta.order_by(Publicacion.created_at.desc())
    return [_a_salida(p) for p in db.scalars(consulta).unique().all()]


@router.get("/{pub_id}", response_model=PublicacionOut)
def ver_publicacion(
    pub_id: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _a_salida(_cargar(db, pub_id))


@router.patch("/{pub_id}", response_model=PublicacionOut)
def editar_publicacion(
    pub_id: uuid.UUID,
    datos: PublicacionUpdate,
    yo: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edita título, descripción o pausa/reabre/cancela la publicación (solo el autor)."""
    p = _cargar(db, pub_id)
    if p.autor_id != yo.id:
        raise HTTPException(403, "Solo el autor puede editar la publicación")
    cambios = datos.model_dump(exclude_unset=True)
    nuevo_estado = cambios.pop("estado", None)
    if nuevo_estado is not None:
        if nuevo_estado not in ESTADOS_EDITABLES:
            raise HTTPException(422, "Solo puedes cambiar el estado a ABIERTA, PAUSADA o CANCELADA")
        if p.estado not in ESTADOS_EDITABLES:
            raise HTTPException(409, f"No se puede cambiar el estado desde {p.estado.value}")
        p.estado = nuevo_estado
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(p, campo, valor.strip())
    db.commit()
    return _a_salida(_recargar(db, p.id))


@router.delete("/{pub_id}", status_code=204)
def eliminar_publicacion(
    pub_id: uuid.UUID, yo: Usuario = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Borrado lógico (solo el autor)."""
    p = _cargar(db, pub_id)
    if p.autor_id != yo.id:
        raise HTTPException(403, "Solo el autor puede eliminar la publicación")
    p.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)
