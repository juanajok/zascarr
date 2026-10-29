#!/usr/bin/env python3
"""Genera el fixture reproducible de 123a-i (4 series, 6 números, 40 archivos).

No usa datos reales ni una base de datos por defecto. Escribe:

  <salida>/biblioteca/             38 ficheros sintéticos (2 filas son missing)
  <salida>/seed.sql                SQL de siembra (0600; contiene el secreto)
  <salida>/token.txt               token de la operación completada (0600)
  <salida>/secret_key.txt          secreto sintético del fixture (0600)
  <salida>/resumen.json            recuentos, tamaños y hashes (sin secretos)

La salvaguarda es obligatoria: `ZASCARR_ENTORNO=123a`. Sin ella no se escribe
nada. `--reset` borra un fixture anterior reconocido por `.fixture-123a`.

Con `--aplicar --database-url <url>` comprueba que la BD aislada está vacía
(salvo `--force` o `--reset`) y ejecuta `seed.sql` con `psql`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from zascarr.services.tokens_revision import (  # noqa: E402
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token_vinculacion,
)

MARCADOR = ".fixture-123a"
PREFIJO_CONTENEDOR = "/media/library"


def _png() -> bytes:
    def chunk(tipo: bytes, datos: bytes) -> bytes:
        cuerpo = struct.pack(">I", len(datos)) + tipo + datos
        return cuerpo + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def _cbz(nombre: str) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pagina.png", _png())
        z.writestr("sintetico.txt", f"{nombre}\n")
    return salida.getvalue()


def _cbr(nombre: str, *, zip_en_cbr: bool) -> bytes:
    if zip_en_cbr:
        return _cbz(nombre)
    return b"Rar!\x1a\x07\x00" + f"{nombre}\n".encode()


def _cb7(nombre: str) -> bytes:
    return b"7z\xbc\xaf\x27\x1c" + f"{nombre}\n".encode()


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _q(valor) -> str:
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def _json(valor) -> str:
    return _q(json.dumps(valor, ensure_ascii=False)) + "::jsonb"


def _fecha_iso(dt: datetime) -> str:
    return dt.isoformat()


def _resumen_documento(
    *,
    series,
    issues,
    files,
    ops,
    wishlist,
    ficheros,
    token_sha,
    secreto_sha,
) -> dict:
    return {
        "entorno": "123a",
        "series": series,
        "issues": issues,
        "files": files,
        "files_por_formato": {"cbz": 30, "cbr": 9, "cb7": 1},
        "con_issue": 24,
        "sin_issue": 16,
        "is_missing": 2,
        "sin_sha256": 1,
        "con_formato_contenido": 1,
        "vinculacion_operaciones": ops,
        "wishlist": wishlist,
        "ficheros_en_disco": len(ficheros),
        "bytes_biblioteca": sum(f["bytes"] for f in ficheros),
        "token_sha256": token_sha,
        "secret_key_sha256": secreto_sha,
        "ficheros": ficheros,
    }


def _comprobar_salida(salida: Path, *, reset: bool) -> None:
    if salida.exists() and not salida.is_dir():
        raise SystemExit("ERROR: --salida existe y no es un directorio.")
    if salida.exists() and any(salida.iterdir()):
        if not reset:
            raise SystemExit(
                "ERROR: el directorio de salida ya existe. Usa --reset para "
                "regenerar un fixture de 123a."
            )
        if not (salida / MARCADOR).exists():
            raise SystemExit("ERROR: el directorio no parece un fixture de 123a; no lo borro.")
        shutil.rmtree(salida)


def _url_psql_aislada(url: str) -> str:
    """Convierte la URL a la que entiende psql y exige el puerto aislado.

    No es la compuerta de aislamiento (esa es `verificar_aislamiento_123a.sh`):
    es una guardia barata contra el error humano de apuntar `--aplicar` a
    producción. Sin host y puerto explícitos no se escribe nada.
    """
    try:
        parsed = urlparse(url)
        puerto = parsed.port
    except ValueError as exc:
        raise SystemExit(f"ERROR: URL de base de datos inválida: {exc}") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        raise SystemExit(
            "ERROR: --database-url debe empezar por postgresql:// o postgresql+asyncpg://."
        )
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(
            "ERROR: --aplicar solo puede escribir en la BD aislada local "
            "(127.0.0.1, localhost o ::1). No se escribe nada."
        )
    if puerto != 15432:
        raise SystemExit(
            "ERROR: --aplicar exige el puerto aislado 15432; la URL no lo declara "
            "o usa otro puerto. No se escribe nada."
        )
    if parsed.scheme == "postgresql+asyncpg":
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _psql(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _aplicar(url: str, seed: Path, resumen: dict, *, reset: bool, force: bool) -> None:
    if not shutil.which("psql"):
        raise SystemExit("ERROR: --aplicar necesita el cliente psql.")
    tablas = _psql(
        url,
        "-At",
        "-c",
        "select count(*) from information_schema.tables where table_schema='public' "
        "and table_name in ('series','issues','files','vinculacion_operaciones','wishlist');",
    )
    if tablas.returncode != 0:
        raise SystemExit("ERROR: no pude consultar la BD aislada. No aplico el fixture.")
    if tablas.stdout.strip() != "5":
        raise SystemExit(
            "ERROR: faltan tablas de ZascArr en la BD. Aplica `alembic upgrade head` "
            "antes de --aplicar."
        )
    if not reset:
        cuenta = _psql(
            url,
            "-At",
            "-c",
            "select (select count(*) from series)+(select count(*) from issues)"
            "+(select count(*) from files)+(select count(*) from vinculacion_operaciones)"
            "+(select count(*) from wishlist);",
        )
        if cuenta.returncode != 0:
            raise SystemExit("ERROR: no pude comprobar si la BD está vacía.")
        if int(cuenta.stdout.strip() or "0") > 0 and not force:
            raise SystemExit("ERROR: la BD aislada no está vacía. Usa --reset o --force explícito.")
    if reset:
        limpiar = _psql(
            url,
            "-c",
            "TRUNCATE TABLE files, issues, series, vinculacion_operaciones, wishlist, "
            "runtime_settings RESTART IDENTITY CASCADE;",
        )
        if limpiar.returncode != 0:
            raise SystemExit("ERROR: no pude limpiar el fixture anterior.")
    aplicado = _psql(url, "-f", str(seed))
    if aplicado.returncode != 0:
        raise SystemExit("ERROR: psql no pudo aplicar seed.sql.")
    verificado = _psql(
        url,
        "-At",
        "-c",
        "select (select count(*) from series)||'|'||(select count(*) from issues)||'|'"
        "||(select count(*) from files)||'|'||(select count(*) from vinculacion_operaciones)"
        "||'|'||(select count(*) from wishlist);",
    )
    esperado = (
        f"{resumen['series']}|{resumen['issues']}|{resumen['files']}|"
        f"{resumen['vinculacion_operaciones']}|{resumen['wishlist']['total']}"
    )
    if verificado.returncode != 0 or verificado.stdout.strip() != esperado:
        raise SystemExit("ERROR: los recuentos aplicados no coinciden con el fixture.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el fixture sintético de 123a-i.")
    parser.add_argument("--salida", required=True, type=Path, help="directorio de salida")
    parser.add_argument("--reset", action="store_true", help="borra un fixture 123a anterior")
    parser.add_argument("--force", action="store_true", help="permite aplicar sobre BD no vacía")
    parser.add_argument("--aplicar", action="store_true", help="aplica seed.sql con psql")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()

    if os.environ.get("ZASCARR_ENTORNO") != "123a":
        parser.error("ZASCARR_ENTORNO debe ser exactamente '123a'.")
    if args.aplicar and not args.database_url:
        parser.error("--aplicar requiere --database-url o DATABASE_URL.")
    url_psql = ""
    if args.aplicar:
        url_psql = _url_psql_aislada(args.database_url)

    _comprobar_salida(args.salida, reset=args.reset)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / MARCADOR).write_text("1\n", encoding="utf-8")

    biblioteca = args.salida / "biblioteca"
    biblioteca.mkdir()

    secreto = secrets.token_hex(32)
    ahora = datetime.now(UTC)
    token_hasta = ahora + timedelta(minutes=15)

    series_ids = {n: _uuid(n) for n in range(1, 5)}
    # El detalle aprobado suma 5 números (S1:1,3; S2:1; S3:1,2; S4:0),
    # pero el recuento cerrado es 6. Se añade S2 #2 para respetar el 6.
    issue_defs = [
        (1, 1, "1"),
        (2, 1, "3"),
        (3, 2, "1"),
        (4, 2, "2"),
        (5, 3, "1"),
        (6, 3, "2"),
    ]
    issue_ids = {n: _uuid(100 + n) for n in range(1, 7)}

    formatos = ["cbz"] * 30 + ["cbr"] * 9 + ["cb7"]
    faltantes = {29, 30}
    sin_hash = 38
    con_formato = 31
    ficheros: list[dict] = []
    files_sql: list[str] = []

    for n, formato in enumerate(formatos, start=1):
        nombre = f"sintetico_{n:03d}.{formato}"
        ruta = biblioteca / nombre
        ruta_contenedor = f"{PREFIJO_CONTENEDOR}/{nombre}"
        issue_id = issue_ids[((n - 1) % 6) + 1] if n <= 24 else None
        if n in faltantes:
            contenido = None
            tamano = 12_000 + n
            sha = hashlib.sha256(f"missing-{n}".encode()).hexdigest()
            is_missing = True
            missing_since = _fecha_iso(ahora)
        else:
            if formato == "cbz":
                contenido = _cbz(nombre)
            elif formato == "cbr":
                contenido = _cbr(nombre, zip_en_cbr=(n == con_formato))
            else:
                contenido = _cb7(nombre)
            ruta.write_bytes(contenido)
            tamano = len(contenido)
            sha = None if n == sin_hash else hashlib.sha256(contenido).hexdigest()
            is_missing = False
            missing_since = None
            ficheros.append(
                {
                    "nombre": nombre,
                    "bytes": tamano,
                    "sha256": hashlib.sha256(contenido).hexdigest(),
                }
            )

        metadata = {}
        if n == con_formato:
            metadata = {"formato_contenido": {"firma": "zip", "contrato": 1, "clase": "tebeo"}}
        files_sql.append(
            "INSERT INTO files (id, issue_id, file_path, file_name, file_format, "
            "file_size_bytes, sha256_hash, metadata, is_missing, missing_since) VALUES ("
            f"{_q(_uuid(1000 + n))}, {_q(issue_id)}, {_q(ruta_contenedor)}, {_q(nombre)}, "
            f"{_q(formato)}, {_q(tamano)}, {_q(sha)}, {_json(metadata)}, "
            f"{_q(is_missing)}, {_q(missing_since)});"
        )

    # Operación completada: token firmado con el secreto del fixture.
    archivo_1 = biblioteca / "sintetico_001.cbz"
    archivo_1_stat = archivo_1.stat()
    firmado = VinculacionFirmada(
        clave=f"{PREFIJO_CONTENEDOR}/sintetico_001.cbz",
        series_id=series_ids[1],
        operacion=_uuid(101),
        archivos=(
            ArchivoFirmado(
                id=_uuid(1001),
                numero="1",
                formato="single_issue",
                tamano=archivo_1_stat.st_size,
                mtime_ns=archivo_1_stat.st_mtime_ns,
                conflictos=(),
            ),
        ),
    )
    token = crear_token_vinculacion(firmado, secreto)
    (args.salida / "token.txt").write_text(token + "\n", encoding="utf-8")
    (args.salida / "secret_key.txt").write_text(secreto + "\n", encoding="utf-8")

    def doc(op_id: str, estado: str, motivo: str | None, global_: str) -> dict:
        return {
            "version": 1,
            "operacion_id": op_id,
            "serie_id": series_ids[1],
            "fecha": _fecha_iso(ahora),
            "global": global_,
            "totales": {
                "vinculados": 1 if estado == "vinculado" else 0,
                "ya_estaban": 0,
                "omitidos": 1 if estado == "omitido" else 0,
                "issues_creados": 0,
                "con_conflicto_incluidos": 0,
            },
            "archivos": [
                {
                    "id": _uuid(1001),
                    "estado": estado,
                    "motivo": motivo,
                    "numero": "1",
                    "formato": "single_issue",
                    "issue_creado": False,
                    "conflictos": [],
                }
            ],
        }

    ops_sql = [
        "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta) "
        f"VALUES ({_q(_uuid(101))}, {_q(series_ids[1])}, "
        f"{_json(doc(_uuid(101), 'vinculado', None, 'vinculados_todos'))}, "
        f"{_q(_fecha_iso(token_hasta))});",
        "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta) "
        f"VALUES ({_q(_uuid(102))}, {_q(series_ids[1])}, "
        f"{_json(doc(_uuid(102), 'omitido', 'origen_no_encontrado', 'nada_vinculado'))}, "
        f"{_q(_fecha_iso(token_hasta))});",
        "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta) "
        f"VALUES ({_q(_uuid(103))}, {_q(series_ids[1])}, "
        f"{_json(doc(_uuid(103), 'omitido', 'en_curso', 'nada_vinculado'))}, "
        f"{_q(_fecha_iso(token_hasta))});",
    ]

    wishlist_sql = [
        "INSERT INTO wishlist (id, series_id, issue_id, status, priority, origen, numero) "
        f"VALUES ({_q(_uuid(201))}, {_q(series_ids[2])}, NULL, 'wanted', 5, 'manual', NULL);",
        "INSERT INTO wishlist (id, series_id, issue_id, status, priority, origen, numero) "
        f"VALUES ({_q(_uuid(202))}, {_q(series_ids[3])}, {_q(issue_ids[5])}, 'wanted', 5, "
        "'manual', 1);",
        "INSERT INTO wishlist (id, series_id, issue_id, status, priority, origen, numero) "
        f"VALUES ({_q(_uuid(203))}, {_q(series_ids[3])}, NULL, 'imported', 5, 'manual', NULL);",
    ]

    runtime = {
        "secret_key": secreto,
        "auth_mode": "none",
        "comicvine_enabled": False,
        "anilist_enabled": False,
        "tebeosfera_enabled": False,
        "gcd_enabled": False,
        "prowlarr_enabled": False,
        "transmission_enabled": False,
        "amule_enabled": False,
        "prowlarr_url": "",
        "transmission_url": "",
        "amule_url": "",
        "forum_enabled": False,
    }

    lineas = ["BEGIN;"]
    for n, sid in series_ids.items():
        lineas.append(
            "INSERT INTO series (id, title, sort_title, tradition, status, "
            "wishlist_policy, metadata, locked_fields) VALUES ("
            f"{_q(sid)}, {_q(f'Serie Sintética {n}')}, {_q(f'Serie Sintetica {n}')}, "
            "'american', 'ongoing', 'ninguno', '{}'::jsonb, ARRAY[]::varchar[]);"
        )
    for n, sid, numero in issue_defs:
        lineas.append(
            "INSERT INTO issues (id, series_id, issue_number, volume, title, format) VALUES ("
            f"{_q(issue_ids[n])}, {_q(series_ids[sid])}, {_q(numero)}, 1, "
            f"{_q(f'Número {numero}')}, 'single_issue');"
        )
    lineas += files_sql
    lineas += ops_sql
    lineas += wishlist_sql
    lineas.append(
        "INSERT INTO runtime_settings (id, values) VALUES (1, "
        f"{_json(runtime)}) ON CONFLICT (id) DO UPDATE SET values = EXCLUDED.values;"
    )
    lineas.append("COMMIT;")
    seed = args.salida / "seed.sql"
    seed.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    resumen = _resumen_documento(
        series=4,
        issues=6,
        files=40,
        ops=3,
        wishlist={"total": 3, "wanted": 2, "imported": 1},
        ficheros=sorted(ficheros, key=lambda f: f["nombre"]),
        token_sha=hashlib.sha256(token.encode()).hexdigest(),
        secreto_sha=hashlib.sha256(secreto.encode()).hexdigest(),
    )
    (args.salida / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for ruta in (seed, args.salida / "token.txt", args.salida / "secret_key.txt"):
        ruta.chmod(0o600)

    if args.aplicar:
        _aplicar(
            url_psql,
            seed,
            resumen,
            reset=args.reset,
            force=args.force,
        )

    print(
        "Fixture 123a generado: 4 series, 6 números, 40 archivos "
        f"({len(ficheros)} en disco), 3 operaciones y 3 wishlist."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
