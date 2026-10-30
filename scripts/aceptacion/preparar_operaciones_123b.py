#!/usr/bin/env python3
"""Sidecar de operaciones vivas/históricas para 123b sobre el fixture de 123a.

No crea series, números ni archivos nuevos: reutiliza el fixture 123a aplicado
en la base aislada y sus ficheros. Inserta:

  · 4 asignaciones: preparada, confirmada, limpiada y cancelada;
  · 2 altas: creada y deshecha;
  · 2 import_runs: uno limpio y otro con error.

La `confirmada` copia un archivo del fixture a `_123b/` y actualiza la fila
`files` para que la BD apunte al destino; la `preparada` deja el origen intacto.
No usa datos reales ni toca la biblioteca de producción.

Guardia: `ZASCARR_ENTORNO=123b` y URL local en el puerto aislado 15434.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

MARCA = "_123b"


def _error(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _url_aislada(url: str) -> str:
    try:
        p = urlparse(url)
        puerto = p.port
    except ValueError as exc:
        _error(f"URL inválida: {exc}")
    host = (p.hostname or "").lower()
    if p.scheme not in {"postgresql", "postgresql+asyncpg"}:
        _error("--database-url debe empezar por postgresql:// o postgresql+asyncpg://.")
    if host not in {"127.0.0.1", "localhost", "::1"} or puerto != 15434:
        _error("el sidecar solo escribe en la BD aislada local (127.0.0.1/localhost/::1:15434).")
    if p.scheme == "postgresql+asyncpg":
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _psql(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", *args], capture_output=True, text=True, timeout=120
    )


def _filas(url: str, sql: str) -> list[list[str]]:
    r = _psql(url, "-At", "-F", "|", "-c", sql)
    if r.returncode != 0:
        _error(f"consulta a la BD aislada falló: {r.stderr.strip()[:200]}")
    return [linea.split("|") for linea in r.stdout.splitlines() if linea]


def _q(valor: str | None) -> str:
    if valor is None:
        return "NULL"
    return "'" + valor.replace("'", "''") + "'"


def _json(valor) -> str:
    return _q(json.dumps(valor, ensure_ascii=False)) + "::jsonb"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aplicar(url: str, sql: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(sql)
        ruta = Path(f.name)
    try:
        r = _psql(url, "-f", str(ruta))
        if r.returncode != 0:
            _error(f"no se pudo aplicar el sidecar: {r.stderr.strip()[:300]}")
    finally:
        ruta.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operaciones 123b sobre el fixture 123a")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--biblioteca", required=True, type=Path)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if os.environ.get("ZASCARR_ENTORNO") != "123b":
        parser.error("ZASCARR_ENTORNO debe ser exactamente '123b'.")
    if not args.database_url:
        parser.error("--database-url o DATABASE_URL es obligatorio.")
    url = _url_aislada(args.database_url)
    if not args.biblioteca.is_dir():
        _error("--biblioteca no es un directorio.")
    if not shutil.which("psql"):
        _error("hace falta el cliente psql.")

    existentes = int(_filas(url, "select count(*) from asignacion_operaciones")[0][0])
    if existentes and not args.reset:
        _error("ya hay asignaciones; usa --reset para regenerar el sidecar 123b.")
    if args.reset:
        _aplicar(
            url,
            "DELETE FROM asignacion_operaciones; DELETE FROM alta_operaciones; "
            "DELETE FROM import_runs;",
        )
        shutil.rmtree(args.biblioteca / MARCA, ignore_errors=True)

    series = _filas(url, "select id, title from series order by title limit 2")
    if len(series) < 2:
        _error("el fixture 123a no tiene las 2 series mínimas.")
    s1 = series[0][0]

    filas = _filas(
        url,
        """
        select f.id, f.file_path, f.file_name, coalesce(f.file_size_bytes, 0),
               coalesce(f.sha256_hash, ''), coalesce(f.issue_id::text, ''),
               coalesce(i.series_id::text, ''), coalesce(i.issue_number, '')
        from files f left join issues i on i.id = f.issue_id
        order by f.file_name
    """,
    )
    con_issue = [f for f in filas if f[5]]
    sin_issue = [f for f in filas if not f[5]]
    if len(con_issue) < 2 or len(sin_issue) < 1:
        _error("el fixture 123a no tiene archivos suficientes para las operaciones.")

    def datos(fila: list[str]) -> tuple[Path, int, int, str]:
        nombre = fila[2]
        host = args.biblioteca / nombre
        if not host.is_file():
            # Si el nombre no está en la raíz, buscar por sufijo dentro de la biblioteca.
            encontrados = list(args.biblioteca.rglob(nombre))
            if len(encontrados) != 1:
                _error(f"no encuentro el archivo del fixture {nombre!r}.")
            host = encontrados[0]
        st = host.stat()
        sha = fila[4] or _sha(host)
        return host, st.st_size, st.st_mtime_ns, sha

    # Confirmada: copia el archivo al destino y deja la BD apuntando a él.
    origen_conf, size_conf, mtime_conf, sha_conf = datos(con_issue[0])
    conf_nombre = "confirmada.cbz"
    conf_dest_db = f"/media/library/{MARCA}/{conf_nombre}"
    conf_host = args.biblioteca / MARCA / conf_nombre
    conf_host.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen_conf, conf_host)
    if _sha(conf_host) != sha_conf:
        _error("la copia de la asignación confirmada no coincide.")

    # Preparada: origen intacto, destino libre.
    origen_prep, size_prep, mtime_prep, sha_prep = datos(sin_issue[0])
    prep_dest_db = f"/media/library/{MARCA}/preparada.cbz"

    altas = []
    for estado in ("creada", "deshecha"):
        altas.append(
            "INSERT INTO alta_operaciones (operacion_id, series_id, estado, token_hasta) "
            f"VALUES (gen_random_uuid(), {_q(s1)}, '{estado}', now() + interval '1 hour');"
        )

    ahora = datetime.now(UTC)
    historico = {
        "origen": f"/media/library/{MARCA}/historico-origen.cbz",
        "destino": f"/media/library/{MARCA}/historico-destino.cbz",
        "temporal": f"/media/library/{MARCA}/historico-temporal.cbz",
    }
    sql = ["BEGIN;"]
    sql.append(
        "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, "
        "temporal, size_bytes, mtime_ns, sha256, issue_number, formato) VALUES ("
        f"{_q(con_issue[0][0])}, {_q(con_issue[0][6])}, 'confirmada', "
        f"{_q(con_issue[0][1])}, {_q(conf_dest_db)}, {_q(conf_dest_db + '.part')}, "
        f"{size_conf}, {mtime_conf}, {_q(sha_conf)}, {_q(con_issue[0][7])}, 'single_issue');"
    )
    sql.append(
        "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, "
        "temporal, size_bytes, mtime_ns, sha256, issue_number, formato) VALUES ("
        f"{_q(sin_issue[0][0])}, {_q(s1)}, 'preparada', {_q(origen_prep)}, "
        f"{_q(prep_dest_db)}, {_q(prep_dest_db + '.part')}, {size_prep}, {mtime_prep}, "
        f"{_q(sha_prep)}, '2', 'single_issue');"
    )
    for estado in ("limpiada", "cancelada"):
        sql.append(
            "INSERT INTO asignacion_operaciones (estado, origen, destino, temporal, "
            "size_bytes, mtime_ns, sha256, issue_number, formato) VALUES ("
            f"'{estado}', {_q(historico['origen'])}, {_q(historico['destino'])}, "
            f"{_q(historico['temporal'])}, 1, 1, {_q('a' * 64)}, '1', 'single_issue');"
        )
    sql += altas
    inicio_ok = (ahora - timedelta(hours=2)).isoformat()
    fin_ok = (ahora - timedelta(hours=1, minutes=55)).isoformat()
    inicio_error = (ahora - timedelta(hours=1)).isoformat()
    fin_error = (ahora - timedelta(minutes=55)).isoformat()
    sql.append(
        "INSERT INTO import_runs (started_at, finished_at, files_scanned, imported_count, "
        "duplicate_count, unsorted_count, error_count, disappeared_count, details) VALUES ("
        f"{_q(inicio_ok)}, {_q(fin_ok)}, 0, 0, 0, 0, 0, 0, '{{}}'::jsonb);"
    )
    sql.append(
        "INSERT INTO import_runs (started_at, finished_at, files_scanned, imported_count, "
        "duplicate_count, unsorted_count, error_count, disappeared_count, details) VALUES ("
        f"{_q(inicio_error)}, {_q(fin_error)}, 1, 0, 0, 0, 1, 0, "
        f"{_json({'errors': ['fallo simulado: sin espacio en el disco']})});"
    )
    sql.append(
        f"UPDATE files SET file_path = {_q(conf_dest_db)}, file_name = {_q(conf_nombre)} "
        f"WHERE id = {_q(con_issue[0][0])};"
    )
    sql.append("COMMIT;")
    _aplicar(url, "\n".join(sql) + "\n")

    verificado = _filas(
        url,
        "select (select count(*) from asignacion_operaciones)||'|'||"
        "(select count(*) from alta_operaciones)||'|'||"
        "(select count(*) from import_runs)",
    )
    if verificado[0][0] != "4|2|2":
        _error(f"recuentos inesperados: {verificado[0][0]}")
    print("Sidecar 123b aplicado: 4 asignaciones, 2 altas y 2 import_runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
