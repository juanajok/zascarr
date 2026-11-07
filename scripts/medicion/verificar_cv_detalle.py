#!/usr/bin/env python3
"""Verificación real del detalle de Comic Vine (#465, PR-3) — una sola pasada.

Carga los Ajustes de `runtime_settings` (la clave de Comic Vine vive ahí, ADR 0013), hace
como máximo DOS peticiones —volumen y número— por `ComicVineClient` (que pasa por
`pedir_con_cortesia`, 1,0 s) y escribe un JSON saneado por pantalla y otro listo para
fixture. Nunca imprime la clave, URLs ni query.

Uso:
  python scripts/medicion/verificar_cv_detalle.py --volume 31306 \\
      --salida docs/design/fixtures-cobertura/comicvine_volume_31306_real.json

Sin fila de Ajustes o sin `comicvine_api_key`: exit 2 y **cero peticiones**.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zascarr.config import get_settings
from zascarr.services.comic_vine import ComicVineClient

SALIDA_POR_DEFECTO = "docs/design/fixtures-cobertura/comicvine_volume_{volume}_real.json"


def _url_asyncpg() -> str | None:
    """`DATABASE_URL` en el formato que acepta asyncpg (sin `+asyncpg`)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _leer_ajustes() -> dict[str, Any] | None:
    """Lee SOLO la fila `runtime_settings` (id=1), sin crearla ni escribir."""
    url = _url_asyncpg()
    if not url:
        return None
    import asyncpg

    conexion = await asyncpg.connect(url)
    try:
        fila = await conexion.fetchrow(
            "SELECT values FROM runtime_settings WHERE id = 1")
    finally:
        await conexion.close()
    if fila is None:
        return None
    valores = fila["values"]
    if isinstance(valores, str):
        valores = json.loads(valores)
    return dict(valores) if isinstance(valores, dict) else None


async def cargar_ajustes() -> bool:
    """Aplica los overrides de Ajustes a `get_settings()`; False si no hay fila/BD."""
    try:
        valores = await _leer_ajustes()
    except Exception:  # noqa: BLE001 — sin BD se informa y se sale sin red
        return False
    if not valores:
        return False
    from zascarr.services.runtime_settings import apply_overrides
    apply_overrides(valores)
    return True


def _publisher_saneado(volumen: Any) -> Any:
    """Nombre de editorial si el cliente lo resolvió; si no, su id del raw (nunca URL)."""
    if getattr(volumen, "publisher", None):
        return volumen.publisher
    raw = getattr(volumen, "raw", None) or {}
    publisher = raw.get("publisher")
    if isinstance(publisher, dict):
        if publisher.get("name"):
            return publisher["name"]
        if publisher.get("id") is not None:
            return publisher["id"]
    return None


def _issue_saneado(issue: Any) -> dict[str, Any] | None:
    if issue is None:
        return None
    return {"id": getattr(issue, "cv_id", None),
            "issue_number": getattr(issue, "issue_number", None),
            "cover_date": getattr(issue, "cover_date", None)}


def _volumen_saneado(volumen: Any) -> dict[str, Any]:
    first = getattr(volumen, "first_issue", None)
    last = getattr(volumen, "last_issue", None)

    def _ref(valor: Any) -> dict[str, Any] | None:
        if not isinstance(valor, dict):
            return None
        return {"id": valor.get("id"), "issue_number": valor.get("issue_number")}

    return {
        "id": getattr(volumen, "cv_id", None),
        "name": getattr(volumen, "name", None),
        "publisher": _publisher_saneado(volumen),
        "start_year": getattr(volumen, "start_year", None),
        "count_of_issues": getattr(volumen, "count_of_issues", None),
        "first_issue": _ref(first),
        "last_issue": _ref(last),
    }


def _fixture(volumen: dict[str, Any], issue: dict[str, Any] | None,
             *, estado: str, sha_ejecutor: str) -> dict[str, Any]:
    capturado = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        "_fixture": "REAL capturada con scripts/medicion/verificar_cv_detalle.py",
        "capturado": {"fecha": capturado, "sha_ejecutor": sha_ejecutor},
        "estado": estado,
        **volumen,
        "issue": issue,
    }


async def verificar(volume_id: int, issue_id: int | None, *,
                    cliente_factory=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Hace las peticiones y devuelve (salida_saneada, fixture). Sin clave no llega aquí."""
    cliente_cls = cliente_factory or ComicVineClient
    async with cliente_cls() as cliente:
        volumen = await cliente.get_volume(volume_id)
        if volumen is None:
            return ({"estado": "sin_resultados", "volume": None, "issue": None},
                    {"estado": "sin_resultados", "volume": None, "issue": None})
        volumen_datos = _volumen_saneado(volumen)
        # Si no se pasó --issue, se usa el first_issue del volumen (sin petición extra).
        if issue_id is None:
            first = getattr(volumen, "first_issue", None)
            if isinstance(first, dict):
                issue_id = first.get("id")
        issue = await cliente.get_issue(int(issue_id)) if issue_id is not None else None
        issue_datos = _issue_saneado(issue)
        estado = "ok" if issue_datos is not None or issue_id is None else "sin_resultados_issue"
        salida = {"estado": estado, "volume": volumen_datos, "issue": issue_datos}
        fixture = _fixture(volumen_datos, issue_datos, estado=estado,
                           sha_ejecutor="no_disponible")
        return salida, fixture


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verificación real de /volume/ y /issue/ de Comic Vine (máx. 2 peticiones).")
    parser.add_argument("--volume", type=int, default=31306,
                        help="id de volumen Comic Vine (por defecto 31306, BOLA DE DRAC)")
    parser.add_argument("--issue", type=int, default=None,
                        help="id de número; por defecto, el first_issue del volumen")
    parser.add_argument("--salida", default=None,
                        help="JSON listo para fixture; por defecto docs/design/fixtures-cobertura/")
    parser.add_argument("--sha-ejecutor", default="no_disponible",
                        help="SHA del árbol ejecutor (explícito)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, cliente_factory=None) -> int:
    args = _argumentos(argv)
    salida_path = Path(args.salida or SALIDA_POR_DEFECTO.format(volume=args.volume))
    if not asyncio.run(cargar_ajustes()):
        print(json.dumps({"estado": "sin_ajustes_o_sin_clave",
                          "detalle": "No hay fila de Ajustes utilizable."},
                         ensure_ascii=False))
        print("FAIL  sin Ajustes/Comic Vine; no se envía ninguna petición.", file=sys.stderr)
        return 2
    if not get_settings().comicvine_api_key:
        print(json.dumps({"estado": "sin_clave",
                          "detalle": "comicvine_api_key vacía en Ajustes."},
                         ensure_ascii=False))
        print("FAIL  falta comicvine_api_key; no se envía ninguna petición.", file=sys.stderr)
        return 2
    try:
        salida, fixture = asyncio.run(verificar(
            args.volume, args.issue, cliente_factory=cliente_factory))
    except Exception as exc:  # noqa: BLE001 — se informa sin volcar clave/URL
        # La traza va a stderr (local, para diagnosticar); el JSON sigue saneado.
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"estado": "error", "detalle": type(exc).__name__},
                         ensure_ascii=False))
        return 1
    # La fixture debe llevar el SHA explícito; se reescribe el campo capturado.
    capturado = fixture.setdefault("capturado", {})
    capturado["sha_ejecutor"] = args.sha_ejecutor
    capturado.setdefault("fecha", datetime.now(UTC).isoformat(timespec="seconds"))
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    salida_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"fixture: {salida_path}", file=sys.stderr)
    return 0 if salida["estado"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
