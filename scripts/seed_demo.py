"""Datos de demostración para la hackatón (usuarios, servicios, favores, emergencias).
Uso:  python scripts/seed_demo.py
Todos los usuarios tienen la contraseña  demo1234  (ana@aquipe.pe, carlos@aquipe.pe, ...)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.auth import hashear_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.enums import *  # noqa: E402,F403
from app.models import (  # noqa: E402
    Acuerdo, Categoria, DetalleEmergencia, DetalleServicio, PerfilProveedor,
    Publicacion, Resena, Respuesta, Usuario, Zona,
)

db = SessionLocal()
if db.scalar(select(Usuario.id).where(Usuario.correo == "ana@aquipe.pe")):
    print("Los datos de demostración ya existen. No se hizo nada.")
    sys.exit(0)

zona = {z.nombre: z for z in db.scalars(select(Zona))}
cat = {c.nombre: c.id for c in db.scalars(select(Categoria))}

# --- Usuarios -----------------------------------------------------------
def usuario(nombre, correo, tel, zona_nombre):
    z = zona[zona_nombre]
    u = Usuario(nombre_completo=nombre, correo=correo, telefono=tel,
                password_hash=hashear_password("demo1234"), zona_id=z.id,
                latitud=z.latitud, longitud=z.longitud)
    db.add(u)
    return u

ana = usuario("Ana Torres", "ana@aquipe.pe", "999111001", "Cercado")
carlos = usuario("Carlos Ramos", "carlos@aquipe.pe", "999111222", "Cercado")
luis = usuario("Luis Mamani", "luis@aquipe.pe", "999222333", "Yanahuara")
andrea = usuario("Andrea Paredes", "andrea@aquipe.pe", "999333444", "Cayma")
miguel = usuario("Miguel Tapia", "miguel@aquipe.pe", "999444555", "Cercado")
maria = usuario("María Quispe", "maria@aquipe.pe", "999555666", "Cercado")
db.flush()

for u, bio, anios in [(carlos, "Electricista con experiencia en instalaciones domiciliarias.", 10),
                      (luis, "Gasfitero: reparación de tuberías y mantenimiento.", 7),
                      (andrea, "Profesora de matemáticas y apoyo escolar.", 5),
                      (miguel, "Soporte técnico y mantenimiento de computadoras.", 6)]:
    db.add(PerfilProveedor(usuario_id=u.id, biografia=bio, anios_experiencia=anios))

# --- Publicaciones ------------------------------------------------------
def pub(autor, tipo, direccion, categoria, titulo, desc, zona_nombre, lat=None, lng=None,
        servicio=None, emergencia=None):
    z = zona[zona_nombre]
    p = Publicacion(autor_id=autor.id, tipo=tipo, direccion=direccion,
                    categoria_id=cat.get(categoria), titulo=titulo, descripcion=desc,
                    zona_id=z.id, latitud=lat or z.latitud, longitud=lng or z.longitud)
    if servicio:
        p.servicio = DetalleServicio(**servicio)
    if emergencia:
        p.emergencia = DetalleEmergencia(**emergencia)
    db.add(p)
    return p

S, F, E = TipoPublicacion.SERVICIO, TipoPublicacion.FAVOR, TipoPublicacion.EMERGENCIA
OFRECE, SOLICITA = DireccionPublicacion.OFRECE, DireccionPublicacion.SOLICITA
fijo, hora = TipoPrecio.FIJO, TipoPrecio.POR_HORA

def serv(tipo_precio=TipoPrecio.A_CONVENIR, monto=None, modalidad=ModalidadServicio.DOMICILIO,
         radio_km=None, presupuesto_min=None, presupuesto_max=None, urgencia=NivelUrgencia.MEDIA):
    return dict(tipo_precio=tipo_precio, monto=monto, modalidad=modalidad, radio_km=radio_km,
                presupuesto_min=presupuesto_min, presupuesto_max=presupuesto_max, urgencia=urgencia)

# Servicios ofrecidos
pub(carlos, S, OFRECE, "Hogar", "Electricista a domicilio", "Instalaciones eléctricas, reparaciones y mantenimiento.",
    "Cercado", -16.3988, -71.5369, serv(fijo, 45, radio_km=5))
pub(luis, S, OFRECE, "Hogar", "Gasfitero", "Reparación de tuberías y mantenimiento.",
    "Yanahuara", -16.395, -71.541, serv(fijo, 40, radio_km=5))
pub(andrea, S, OFRECE, "Educación", "Clases particulares de matemáticas", "A domicilio o virtuales.",
    "Cayma", -16.403, -71.525, serv(hora, 30, ModalidadServicio.VIRTUAL, 8))
pub(miguel, S, OFRECE, "Tecnología", "Soporte técnico", "Reparación y mantenimiento de computadoras.",
    "Cercado", -16.4015, -71.5295, serv(fijo, 45, radio_km=6))

# Solicitudes de trabajo
sol_ana = pub(ana, S, SOLICITA, "Hogar", "Necesito un electricista", "Revisión del tablero eléctrico de mi casa.",
              "Cercado", -16.3975, -71.5335, serv(presupuesto_min=50, presupuesto_max=120, urgencia=NivelUrgencia.ALTA))
pub(maria, S, SOLICITA, "Seguridad", "Instalación de cámaras", "Dos cámaras en la entrada de mi casa.",
    "Cercado", -16.3955, -71.540, serv(presupuesto_min=150, presupuesto_max=300))

# Favores
pub(maria, F, SOLICITA, "Herramienta", "Préstamo de escalera", "Necesito una escalera para una reparación.",
    "Cercado", -16.3948, -71.532)
pub(ana, F, SOLICITA, "Apoyo", "Apoyo en tareas escolares", "Busco ayuda con ejercicios de matemáticas.",
    "Cercado", -16.405, -71.538)
pub(miguel, F, OFRECE, "Tecnología", "Ayuda con computadoras", "Puedo ayudar a vecinos con sus equipos.", "Cercado")

# Emergencias
pub(carlos, E, OFRECE, "Agua y alimentos", "Puesto de apoyo comunitario", "Agua potable y alimentos no perecibles.",
    "Cercado", -16.399, -71.536,
    emergencia=dict(cantidad=20, unidad="botellas", detalle_cantidad="20 botellas de agua y 15 paquetes",
                    nivel_urgencia=NivelUrgencia.ALTA))
pub(ana, E, SOLICITA, "Agua y alimentos", "Solicitud de agua potable", "Se necesita agua para varias familias.",
    "Cercado", -16.402, -71.531, emergencia=dict(nivel_urgencia=NivelUrgencia.CRITICA))
db.flush()

# --- Un trabajo ya completado (para que existan reseñas) ----------------
pasado = pub(maria, S, SOLICITA, "Hogar", "Cambio de tomacorrientes", "Cambiar 3 tomacorrientes.",
             "Cercado", servicio=serv(presupuesto_min=40, presupuesto_max=80))
db.flush()
r = Respuesta(publicacion_id=pasado.id, usuario_id=carlos.id, mensaje="Puedo ir mañana.", precio_propuesto=60)
db.add(r); db.flush()
r.estado = EstadoRespuesta.ACEPTADA; db.flush()
ac = Acuerdo(publicacion_id=pasado.id, respuesta_id=r.id, solicitante_id=maria.id, proveedor_id=carlos.id,
             precio_acordado=60, estado=EstadoAcuerdo.COMPLETADO)
pasado.estado = EstadoPublicacion.COMPLETADA
db.add(ac); db.flush()
db.add(Resena(acuerdo_id=ac.id, autor_id=maria.id, destinatario_id=carlos.id, calificacion=5, comentario="Puntual y responsable."))
db.add(Resena(acuerdo_id=ac.id, autor_id=carlos.id, destinatario_id=maria.id, calificacion=5, comentario="Muy amable."))

# --- Una postulación pendiente para probar "aceptar" --------------------
db.add(Respuesta(publicacion_id=sol_ana.id, usuario_id=carlos.id, mensaje="Puedo ir hoy mismo.", precio_propuesto=80))
db.commit()
print("Datos de demostración creados. Usuarios: ana, carlos, luis, andrea, miguel, maria @aquipe.pe  (contraseña: demo1234)")
