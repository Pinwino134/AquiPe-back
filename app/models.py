import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import (
    DireccionPublicacion,
    EstadoAcuerdo,
    EstadoPublicacion,
    EstadoRespuesta,
    EstadoUsuario,
    ModalidadServicio,
    NivelUrgencia,
    TipoPrecio,
    TipoPublicacion,
)


def pg_enum(cls, nombre: str) -> SAEnum:
    """ENUM nativo de PostgreSQL que ya existe en la base (no se crea desde Python)."""
    return SAEnum(cls, name=nombre, create_type=False)


def num(precision: int, escala: int) -> Numeric:
    """NUMERIC que se lee como float (más cómodo para el frontend que Decimal)."""
    return Numeric(precision, escala, asdecimal=False)


def pk_uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def ts_creado() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Zona(Base):
    __tablename__ = "zona"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    distrito: Mapped[str] = mapped_column(String(100))
    ciudad: Mapped[str] = mapped_column(String(100))
    latitud: Mapped[float] = mapped_column(num(9, 6))
    longitud: Mapped[float] = mapped_column(num(9, 6))


class Categoria(Base):
    # La columna aplica_a (enum[]) no se mapea: el catálogo la lee con SQL directo.
    __tablename__ = "categoria"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    icono: Mapped[str | None] = mapped_column(String(50))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"))


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[uuid.UUID] = pk_uuid()
    nombre_completo: Mapped[str] = mapped_column(String(120))
    correo: Mapped[str] = mapped_column(String(160))
    telefono: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    foto_url: Mapped[str | None] = mapped_column(Text)
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zona.id"))
    latitud: Mapped[float | None] = mapped_column(num(9, 6))
    longitud: Mapped[float | None] = mapped_column(num(9, 6))
    perfil_publico: Mapped[bool] = mapped_column(Boolean, default=True)
    notificaciones_activas: Mapped[bool] = mapped_column(Boolean, default=True)
    estado: Mapped[EstadoUsuario] = mapped_column(
        pg_enum(EstadoUsuario, "estado_usuario"), default=EstadoUsuario.ACTIVO
    )
    calificacion_promedio: Mapped[float] = mapped_column(num(3, 2), server_default="0")
    total_resenas: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = ts_creado()

    zona: Mapped[Zona | None] = relationship(lazy="joined")
    perfil_proveedor: Mapped["PerfilProveedor | None"] = relationship(
        lazy="joined", uselist=False
    )


class PerfilProveedor(Base):
    __tablename__ = "perfil_proveedor"
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), primary_key=True
    )
    biografia: Mapped[str | None] = mapped_column(String(500))
    anios_experiencia: Mapped[int | None] = mapped_column(SmallInteger)
    disponibilidad: Mapped[str | None] = mapped_column(String(200))
    verificado: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Publicacion(Base):
    __tablename__ = "publicacion"
    id: Mapped[uuid.UUID] = pk_uuid()
    autor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    tipo: Mapped[TipoPublicacion] = mapped_column(pg_enum(TipoPublicacion, "tipo_publicacion"))
    direccion: Mapped[DireccionPublicacion] = mapped_column(
        pg_enum(DireccionPublicacion, "direccion_publicacion")
    )
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"))
    titulo: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str] = mapped_column(String(1000))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zona.id"))
    latitud: Mapped[float | None] = mapped_column(num(9, 6))
    longitud: Mapped[float | None] = mapped_column(num(9, 6))
    estado: Mapped[EstadoPublicacion] = mapped_column(
        pg_enum(EstadoPublicacion, "estado_publicacion"), default=EstadoPublicacion.ABIERTA
    )
    expira_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_creado()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    autor: Mapped[Usuario] = relationship(lazy="joined")
    categoria: Mapped[Categoria | None] = relationship(lazy="joined")
    zona: Mapped[Zona | None] = relationship(lazy="joined")
    servicio: Mapped["DetalleServicio | None"] = relationship(
        lazy="joined", uselist=False, cascade="all, delete-orphan"
    )
    emergencia: Mapped["DetalleEmergencia | None"] = relationship(
        lazy="joined", uselist=False, cascade="all, delete-orphan"
    )


class DetalleServicio(Base):
    __tablename__ = "detalle_servicio"
    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id"), primary_key=True
    )
    tipo: Mapped[TipoPublicacion] = mapped_column(
        pg_enum(TipoPublicacion, "tipo_publicacion"), default=TipoPublicacion.SERVICIO
    )
    tipo_precio: Mapped[TipoPrecio] = mapped_column(pg_enum(TipoPrecio, "tipo_precio"))
    monto: Mapped[float | None] = mapped_column(num(10, 2))
    moneda: Mapped[str] = mapped_column(String(3), default="PEN")
    modalidad: Mapped[ModalidadServicio] = mapped_column(
        pg_enum(ModalidadServicio, "modalidad_servicio")
    )
    radio_km: Mapped[float | None] = mapped_column(num(5, 2))
    disponibilidad: Mapped[str | None] = mapped_column(String(200))
    presupuesto_min: Mapped[float | None] = mapped_column(num(10, 2))
    presupuesto_max: Mapped[float | None] = mapped_column(num(10, 2))
    fecha_requerida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    urgencia: Mapped[NivelUrgencia] = mapped_column(pg_enum(NivelUrgencia, "nivel_urgencia"))


class DetalleEmergencia(Base):
    __tablename__ = "detalle_emergencia"
    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id"), primary_key=True
    )
    tipo: Mapped[TipoPublicacion] = mapped_column(
        pg_enum(TipoPublicacion, "tipo_publicacion"), default=TipoPublicacion.EMERGENCIA
    )
    cantidad: Mapped[int | None] = mapped_column(Integer)
    unidad: Mapped[str | None] = mapped_column(String(30))
    detalle_cantidad: Mapped[str | None] = mapped_column(String(200))
    nivel_urgencia: Mapped[NivelUrgencia] = mapped_column(
        pg_enum(NivelUrgencia, "nivel_urgencia")
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Respuesta(Base):
    __tablename__ = "respuesta"
    id: Mapped[uuid.UUID] = pk_uuid()
    publicacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publicacion.id"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    mensaje: Mapped[str] = mapped_column(String(500))
    precio_propuesto: Mapped[float | None] = mapped_column(num(10, 2))
    estado: Mapped[EstadoRespuesta] = mapped_column(
        pg_enum(EstadoRespuesta, "estado_respuesta"), default=EstadoRespuesta.ENVIADA
    )
    created_at: Mapped[datetime] = ts_creado()

    usuario: Mapped[Usuario] = relationship(lazy="joined")
    publicacion: Mapped[Publicacion] = relationship(lazy="joined")


class Acuerdo(Base):
    __tablename__ = "acuerdo"
    id: Mapped[uuid.UUID] = pk_uuid()
    publicacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publicacion.id"))
    respuesta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("respuesta.id"))
    solicitante_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    proveedor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    precio_acordado: Mapped[float | None] = mapped_column(num(10, 2))
    estado: Mapped[EstadoAcuerdo] = mapped_column(
        pg_enum(EstadoAcuerdo, "estado_acuerdo"), default=EstadoAcuerdo.PROGRAMADO
    )
    fecha_programada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = ts_creado()

    publicacion: Mapped[Publicacion] = relationship(lazy="joined")
    solicitante: Mapped[Usuario] = relationship(lazy="joined", foreign_keys=[solicitante_id])
    proveedor: Mapped[Usuario] = relationship(lazy="joined", foreign_keys=[proveedor_id])


class Resena(Base):
    __tablename__ = "resena"
    id: Mapped[uuid.UUID] = pk_uuid()
    acuerdo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("acuerdo.id"))
    autor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    destinatario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    calificacion: Mapped[int] = mapped_column(SmallInteger)
    comentario: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = ts_creado()

    autor: Mapped[Usuario] = relationship(lazy="joined", foreign_keys=[autor_id])
