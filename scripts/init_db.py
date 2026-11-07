import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import psycopg  

from app.config import DATABASE_URL  

url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
sql = (pathlib.Path(__file__).resolve().parent.parent / "sql" / "aquipe_db.sql").read_text(encoding="utf-8")

with psycopg.connect(url, autocommit=True) as conn:
    if conn.execute("SELECT to_regclass('public.usuario')").fetchone()[0]:
        print("Las tablas ya existen. No se hizo nada.")
        sys.exit(0)
    conn.execute(sql)
    print("Base de datos creada correctamente.")
