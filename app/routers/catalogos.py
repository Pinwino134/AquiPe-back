from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..enums import TipoPublicacion
from ..models import Zona
from ..schemas import CategoriaOut, ZonaOut

router = APIRouter(tags=["Catálogos"])


@router.get("/zonas", response_model=list[ZonaOut])
def listar_zonas(db: Session = Depends(get_db)):
    return db.scalars(select(Zona).order_by(Zona.nombre)).all()


@router.get("/categorias", response_model=list[CategoriaOut])
def listar_categorias(tipo: TipoPublicacion | None = None, db: Session = Depends(get_db)):
    """Categorías activas. Con ?tipo=SERVICIO devuelve solo las que aplican a ese tipo."""
    filas = db.execute(
        text(
            "SELECT id, nombre, icono, padre_id, aplica_a::text[] AS aplica_a "
            "FROM categoria WHERE activa ORDER BY id"
        )
    ).mappings().all()
    salida = [dict(f) for f in filas]
    if tipo is not None:
        salida = [c for c in salida if tipo.value in c["aplica_a"]]
    return salida
