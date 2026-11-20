#!/usr/bin/env python3
"""Arnés de host sin privilegios para la puerta OPS4 (#443).

No instala ni inicia unidades, no usa Docker, sudo, systemd, red ni la base de
datos. Solo importa el auxiliar existente y comprueba que una petición de
actualización no llega a ningún lanzador.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import tempfile
from pathlib import Path

REPO = Path("/opt/zascarr/zascarr")
OPS_PATH = REPO / "deploy" / "ops" / "zascarr_ops.py"
CLAVE = bytes(range(32))
AHORA = 1_800_000_000
ID = "a" * 32


def cargar():
    spec = importlib.util.spec_from_file_location("zascarr_ops_arnes", OPS_PATH)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


class LanzadorProhibido:
    def __getattr__(self, nombre):
        raise AssertionError(f"el gate llamó al lanzador: {nombre}")


def linea(cuerpo: dict) -> bytes:
    return json.dumps(cuerpo, separators=(",", ":")).encode() + b"\n"


def firma(texto: str) -> str:
    return hmac.new(CLAVE, texto.encode(), hashlib.sha256).hexdigest()


def main() -> None:
    assert os.geteuid() != 0, "el arnés no debe ejecutarse como root"
    ops = cargar()
    assert "actualizar" not in ops.UNIDADES
    with tempfile.TemporaryDirectory(prefix="ops4-", dir=os.environ["OPS4_TMP"]) as tmp:
        base = Path(tmp)
        run, status = base / "run", base / "status"
        run.mkdir()
        status.mkdir()
        estado = ops.EstadoOps(str(run), str(status))

        def prohibido(*_a, **_k):
            raise AssertionError("se intentó lanzar un subproceso")

        ops.subprocess.run = prohibido
        casos = []
        cuerpo = {"v": 1, "id": ID, "accion": "actualizar", "creada": AHORA,
                  "firma": firma(f"1|{ID}|actualizar|{AHORA}")}
        respuesta = ops.procesar(linea(cuerpo), AHORA, CLAVE, estado,
                                 LanzadorProhibido(), copias=[])
        casos.append(("v1_actualizar", respuesta.resultado, respuesta.codigo))
        assert respuesta.resultado == "rechazada"
        assert respuesta.codigo == "accion_no_disponible"

        ambiguo = (b'{"v":1,"id":"' + ID.encode() + b'","accion":"actualizar",'
                   b'"creada":1800000000,"firma":"' + b"f" * 64 + b'",'
                   b'"firma":"' + b"f" * 64 + b'"}\n')
        respuesta = ops.procesar(ambiguo, AHORA, CLAVE, estado,
                                 LanzadorProhibido(), copias=[])
        casos.append(("duplicado", respuesta.resultado, respuesta.codigo))
        assert respuesta.codigo == "esquema_invalido"

        v2 = {"v": 2, "id": ID, "accion": "actualizar", "copia": "backup-20260101_120000",
              "prueba": "secreta", "creada": AHORA, "firma": "f" * 64}
        respuesta = ops.procesar(linea(v2), AHORA, CLAVE, estado,
                                 LanzadorProhibido(), copias=[])
        casos.append(("v2_actualizar", respuesta.resultado, respuesta.codigo))
        assert respuesta.codigo == "esquema_invalido"

        print(json.dumps({
            "uid": os.geteuid(), "root": False, "unidades": sorted(ops.UNIDADES),
            "casos": casos, "estado_escrito": sorted(p.name for p in base.rglob("*")),
        }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
