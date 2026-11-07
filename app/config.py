import os

from dotenv import load_dotenv

load_dotenv()


def _normalizar_url(url: str) -> str:
    for prefijo in ("postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


DATABASE_URL = _normalizar_url(
    os.getenv("DATABASE_URL", "postgresql://aquipe:aquipe@localhost:5432/aquipe")
)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
