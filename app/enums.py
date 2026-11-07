"""Enumeraciones. Los valores coinciden exactamente con los tipos ENUM de sql/aquipe_db.sql."""
from enum import Enum


class EstadoUsuario(str, Enum):
    ACTIVO = "ACTIVO"
    SUSPENDIDO = "SUSPENDIDO"
    ELIMINADO = "ELIMINADO"


class TipoPublicacion(str, Enum):
    SERVICIO = "SERVICIO"
    FAVOR = "FAVOR"
    RECURSO = "RECURSO"
    EMERGENCIA = "EMERGENCIA"


class DireccionPublicacion(str, Enum):
    SOLICITA = "SOLICITA"
    OFRECE = "OFRECE"


class EstadoPublicacion(str, Enum):
    ABIERTA = "ABIERTA"
    PAUSADA = "PAUSADA"
    ASIGNADA = "ASIGNADA"
    EN_CURSO = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    CANCELADA = "CANCELADA"
    EXPIRADA = "EXPIRADA"


class TipoPrecio(str, Enum):
    FIJO = "FIJO"
    POR_HORA = "POR_HORA"
    A_CONVENIR = "A_CONVENIR"


class ModalidadServicio(str, Enum):
    DOMICILIO = "DOMICILIO"
    VIRTUAL = "VIRTUAL"
    EN_LOCAL = "EN_LOCAL"


class NivelUrgencia(str, Enum):
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class EstadoRespuesta(str, Enum):
    ENVIADA = "ENVIADA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    RETIRADA = "RETIRADA"


class EstadoAcuerdo(str, Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_CURSO = "EN_CURSO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"
