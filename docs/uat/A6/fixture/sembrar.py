#!/usr/bin/env python3
"""Siembra el catálogo sintético de A6 en el entorno E-A6 (nunca en producción).

Requiere:
  COMPOSE_FILE, ENV_FILE, DB_NAME, DB_USER
  HOST_LIBRARY_DIR  raíz de biblioteca del host (bind a LIBRARY_PATH en el contenedor)
  LIBRARY_PATH      raíz de biblioteca del contenedor (por defecto /biblioteca)

Crea 2 series, 2 números y 2 archivos con UUID fijos. El progreso de lectura NO se
siembra por SQL: lo escribe el lector real (`POST /ui/leer/<file_id>/progreso`).
No imprime rutas absolutas ni credenciales.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
UUID_S1 = "a6000000-0000-4000-8000-000000000001"
UUID_S2 = "a6000000-0000-4000-8000-000000000002"
UUID_I1 = "a6000000-0000-4000-8000-000000000011"
UUID_I2 = "a6000000-0000-4000-8000-000000000012"
UUID_F1 = "a6000000-0000-4000-8000-000000000021"
UUID_F2 = "a6000000-0000-4000-8000-000000000022"

COMPOSE = os.environ.get("COMPOSE_FILE", "")
ENV_FILE = os.environ.get("ENV_FILE", "")
DB_NAME = os.environ.get("DB_NAME", "zascarr")
DB_USER = os.environ.get("DB_USER", "comics_admin")
HOST_LIBRARY_DIR = pathlib.Path(os.environ["HOST_LIBRARY_DIR"])
LIBRARY_PATH = os.environ.get("LIBRARY_PATH", "/biblioteca")
assert COMPOSE and ENV_FILE, "Faltan COMPOSE_FILE/ENV_FILE"
assert LIBRARY_PATH.startswith("/") and LIBRARY_PATH != "/", "LIBRARY_PATH no válido"


def psql(sql: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE, "--env-file", ENV_FILE, "exec", "-T",
         "postgres", "psql", "-U", DB_USER, "-d", DB_NAME, "-v", "ON_ERROR_STOP=1", "-q"],
        input=sql, text=True, check=True,
    )


def sha256(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fila(uuid: str, issue: str, raiz: pathlib.Path, nombre: str) -> str:
    archivo = raiz / nombre
    st = archivo.stat()
    ruta = f"{LIBRARY_PATH}/{raiz.name}/{nombre}"
    return (f"('{uuid}','{issue}','{root_id}','{ruta}','{nombre}','cbz',"
            f"{st.st_size},{st.st_mtime_ns},'{sha256(archivo)}')")


subprocess.run([sys.executable, str(RAIZ / "crear_cbz.py"),
                str(HOST_LIBRARY_DIR / "fixture")], check=True)
for carpeta, nombre in (("serie-a6-uno", "ARCHIVO-A.cbz"), ("serie-a6-dos", "ARCHIVO-B.cbz")):
    destino = HOST_LIBRARY_DIR / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nombre).write_bytes((HOST_LIBRARY_DIR / "fixture" / nombre).read_bytes())

raices = subprocess.run(
    ["docker", "compose", "-f", COMPOSE, "--env-file", ENV_FILE, "exec", "-T",
     "postgres", "psql", "-U", DB_USER, "-d", DB_NAME, "-At",
     "-c", "select id from library_roots where is_default"],
    text=True, check=True, capture_output=True,
).stdout.strip()
assert raices, "No hay raíz de biblioteca por defecto"
root_id = raices.splitlines()[0]

sql = f"""BEGIN;
UPDATE library_roots SET path='{LIBRARY_PATH}' WHERE id='{root_id}';
DELETE FROM files WHERE id IN ('{UUID_F1}','{UUID_F2}');
DELETE FROM issues WHERE id IN ('{UUID_I1}','{UUID_I2}');
DELETE FROM series WHERE id IN ('{UUID_S1}','{UUID_S2}');
INSERT INTO series (id,title,tradition,kind,wishlist_policy) VALUES
 ('{UUID_S1}','Serie A6 Uno','american','regular','ninguno'),
 ('{UUID_S2}','Serie A6 Dos','american','regular','ninguno');
INSERT INTO issues (id,series_id,issue_number,title) VALUES
 ('{UUID_I1}','{UUID_S1}','1','Numero uno'),
 ('{UUID_I2}','{UUID_S2}','1','Numero uno');
INSERT INTO files (id,issue_id,root_id,file_path,file_name,file_format,
                   file_size_bytes,file_mtime_ns,sha256_hash) VALUES
 {fila(UUID_F1, UUID_I1, HOST_LIBRARY_DIR / 'serie-a6-uno', 'ARCHIVO-A.cbz')},
 {fila(UUID_F2, UUID_I2, HOST_LIBRARY_DIR / 'serie-a6-dos', 'ARCHIVO-B.cbz')};
COMMIT;
"""
psql(sql)
print("semilla aplicada: 2 series, 2 números, 2 archivos")
