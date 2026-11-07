"""Prueba de humo del flujo completo. Requiere la base con datos demo (scripts/seed_demo.py).
Uso:  python tests/smoke_test.py"""
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
fallos = []


def check(nombre, resp, esperado):
    ok = resp.status_code == esperado
    print(("OK   " if ok else "FALLA"), f"{nombre}: {resp.status_code} (esperado {esperado})")
    if not ok:
        print("      ", resp.text[:300])
        fallos.append(nombre)
    return resp


def login(correo):
    r = check(f"login {correo}", c.post("/auth/login", json={"correo": correo, "password": "demo1234"}), 200)
    return {"X-User-Id": r.json()["id"]}, r.json()


check("health", c.get("/health"), 200)
check("login con clave mala", c.post("/auth/login", json={"correo": "ana@aquipe.pe", "password": "x"}), 401)
check("sin header", c.get("/usuarios/me"), 401)

nuevo = f"{uuid.uuid4().hex[:8]}@test.pe"
r = check("registro", c.post("/auth/registro", json={
    "nombre_completo": "Prueba Uno", "correo": nuevo, "telefono": "987 654 3" + str(uuid.uuid4().int)[:2], "password": "secreto1", "zona_id": 2}), 201)
check("registro correo repetido", c.post("/auth/registro", json={
    "nombre_completo": "Otro", "correo": nuevo, "telefono": "911222333", "password": "secreto1"}), 409)

ana, ana_u = login("ana@aquipe.pe")
carlos, carlos_u = login("carlos@aquipe.pe")
luis, _ = login("luis@aquipe.pe")
maria, _ = login("maria@aquipe.pe")

check("zonas", c.get("/zonas"), 200)
cats = check("categorias SERVICIO", c.get("/categorias", params={"tipo": "SERVICIO"}), 200).json()
print("      categorías de servicio:", [x["nombre"] for x in cats])
check("mi perfil", c.get("/usuarios/me", headers=ana), 200)
check("activar perfil proveedor", c.put("/usuarios/me/proveedor", headers=ana, json={"biografia": "Hola", "anios_experiencia": 2}), 200)

# ---- Crear solicitud de trabajo (nueva funcionalidad) ----
hogar = next(x["id"] for x in cats if x["nombre"] == "Hogar")
r = check("crear solicitud de trabajo", c.post("/publicaciones", headers=ana, json={
    "tipo": "SERVICIO", "direccion": "SOLICITA", "categoria_id": hogar,
    "titulo": "Pintar una habitación", "descripcion": "Habitación de 3x4 m.",
    "servicio": {"presupuesto_min": 100, "presupuesto_max": 200, "urgencia": "BAJA"}}), 201)
sol = r.json()
print("      ubicación heredada:", sol["latitud"], sol["longitud"], "| estado:", sol["estado"])
check("solicitud con categoría que no aplica", c.post("/publicaciones", headers=ana, json={
    "tipo": "SERVICIO", "direccion": "SOLICITA", "categoria_id": 7, "titulo": "x", "descripcion": "x"}), 422)
check("emergencia sin coordenadas", c.post("/publicaciones", headers=ana, json={
    "tipo": "EMERGENCIA", "direccion": "SOLICITA", "titulo": "x", "descripcion": "x"}), 422)
check("monto obligatorio si precio FIJO", c.post("/publicaciones", headers=carlos, json={
    "tipo": "SERVICIO", "direccion": "OFRECE", "titulo": "x", "descripcion": "x", "servicio": {"tipo_precio": "FIJO"}}), 422)

# ---- Ofrecer un servicio (nueva funcionalidad) ----
r = check("ofrecer servicio", c.post("/publicaciones", headers=luis, json={
    "tipo": "SERVICIO", "direccion": "OFRECE", "categoria_id": hogar,
    "titulo": "Pintura de interiores", "descripcion": "Pinto casas y departamentos.",
    "servicio": {"tipo_precio": "POR_HORA", "monto": 25, "modalidad": "DOMICILIO", "radio_km": 6}}), 201)
oferta = r.json()

# ---- Listados ----
r = check("feed cerca de Cercado (radio 3km)", c.get("/publicaciones", headers=ana, params={
    "lat": -16.399, "lng": -71.535, "radio_km": 3, "tipo": "SERVICIO", "direccion": "OFRECE"}), 200)
print("      cercanos:", [(p["titulo"], p["distancia_km"]) for p in r.json()])
check("búsqueda por texto", c.get("/publicaciones", headers=ana, params={"q": "electricista"}), 200)
check("mis publicaciones", c.get("/publicaciones/mias", headers=ana), 200)
check("detalle", c.get(f"/publicaciones/{sol['id']}", headers=carlos), 200)

# ---- Respuestas ----
check("responder a mi propia publicación", c.post(f"/publicaciones/{sol['id']}/respuestas", headers=ana, json={"mensaje": "yo"}), 409)
r1 = check("Carlos se postula", c.post(f"/publicaciones/{sol['id']}/respuestas", headers=carlos, json={"mensaje": "Puedo ir", "precio_propuesto": 150}), 201).json()
r2 = check("Luis se postula", c.post(f"/publicaciones/{sol['id']}/respuestas", headers=luis, json={"mensaje": "Yo también", "precio_propuesto": 170}), 201).json()
check("postulación duplicada", c.post(f"/publicaciones/{sol['id']}/respuestas", headers=carlos, json={"mensaje": "otra vez"}), 409)
check("solo el autor ve respuestas (403)", c.get(f"/publicaciones/{sol['id']}/respuestas", headers=carlos), 403)
resp = check("Ana ve respuestas", c.get(f"/publicaciones/{sol['id']}/respuestas", headers=ana), 200).json()
print("      respuestas recibidas:", len(resp))
check("mis respuestas (Carlos)", c.get("/respuestas/mias", headers=carlos), 200)
check("Carlos no puede aceptar", c.post(f"/respuestas/{r1['id']}/aceptar", headers=carlos), 403)

# ---- Aceptar -> acuerdo ----
ac = check("Ana acepta a Carlos", c.post(f"/respuestas/{r1['id']}/aceptar", headers=ana, json={}), 201).json()
print("      acuerdo:", ac["estado"], "| solicitante:", ac["solicitante"]["nombre_completo"], "| proveedor:", ac["proveedor"]["nombre_completo"], "| precio:", ac["precio_acordado"])
check("publicación quedó ASIGNADA", c.get(f"/publicaciones/{sol['id']}", headers=ana), 200)
print("      estado publicación:", c.get(f"/publicaciones/{sol['id']}", headers=ana).json()["estado"])
estados = {x["usuario"]["nombre_completo"]: x["estado"] for x in c.get(f"/publicaciones/{sol['id']}/respuestas", headers=ana).json()}
print("      respuestas:", estados)
check("aceptar a Luis también (debe fallar)", c.post(f"/respuestas/{r2['id']}/aceptar", headers=ana), 409)

# ---- Ciclo del acuerdo y reseñas ----
check("reseña antes de completar", c.post(f"/acuerdos/{ac['id']}/resenas", headers=ana, json={"calificacion": 5}), 409)
check("Luis no participa (403)", c.get(f"/acuerdos/{ac['id']}", headers=luis), 403)
check("PROGRAMADO -> EN_CURSO", c.patch(f"/acuerdos/{ac['id']}/estado", headers=carlos, json={"estado": "EN_CURSO"}), 200)
check("EN_CURSO -> COMPLETADO", c.patch(f"/acuerdos/{ac['id']}/estado", headers=ana, json={"estado": "COMPLETADO"}), 200)
check("COMPLETADO -> CANCELADO (inválido)", c.patch(f"/acuerdos/{ac['id']}/estado", headers=ana, json={"estado": "CANCELADO"}), 409)
check("reseña Ana -> Carlos", c.post(f"/acuerdos/{ac['id']}/resenas", headers=ana, json={"calificacion": 4, "comentario": "Buen trabajo"}), 201)
check("reseña duplicada", c.post(f"/acuerdos/{ac['id']}/resenas", headers=ana, json={"calificacion": 1}), 409)
check("reseña Carlos -> Ana", c.post(f"/acuerdos/{ac['id']}/resenas", headers=carlos, json={"calificacion": 5}), 201)
perfil = check("perfil público de Carlos", c.get(f"/usuarios/{carlos_u['id']}", headers=ana), 200).json()
print("      Carlos:", perfil["calificacion_promedio"], "con", perfil["total_resenas"], "reseñas | teléfono visible:", perfil["telefono"])
check("reseñas de Carlos", c.get(f"/usuarios/{carlos_u['id']}/resenas", headers=ana), 200)
print("      estado final publicación:", c.get(f"/publicaciones/{sol['id']}", headers=ana).json()["estado"])

# ---- Contratar un servicio ofrecido (OFRECE) ----
ro = check("Ana contrata la oferta de Luis", c.post(f"/publicaciones/{oferta['id']}/respuestas", headers=ana, json={"mensaje": "Necesito pintar mi sala"}), 201).json()
ac2 = check("Luis acepta", c.post(f"/respuestas/{ro['id']}/aceptar", headers=luis), 201).json()
print("      oferta sigue:", c.get(f"/publicaciones/{oferta['id']}", headers=ana).json()["estado"], "| precio acordado (de la oferta):", ac2["precio_acordado"], "| solicitante:", ac2["solicitante"]["nombre_completo"])
check("cancelar acuerdo", c.patch(f"/acuerdos/{ac2['id']}/estado", headers=ana, json={"estado": "CANCELADO", "motivo": "Ya no lo necesito"}), 200)

# ---- Editar / pausar / eliminar ----
check("Carlos no puede editar publicación ajena", c.patch(f"/publicaciones/{oferta['id']}", headers=carlos, json={"titulo": "hack"}), 403)
check("Luis pausa su oferta", c.patch(f"/publicaciones/{oferta['id']}", headers=luis, json={"estado": "PAUSADA"}), 200)
check("Luis elimina su oferta", c.delete(f"/publicaciones/{oferta['id']}", headers=luis), 204)
check("eliminada -> 404", c.get(f"/publicaciones/{oferta['id']}", headers=luis), 404)
check("actualizar mi perfil", c.patch("/usuarios/me", headers=ana, json={"perfil_publico": False, "telefono": "+51 999 111 001"}), 200)

print("\nFALLOS:", fallos if fallos else "ninguno")
sys.exit(1 if fallos else 0)
