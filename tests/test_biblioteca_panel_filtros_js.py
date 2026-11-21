# ruff: noqa: E501
"""UXA-08: cierre del panel «Filtros» de Biblioteca (`biblioteca-filtros.js`) con un DOM mínimo en Node.

«Cerrar filtros» cierra el panel y devuelve el foco al botón «Filtros»; Escape hace lo mismo; un clic dentro
del panel, en cambio, lo deja abierto."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static" / "biblioteca-filtros.js"

HARNESS = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
class Element {}
const escuchas = {};
let activo = null;
const boton = Object.assign(new Element(), { focus() { activo = this; }, getBoundingClientRect: () => ({ bottom: 0 }) });
const cerrar = Object.assign(new Element(), { closest(s) { return s === "[data-cerrar-filtros]" ? this : null; } });
const campo = Object.assign(new Element(), { closest() { return null; } });
const fuera = Object.assign(new Element(), { closest() { return null; } });
const panel = {
  open: true,
  querySelector(s) { return s === "summary" ? boton : null; },
  addEventListener() {},
  contains(e) { return e === cerrar || e === campo; },
};
const documento = {
  getElementById: (id) => (id === "panel-filtros" ? panel : null),
  addEventListener: (tipo, f) => { escuchas[tipo] = f; },
  body: { addEventListener() {} },
  get activeElement() { return activo; },
};
vm.runInContext(js, vm.createContext({ document: documento, Element, console,
  window: { matchMedia: () => ({ matches: false }), addEventListener() {} } }));
const salida = {};

// Un clic dentro del panel (en un campo) lo deja abierto.
escuchas.click({ target: campo });
salida.campoNoCierra = panel.open === true;

// «Cerrar filtros» cierra y devuelve el foco a «Filtros».
escuchas.click({ target: cerrar });
salida.cierraConBoton = panel.open === false;
salida.focoEnFiltros = activo === boton;

// Escape cierra y devuelve el foco; con el panel cerrado no hace nada.
panel.open = true; activo = null;
escuchas.keydown({ key: "Escape" });
salida.escapeCierra = panel.open === false && activo === boton;
activo = null;
escuchas.keydown({ key: "Escape" });
salida.escapeCerradoNoMueveFoco = activo === null;

// Un clic fuera sigue cerrando el panel (sin tocar el foco).
panel.open = true;
escuchas.click({ target: fuera });
salida.fueraCierra = panel.open === false;
console.log(JSON.stringify(salida));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_cerrar_filtros_cierra_el_panel_y_devuelve_el_foco(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida == {
        "campoNoCierra": True,
        "cierraConBoton": True,
        "focoEnFiltros": True,
        "escapeCierra": True,
        "escapeCerradoNoMueveFoco": True,
        "fueraCierra": True,
    }
