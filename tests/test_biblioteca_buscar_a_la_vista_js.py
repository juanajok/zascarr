# ruff: noqa: E501
"""UXA-08c (#1214): tras «Buscar», los resultados se desplazan a la vista (`biblioteca-filtros.js`).

Un DOM mínimo en Node. Solo se desplaza cuando la búsqueda se envía y la lista empieza bajo el pliegue;
un cambio de filtro o de orden no mueve la página; una búsqueda que acaba mal no deja la marca puesta."""
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
const escuchas = {};
let top = 900;
const llamadas = [];
const rejilla = {
  getBoundingClientRect: () => ({ top }),
  scrollIntoView: (o) => llamadas.push(o),
  setAttribute() {}, removeAttribute() {}, dataset: {},
};
const formulario = { addEventListener: (t, f) => { escuchas["form:" + t] = f; } };
const elementos = { filtros: formulario, rejilla };
let reducido = false;
const documento = {
  getElementById: (id) => elementos[id] || null,
  querySelector: (s) => (s === "#rejilla" ? rejilla : null),
  addEventListener: (t, f) => { escuchas[t] = f; },
  body: { addEventListener() {} },
  documentElement: { clientHeight: 640 },
};
vm.runInContext(js, vm.createContext({ document: documento, console, Element: class {},
  window: { htmx: { ajax() {} }, innerHeight: 640, addEventListener() {},
            matchMedia: () => ({ matches: reducido }) } }));
const ctx = { target: rejilla, request: { action: "/x" }, response: { status: 200 } };
const otro = { target: {}, request: { action: "/y" }, response: { status: 200 } };
const salida = {};
const n = () => llamadas.length;

// 1. Búsqueda enviada y la lista bajo el pliegue: se desplaza, al principio, con animación.
escuchas["form:submit"]();
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.desplazaUnaVez = n() === 1 && llamadas[0].block === "start" && llamadas[0].behavior === "smooth";
escuchas["htmx:finally:request"]({ detail: { ctx } });

// 2. Un cambio de filtro u orden (sin enviar la búsqueda) no mueve la página.
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.cambioDeFiltroNoDesplaza = n() === 1;

// 3. La lista ya se ve: no se desplaza.
top = 200;
escuchas["form:submit"]();
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.yaVisibleNoDesplaza = n() === 1;
escuchas["htmx:finally:request"]({ detail: { ctx } });

// 4. Movimiento reducido: sin animación.
top = 900; reducido = true;
escuchas["form:submit"]();
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.movimientoReducido = n() === 2 && llamadas[1].behavior === "auto";
escuchas["htmx:finally:request"]({ detail: { ctx } });
reducido = false;

// 5. Un intercambio de otro destino no cuenta ni gasta la marca.
escuchas["form:submit"]();
escuchas["htmx:after:swap"]({ detail: { ctx: otro } });
salida.otroDestinoNoDesplaza = n() === 2;
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.luegoSiDesplaza = n() === 3;
escuchas["htmx:finally:request"]({ detail: { ctx } });

// 6. Una búsqueda que acaba sin intercambio (error o cancelada) no deja la marca para el siguiente filtro.
escuchas["form:submit"]();
escuchas["htmx:finally:request"]({ detail: { ctx } });
escuchas["htmx:after:swap"]({ detail: { ctx } });
salida.busquedaFallidaNoArrastra = n() === 3;
console.log(JSON.stringify(salida));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_tras_buscar_los_resultados_se_desplazan_a_la_vista(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida == {
        "desplazaUnaVez": True,
        "cambioDeFiltroNoDesplaza": True,
        "yaVisibleNoDesplaza": True,
        "movimientoReducido": True,
        "otroDestinoNoDesplaza": True,
        "luegoSiDesplaza": True,
        "busquedaFallidaNoArrastra": True,
    }


def test_el_resultado_no_queda_pegado_al_borde():
    css = (JS.parent / "web.css").read_text(encoding="utf-8")
    assert "#rejilla { scroll-margin-top: var(--space-3); }" in css
