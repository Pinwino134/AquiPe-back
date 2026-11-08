import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .enums import (
    DireccionPublicacion,
    EstadoAcuerdo,
    EstadoPublicacion,
    EstadoRespuesta,
    ModalidadServicio,
    NivelUrgencia,
    TipoPrecio,
    TipoPublicacion,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Catálogos
# ----------------------------------------------------------------------
class ZonaOut(ORM):
    id: int
    nombre: str
    distrito: str
    ciudad: str
    latitud: float
    longitud: float


class CategoriaOut(BaseModel):
    id: int
    nombre: str
    icono: str | None = None
    padre_id: int | None = None
    aplica_a: list[TipoPublicacion]


class CategoriaResumen(ORM):
    id: int
    nombre: str
    icono: str | None = None


# ----------------------------------------------------------------------
# Usuarios
# ----------------------------------------------------------------------
def _normalizar_telefono(v: str) -> str:
    limpio = re.sub(r"[\s\-().]", "", v)
    if not re.fullmatch(r"\+?\d{7,15}", limpio):
        raise ValueError("Teléfono inválido (7 a 15 dígitos)")
    return limpio


class RegistroIn(BaseModel):
    nombre_completo: str = Field(min_length=2, max_length=120)
    correo: EmailStr
    telefono: str
    password: str = Field(min_length=6, max_length=100)
    zona_id: int | None = None

    _tel = field_validator("telefono")(_normalizar_telefono)


class LoginIn(BaseModel):
    correo: EmailStr
    password: str


class PerfilProveedorIn(BaseModel):
    biografia: str | None = Field(None, max_length=500)
    anios_experiencia: int | None = Field(None, ge=0, le=80)
    disponibilidad: str | None = Field(None, max_length=200)


class PerfilProveedorOut(ORM):
    biografia: str | None
    anios_experiencia: int | None
    disponibilidad: str | None
    verificado: bool


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = Field(None, min_length=2, max_length=120)
    telefono: str | None = None
    zona_id: int | None = None
    latitud: float | None = Field(None, ge=-90, le=90)
    longitud: float | None = Field(None, ge=-180, le=180)
    foto_url: str | None = None
    perfil_publico: bool | None = None
    notificaciones_activas: bool | None = None

    @field_validator("telefono")
    @classmethod
    def _tel(cls, v):
        return None if v is None else _normalizar_telefono(v)


class UsuarioResumen(ORM):
    id: uuid.UUID
    nombre_completo: str
    foto_url: str | None
    calificacion_promedio: float
    total_resenas: int


class UsuarioOut(UsuarioResumen):
    """Datos del propio usuario (login, /usuarios/me)."""
    correo: str
    telefono: str
    zona: ZonaOut | None
    latitud: float | None
    longitud: float | None
    perfil_publico: bool
    notificaciones_activas: bool
    perfil_proveedor: PerfilProveedorOut | None
    created_at: datetime
    access_token: str | None = None


class UsuarioPublico(UsuarioResumen):
    """Perfil que ve otro usuario. El teléfono solo aparece si el perfil es público
    o si ambos tienen un acuerdo."""
    zona: ZonaOut | None
    perfil_proveedor: PerfilProveedorOut | None
    telefono: str | None = None


# ----------------------------------------------------------------------
# Publicaciones
# ----------------------------------------------------------------------
class DetalleServicioIn(BaseModel):
    # Si OFRECE un servicio: tipo_precio, monto, modalidad, radio_km, disponibilidad
    tipo_precio: TipoPrecio = TipoPrecio.A_CONVENIR
    monto: float | None = Field(None, ge=0)
    modalidad: ModalidadServicio = ModalidadServicio.DOMICILIO
    radio_km: float | None = Field(None, gt=0, le=999)
    disponibilidad: str | None = Field(None, max_length=200)
    # Si SOLICITA un trabajo: presupuesto, fecha deseada y urgencia
    presupuesto_min: float | None = Field(None, ge=0)
    presupuesto_max: float | None = Field(None, ge=0)
    fecha_requerida: datetime | None = None
    urgencia: NivelUrgencia = NivelUrgencia.MEDIA

    @model_validator(mode="after")
    def _validar(self):
        if self.tipo_precio != TipoPrecio.A_CONVENIR and self.monto is None:
            raise ValueError("monto es obligatorio cuando tipo_precio no es A_CONVENIR")
        if (
            self.presupuesto_min is not None
            and self.presupuesto_max is not None
            and self.presupuesto_max < self.presupuesto_min
        ):
            raise ValueError("presupuesto_max no puede ser menor que presupuesto_min")
        return self


class DetalleServicioOut(ORM):
    tipo_precio: TipoPrecio
    monto: float | None
    moneda: str
    modalidad: ModalidadServicio
    radio_km: float | None
    disponibilidad: str | None
    presupuesto_min: float | None
    presupuesto_max: float | None
    fecha_requerida: datetime | None
    urgencia: NivelUrgencia


class DetalleEmergenciaIn(BaseModel):
    cantidad: int | None = Field(None, gt=0)
    unidad: str | None = Field(None, max_length=30)
    detalle_cantidad: str | None = Field(None, max_length=200)
    nivel_urgencia: NivelUrgencia = NivelUrgencia.ALTA
    vigente_hasta: datetime | None = None


class DetalleEmergenciaOut(ORM):
    cantidad: int | None
    unidad: str | None
    detalle_cantidad: str | None
    nivel_urgencia: NivelUrgencia
    vigente_hasta: datetime | None


class PublicacionCreate(BaseModel):
    """Una sola entrada para todo lo que se publica:
    - Ofrecer un servicio  -> tipo=SERVICIO,    direccion=OFRECE
    - Solicitud de trabajo -> tipo=SERVICIO,    direccion=SOLICITA
    - Favor / donación     -> tipo=FAVOR,       direccion=SOLICITA u OFRECE
    - Emergencia           -> tipo=EMERGENCIA,  direccion=SOLICITA u OFRECE
    """
    tipo: TipoPublicacion
    direccion: DireccionPublicacion
    categoria_id: int | None = None
    titulo: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(min_length=1, max_length=1000)
    zona_id: int | None = None
    latitud: float | None = Field(None, ge=-90, le=90)
    longitud: float | None = Field(None, ge=-180, le=180)
    expira_at: datetime | None = None
    servicio: DetalleServicioIn | None = None
    emergencia: DetalleEmergenciaIn | None = None

    @model_validator(mode="after")
    def _validar(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("latitud y longitud se envían juntas")
        if self.tipo == TipoPublicacion.SERVICIO:
            if self.emergencia is not None:
                raise ValueError("'emergencia' solo aplica a tipo EMERGENCIA")
            if self.servicio is None:
                self.servicio = DetalleServicioIn()
        elif self.tipo == TipoPublicacion.EMERGENCIA:
            if self.servicio is not None:
                raise ValueError("'servicio' solo aplica a tipo SERVICIO")
            if self.latitud is None:
                raise ValueError("Una emergencia requiere latitud y longitud")
            if self.emergencia is None:
                self.emergencia = DetalleEmergenciaIn()
            if self.direccion == DireccionPublicacion.OFRECE and self.emergencia.cantidad is None:
                raise ValueError("Al ofrecer recursos en una emergencia indica la cantidad")
        else:
            if self.servicio is not None or self.emergencia is not None:
                raise ValueError("'servicio' y 'emergencia' no aplican a este tipo")
        return self


class PublicacionUpdate(BaseModel):
    titulo: str | None = Field(None, min_length=1, max_length=80)
    descripcion: str | None = Field(None, min_length=1, max_length=1000)
    estado: EstadoPublicacion | None = Field(
        None, description="Solo se permite ABIERTA, PAUSADA o CANCELADA"
    )


class PublicacionOut(ORM):
    id: uuid.UUID
    tipo: TipoPublicacion
    direccion: DireccionPublicacion
    titulo: str
    descripcion: str
    estado: EstadoPublicacion
    latitud: float | None
    longitud: float | None
    expira_at: datetime | None
    created_at: datetime
    autor: UsuarioResumen
    categoria: CategoriaResumen | None
    zona: ZonaOut | None
    servicio: DetalleServicioOut | None
    emergencia: DetalleEmergenciaOut | None
    distancia_km: float | None = None


# ----------------------------------------------------------------------
# Respuestas, acuerdos y reseñas
# ----------------------------------------------------------------------
class RespuestaCreate(BaseModel):
    mensaje: str = Field(min_length=1, max_length=500)
    precio_propuesto: float | None = Field(None, ge=0)


class RespuestaOut(ORM):
    id: uuid.UUID
    publicacion_id: uuid.UUID
    mensaje: str
    precio_propuesto: float | None
    estado: EstadoRespuesta
    created_at: datetime
    usuario: UsuarioResumen


class RespuestaMiaOut(RespuestaOut):
    publicacion: "PublicacionResumen"


class PublicacionResumen(ORM):
    id: uuid.UUID
    tipo: TipoPublicacion
    direccion: DireccionPublicacion
    titulo: str
    estado: EstadoPublicacion


RespuestaMiaOut.model_rebuild()


class AceptarIn(BaseModel):
    fecha_programada: datetime | None = None


class AcuerdoOut(ORM):
    id: uuid.UUID
    estado: EstadoAcuerdo
    precio_acordado: float | None
    fecha_programada: datetime | None
    completado_at: datetime | None
    cancelado_at: datetime | None
    motivo_cancelacion: str | None
    created_at: datetime
    publicacion: PublicacionResumen
    solicitante: UsuarioResumen
    proveedor: UsuarioResumen


class AcuerdoEstadoIn(BaseModel):
    estado: EstadoAcuerdo
    motivo: str | None = Field(None, max_length=300, description="Solo al cancelar")


class ResenaCreate(BaseModel):
    calificacion: int = Field(ge=1, le=5)
    comentario: str | None = Field(None, max_length=500)


class ResenaOut(ORM):
    id: uuid.UUID
    acuerdo_id: uuid.UUID
    calificacion: int
    comentario: str | None
    created_at: datetime
    autor: UsuarioResumen


class CalificarServicioIn(BaseModel):
    calificacion: int = Field(ge=1, le=5)
    comentario: str | None = Field(None, max_length=400)
    etiquetas: list[str] = Field(default_factory=list, max_length=5)


class CalificarServicioOut(BaseModel):
    resena: ResenaOut
    calificacion_promedio: float
    total_resenas: int
    visto_bueno_vecinal: bool


class RecursoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=300)
    cantidad: int = Field(1, gt=0)
    unidad: str | None = Field(None, max_length=30)
    disponible: bool = True


class RecursoUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=300)
    cantidad: int | None = Field(None, gt=0)
    unidad: str | None = Field(None, max_length=30)
    disponible: bool | None = None


class RecursoOut(ORM):
    id: uuid.UUID
    usuario_id: uuid.UUID
    nombre: str
    descripcion: str | None
    cantidad: int
    unidad: str | None
    disponible: bool
    created_at: datetime
