# ruff: noqa: E501
"""#334 — lo que VE la persona en `/estado` cuando la última copia de seguridad ha fallado.

`/estado` se pinta en el navegador: el servidor sirve el esqueleto y un `<script>` en línea convierte el JSON de
`/api/health` en filas y avisos. Por eso `test_health.py::test_estado_pinta_la_fila_de_copias` (que solo busca cadenas
en la plantilla) no acredita lo que se ve. Aquí se enlaza el recorrido entero: el fichero de estado que escribe
`backup.sh` → `/api/health` real → el script REAL de la página, ejecutado con Node sobre un DOM mínimo → el texto que
queda visible y el que queda plegado en «Detalle técnico».

Requiere `node` (viene en los runners de GitHub); sin él se salta y NO cuenta como pasada.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.api.health import _BACKUP_ERRORES
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="requiere node para ejecutar el script de /estado")

#: El DOM mínimo que usa el script de la página. `textContent` y `innerHTML` se guardan tal cual; `append*` apila hijos.
CONTROLADOR_NODE = r"""
const vm = require("vm");
const DATA = JSON.parse(process.env.HEALTH_JSON);
class El {
  constructor(tag) { this.tag = tag; this.className = ""; this._text = ""; this._html = ""; this.children = [];
                     this.classList = { add() {}, remove() {} }; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text; }
  set innerHTML(v) { this._html = String(v); this.children = []; }
  get innerHTML() { return this._html; }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.children.push(c)); }
}
const porId = {};
global.document = {
  getElementById: (id) => (porId[id] = porId[id] || new El(id)),
  createElement: (tag) => new El(tag),
};
global.fetch = async () => ({ json: async () => DATA });
global.setInterval = () => 0;
vm.runInThisContext(process.env.SCRIPT_PAGINA);
setTimeout(() => {
  const g = (id) => porId[id];
  console.log(JSON.stringify({
    etiqueta: g("summary-label")._text, detalle: g("summary-detail")._text, punto: g("summary-dot").className,
    filas: g("checks").children.map((r) => r._html),
    avisos: g("warnings-list").children.map((li) => ({
      visible: li._text,
      plegado: li.children.filter((c) => c.tag === "details").map((d) => ({ resumen: d.children[0]._text, detalle: d.children[1]._text })),
    })),
  }));
}, 30);
"""

#: Lo que NO puede aparecer a la vista: nombres de programas, códigos internos del script y del registro.
JERGA = ("pg_dump", "gzip", "alembic", "sha256", "manifest", ".sql", "_failed", "_invalid", "_missing", "_distinto",
         "unexpected", "traceback", "undefined", "null", "none")


class _SesionFalsa:
    async def execute(self, _sentencia):
        return None

    async def rollback(self):
        return None


def _sin_html(fragmento: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragmento)).strip()


def _pedir_la_pagina(tmp_path, monkeypatch, codigo: str) -> dict:
    """Lo que dibuja el script de `/estado` cuando `backup.sh` dejó `status=failed` con ese código de error."""
    fichero = tmp_path / "status.json"
    fichero.write_text(json.dumps({"status": "failed", "error": codigo, "last_success_at_epoch": time.time()}),
                       encoding="utf-8")
    vpn, restauracion = tmp_path / "vpn.json", tmp_path / "restore-status.json"      # lo demás, sano y reciente
    vpn.write_text(json.dumps({"updated_at_epoch": time.time(), "vpn_active": True, "interface": "wg0"}), encoding="utf-8")
    restauracion.write_text(json.dumps({"status": "ok", "error": None, "last_ok_at_epoch": time.time()}), encoding="utf-8")
    ajustes = get_settings()
    monkeypatch.setattr(ajustes, "backup_status_file", str(fichero))
    monkeypatch.setattr(ajustes, "vpn_state_file", str(vpn))
    monkeypatch.setattr(ajustes, "restore_status_file", str(restauracion))
    monkeypatch.setattr(ajustes, "transmission_enabled", True)
    monkeypatch.setattr(ajustes, "amule_enabled", True)

    async def _get_db():
        yield _SesionFalsa()

    app.dependency_overrides[get_db] = _get_db
    try:
        with (
            patch("zascarr.api.health._check_transmission", AsyncMock(return_value=True)),
            patch("zascarr.api.health._check_amule", AsyncMock(return_value=True)),
            patch("zascarr.api.health._database_status", AsyncMock(return_value=("ok", "Conectada y migrada."))),
        ):
            cliente = TestClient(app)
            salud = cliente.get("/api/health").json()
            pagina = cliente.get("/estado")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert pagina.status_code == 200
    guiones = re.findall(r"<script>(.*?)</script>", pagina.text, re.S)
    script = next(s for s in guiones if "function renderHealth" in s)
    ejecucion = subprocess.run(
        ["node", "-e", CONTROLADOR_NODE], capture_output=True, text=True, timeout=30, check=False,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HEALTH_JSON": json.dumps(salud), "SCRIPT_PAGINA": script},
    )
    assert ejecucion.returncode == 0, ejecucion.stderr
    return {"salud": salud, "dibujo": json.loads(ejecucion.stdout)}


@pytest.mark.parametrize("codigo", [*sorted(_BACKUP_ERRORES), "codigo_nuevo_sin_traducir"])
def test_una_copia_fallida_se_ve_en_llano_y_lo_tecnico_va_plegado(tmp_path, monkeypatch, codigo):
    r = _pedir_la_pagina(tmp_path, monkeypatch, codigo)
    salud, dibujo = r["salud"], r["dibujo"]
    assert salud["checks"]["backup"] == "error"            # lo que la API entrega...

    # ...y lo que la persona ve: el resumen, la fila de copias en rojo y el resto sin tocar.
    assert dibujo["etiqueta"] == "Atención" and "estado-warn" in dibujo["punto"]
    assert dibujo["detalle"] == "Copias de seguridad"
    filas = {re.search(r'estado-check-name">(.*?)<', f).group(1): f for f in dibujo["filas"]}
    copias = filas["Copias de seguridad"]
    assert "estado-bad" in copias and _sin_html(copias) == "Copias de seguridad La última copia falló"
    assert _sin_html(filas["Base de datos"]) == "Base de datos Funciona"

    # El aviso visible es una frase llana con qué hacer; el texto de la API, tal cual, queda plegado.
    assert len(dibujo["avisos"]) == 1
    aviso = dibujo["avisos"][0]
    assert aviso["visible"] == "La copia de seguridad tiene un problema: revisa el aviso técnico y el disco de respaldo."
    assert aviso["plegado"] == [{"resumen": "Detalle técnico", "detalle": salud["warnings"]["backup"]}]
    assert salud["warnings"]["backup"].startswith("La última copia falló: ")

    # Nada técnico a la vista: resumen, filas y frase del aviso (lo plegado, «Detalle técnico», sí puede serlo).
    a_la_vista = " ".join([dibujo["etiqueta"], dibujo["detalle"], *(_sin_html(f) for f in dibujo["filas"]), aviso["visible"]])
    hallados = [j for j in JERGA if j in a_la_vista.lower()]
    assert hallados == [], f"jerga a la vista: {hallados} en «{a_la_vista}»"
