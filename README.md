# AquiPe – Backend (FastAPI + PostgreSQL)

API del MVP de AquiPe: registro/login, perfil, ofrecer servicios, solicitudes de trabajo, favores,
emergencias, respuestas (postulaciones), acuerdos y reseñas.

> **Autenticación sin tokens (solo desarrollo).** El login devuelve el usuario; el frontend guarda su `id`
> y lo manda en el header `X-User-Id`. Ver [Pasar a JWT](#pasar-a-jwt-más-adelante).

## 1. Puesta en marcha

Requisitos: Python 3.11+ y PostgreSQL 13+ (local con Docker, o Supabase / Neon gratis).

```bash
# 1) Entorno e instalación
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 2) Base de datos
copy .env.example .env            # Linux/Mac: cp .env.example .env
docker compose up -d              # crea Postgres y las tablas (sql/aquipe_db.sql) la primera vez
#   Sin Docker: crea la base en Supabase/Neon, pega su cadena en DATABASE_URL (.env)
#   y ejecuta:  python scripts/init_db.py

# 3) Datos de demostración (opcional, recomendado para la demo)
python scripts/seed_demo.py

# 4) Servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Documentación interactiva: <http://localhost:8000/docs>
- Usuarios demo (contraseña `demo1234`): `ana@`, `carlos@`, `luis@`, `andrea@`, `miguel@`, `maria@` + `aquipe.pe`
- Prueba de humo del flujo completo: `python tests/smoke_test.py`

## 2. Cómo probar en Swagger

1. `POST /auth/login` con `{"correo": "ana@aquipe.pe", "password": "demo1234"}`.
2. Copia el `id` de la respuesta → botón **Authorize** → pégalo en `X-User-Id`.
3. Para simular a otra persona, vuelve a Authorize con el `id` de otro usuario.

## 3. Conectar el frontend (Expo)

```ts
const API = 'http://TU_IP_LOCAL:8000';   // no uses localhost desde el celular; Android emulador: 10.0.2.2
let usuarioId: string | null = null;

export async function login(correo: string, password: string) {
  const r = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ correo, password }),
  });
  if (!r.ok) throw new Error((await r.json()).detail);
  const usuario = await r.json();
  usuarioId = usuario.id;
  return usuario;
}

export async function api(path: string, init: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-User-Id': usuarioId ?? '', ...(init.headers || {}) },
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? 'Error');
  return r.status === 204 ? null : r.json();
}
```

Los errores de reglas de negocio llegan como `{ "detail": "mensaje legible" }` (409/422).

## 4. Endpoints

| Módulo | Endpoint | Descripción |
|---|---|---|
| Auth | `POST /auth/registro` · `POST /auth/login` | Crear cuenta · entrar (devuelve el usuario) |
| Usuarios | `GET/PATCH /usuarios/me` | Mi perfil (zona, ubicación, privacidad, notificaciones) |
| | `PUT /usuarios/me/proveedor` | Activar/editar perfil de quien ofrece servicios |
| | `GET /usuarios/{id}` · `GET /usuarios/{id}/resenas` | Perfil público y reseñas recibidas |
| Catálogos | `GET /zonas` · `GET /categorias?tipo=SERVICIO` | Zonas y categorías |
| Publicaciones | `POST /publicaciones` | Crear (servicio, solicitud de trabajo, favor, emergencia) |
| | `GET /publicaciones` | Feed/mapa: filtros `tipo, direccion, categoria_id, zona_id, estado, q, lat, lng, radio_km` |
| | `GET /publicaciones/mias` · `GET/PATCH/DELETE /publicaciones/{id}` | Mis publicaciones · detalle · editar/pausar · borrar |
| Respuestas | `POST /publicaciones/{id}/respuestas` | Postularse / contratar / ofrecer ayuda |
| | `GET /publicaciones/{id}/respuestas` | Respuestas recibidas (solo el autor) |
| | `GET /respuestas/mias` · `POST /respuestas/{id}/retirar` | Mis postulaciones · retirar |
| | `POST /respuestas/{id}/aceptar` · `/rechazar` | El autor decide (aceptar crea el acuerdo) |
| Acuerdos | `GET /acuerdos/mios` · `GET /acuerdos/{id}` | Trabajos acordados |
| | `PATCH /acuerdos/{id}/estado` | `EN_CURSO` → `COMPLETADO` o `CANCELADO` |
| | `POST /acuerdos/{id}/resenas` | Reseñar a la otra parte (acuerdo completado) |

## 5. Las dos funcionalidades nuevas

**Ofrecer un servicio** – `POST /publicaciones`
```json
{ "tipo": "SERVICIO", "direccion": "OFRECE", "categoria_id": 1,
  "titulo": "Electricista a domicilio", "descripcion": "Instalaciones y reparaciones.",
  "zona_id": 1,
  "servicio": { "tipo_precio": "FIJO", "monto": 45, "modalidad": "DOMICILIO", "radio_km": 5,
                "disponibilidad": "Lun-Sáb 8:00-18:00" } }
```

**Solicitud de trabajo** – `POST /publicaciones`
```json
{ "tipo": "SERVICIO", "direccion": "SOLICITA", "categoria_id": 1,
  "titulo": "Necesito un electricista", "descripcion": "Revisar el tablero de mi casa.",
  "servicio": { "presupuesto_min": 50, "presupuesto_max": 120, "urgencia": "ALTA",
                "fecha_requerida": "2026-11-12T09:00:00-05:00" } }
```

**Flujo completo de una solicitud de trabajo**

1. Ana publica la solicitud → estado `ABIERTA`.
2. Carlos y Luis se postulan: `POST /publicaciones/{id}/respuestas` con `mensaje` y `precio_propuesto`.
3. Ana ve las propuestas (`GET /publicaciones/{id}/respuestas`) y acepta una: `POST /respuestas/{id}/aceptar`.
   Se crea el acuerdo, la solicitud pasa a `ASIGNADA` y las demás propuestas quedan `RECHAZADA`.
4. Cualquiera de los dos avanza el acuerdo: `PATCH /acuerdos/{id}/estado` → `EN_CURSO` → `COMPLETADO`.
5. Ambos se reseñan: `POST /acuerdos/{id}/resenas`. La calificación promedio del usuario se actualiza sola.

Para **contratar un servicio ofrecido** es igual, pero se responde a la publicación `OFRECE`;
la oferta sigue `ABIERTA` para atender a más personas. Los pagos se hacen fuera de la app
(el acuerdo solo guarda el `precio_acordado` como referencia).

Si no envías `latitud`/`longitud`, la publicación usa la ubicación del usuario y, si no tiene, el centro de su zona.
Las emergencias sí requieren coordenadas.

## 6. Dónde viven las reglas de negocio

Las reglas críticas están en la base de datos (`sql/aquipe_db.sql`), así que se cumplen aunque cambie el backend:
no responder a la propia publicación, una respuesta por persona, una sola respuesta aceptada por solicitud,
reseñas solo entre las partes de un acuerdo completado. La API las traduce a errores HTTP 409/422 con un mensaje claro.

## 7. Pasar a JWT (más adelante)

Todos los endpoints dependen de `get_current_user` en `app/auth.py`. Para activar JWT solo hay que cambiar el cuerpo
de esa función (leer `Authorization: Bearer <token>`, validarlo y buscar al usuario) y hacer que `/auth/login`
devuelva el token. Ningún endpoint se modifica.
**Mientras tanto, no despliegues esto como producción**: quien conozca un UUID puede suplantar a ese usuario.

## 8. Estructura

```
app/
  main.py            # app, CORS y traducción de errores de la base de datos
  auth.py            # get_current_user (modo X-User-Id) + hash argon2
  models.py          # modelos SQLAlchemy (mapean las tablas existentes)
  schemas.py         # validación de entrada/salida (Pydantic)
  routers/           # auth, usuarios, catalogos, publicaciones, respuestas, acuerdos
sql/aquipe_db.sql    # esquema completo (tablas, enums, triggers, datos iniciales)
scripts/             # init_db.py, seed_demo.py
tests/smoke_test.py  # recorre todo el flujo
```

## 9. Pendiente (siguientes pasos)

Coincidencias automáticas (tabla `coincidencia`), notificaciones y push (`notificacion`, `dispositivo_push`),
recursos personales (`recurso`), fotos (`publicacion_adjunto`), reportes/bloqueos y recuperación de contraseña.
Las tablas ya existen; faltan sus endpoints.
