# ruff: noqa: E501
"""#1120: comportamiento de `biblioteca-filtros.js` ante un fallo de la petición que actualiza la rejilla,
con un DOM mínimo en Node (el mismo enfoque que `test_lector_js.py`)."""
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
let activo = null;
const rejilla = { dataset: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } };
const boton = { listeners: {}, disabled: false, textContent: "Reintentar",
  addEventListener(t, f) { this.listeners[t] = f; }, focus() { activo = this; } };
const consulta = { textContent: "" };
const region = {
  hijos: 0, replaceChildren(...n) { this.hijos = n.length; },
  querySelector(s) { return this.hijos ? (s === "[data-consulta]" ? consulta : s === "[data-reintentar]" ? boton : null) : null; },
  contains(e) { return e === boton && this.hijos > 0; },
};
const campo = { value: "  batman " };
const ajax = [];
const elementos = { "busqueda-fallo": region, "rejilla": rejilla, "f-q": campo,
  "busqueda-fallo-plantilla": { content: { cloneNode: () => ({}) } } };
const documento = {
  getElementById: (id) => elementos[id] || null,
  addEventListener: (tipo, f) => { escuchas[tipo] = f; },
  get activeElement() { return activo; },
};
vm.runInContext(js, vm.createContext({ document: documento, console,
  window: { htmx: { ajax: (...a) => ajax.push(a) } } }));
const lanzar = (tipo, detail) => escuchas[tipo]({ detail });
const salida = {};

// Petición correcta a la rejilla: guarda la URL y marca la rejilla ocupada.
const ctxOk = { target: rejilla, request: { action: "/ui/biblioteca/resultados?q=batman&orden=titulo" }, response: { status: 200 } };
lanzar("htmx:before:request", { ctx: ctxOk });
salida.ocupada = rejilla.attrs["aria-busy"] === "true";
lanzar("htmx:after:request", { ctx: ctxOk });
lanzar("htmx:finally:request", { ctx: ctxOk });
salida.libre = rejilla.attrs["aria-busy"] === undefined;

// 5xx: no se intercambia el cuerpo de error, se avisa con la consulta y se marca la lista como anterior.
lanzar("htmx:before:request", { ctx: ctxOk });
const ctx502 = { target: rejilla, request: ctxOk.request, response: { status: 502 }, swap: "innerHTML" };
lanzar("htmx:response:error", { ctx: ctx502 });
salida.noIntercambia = ctx502.swap === "none";
salida.avisa = region.hijos === 1 && consulta.textContent === " «batman»";
salida.marcaAnterior = rejilla.dataset.obsoleta === "true";

// «Reintentar» repite exactamente la misma petición, sin releer el formulario.
campo.value = "otra cosa";
boton.listeners.click();
salida.reintentoIdentico = ajax.length === 1 && ajax[0][0] === "GET" && ajax[0][1] === ctxOk.request.action
  && ajax[0][2].target === "#rejilla" && boton.disabled === true;

// Al llegar una respuesta buena el aviso y la marca desaparecen.
lanzar("htmx:after:request", { ctx: { target: rejilla, response: { status: 200 } } });
salida.seLimpia = region.hijos === 0 && rejilla.dataset.obsoleta === undefined;

// Fallo de red: también avisa; una cancelación por otra consulta más reciente (AbortError) no.
lanzar("htmx:error", { ctx: ctxOk, error: { name: "AbortError" } });
salida.cancelacionNoAvisa = region.hijos === 0;
lanzar("htmx:error", { ctx: ctxOk, error: { name: "TypeError" } });
salida.redCaidaAvisa = region.hijos === 1;

// Los fallos de otras peticiones (no de la rejilla) no tocan nada.
lanzar("htmx:after:request", { ctx: { target: rejilla, response: { status: 200 } } });
const ajena = { target: {}, swap: "innerHTML" };
lanzar("htmx:response:error", { ctx: ajena });
lanzar("htmx:error", { ctx: ajena, error: { name: "TypeError" } });
salida.ajenasIgnoradas = ajena.swap === "innerHTML" && region.hijos === 0;
process.stdout.write(JSON.stringify(salida));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_un_fallo_de_la_rejilla_avisa_conserva_la_consulta_y_se_puede_reintentar(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    assert json.loads(r.stdout) == {
        "ocupada": True, "libre": True,
        "noIntercambia": True, "avisa": True, "marcaAnterior": True,
        "reintentoIdentico": True, "seLimpia": True,
        "cancelacionNoAvisa": True, "redCaidaAvisa": True, "ajenasIgnoradas": True,
    }
