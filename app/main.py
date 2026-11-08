import psycopg.errors as pgerr
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .config import CORS_ORIGINS
from .database import engine
from .routers import acuerdos, auth, catalogos, publicaciones, recursos, respuestas, usuarios

app = FastAPI(
    title="AquiPe API",
    version="0.2.0",
    description=(
        "Backend de AquiPe (hackatón). Soporta autenticación segura con Bearer Token firmado "
        "(HMAC-SHA256) devuelto en `/auth/login` y compatibilidad con header `X-User-Id`."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def agregar_cabeceras_seguridad(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


for r in (
    auth.router,
    usuarios.router,
    catalogos.router,
    publicaciones.router,
    respuestas.router,
    acuerdos.router,
    recursos.router,
):
    app.include_router(r)


@app.get("/health", tags=["Sistema"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.exception_handler(DBAPIError)
async def errores_de_base_de_datos(request: Request, exc: DBAPIError):
    """Traduce los errores de reglas de negocio de la base de datos (triggers y constraints)
    a respuestas HTTP claras."""
    orig = exc.orig
    if isinstance(orig, pgerr.RaiseException):  # RAISE EXCEPTION de los triggers
        return JSONResponse(status_code=409, content={"detail": orig.diag.message_primary})
    if isinstance(orig, pgerr.UniqueViolation):
        return JSONResponse(
            status_code=409,
            content={"detail": "Ya existe un registro con esos datos", "restriccion": orig.diag.constraint_name},
        )
    if isinstance(orig, (pgerr.CheckViolation, pgerr.ForeignKeyViolation, pgerr.NotNullViolation)):
        return JSONResponse(
            status_code=422,
            content={"detail": "Datos no válidos", "restriccion": orig.diag.constraint_name},
        )
    raise exc
