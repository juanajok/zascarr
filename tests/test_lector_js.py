"""Pruebas de comportamiento del JS del lector (BL-LEC2), con un DOM mínimo en Node."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
JS = RAIZ / "src" / "zascarr" / "static" / "lector.js"

HARNESS = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
function E(id) {
  this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {};
  this.hidden = false; this.disabled = false; this.complete = true;
  this.naturalWidth = 800; this.naturalHeight = 1200; this.textContent = "";
  this._src = null;
}
E.prototype.addEventListener = function (t, f) { (this.listeners[t] ||= []).push(f); };
E.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
E.prototype.getAttribute = function (k) {
  return k === "src" ? this._src : (this.attrs[k] ?? null);
};
E.prototype.removeAttribute = function (k) {
  if (k === "src") this._src = null; else delete this.attrs[k];
};
function run(conPantalla) {
  const els = {};
  const root = new E("root");
  root.dataset = { total: "8", pagina: "1", sentido: "ltr",
    paginaUrl: "/p/", progresoUrl: "/prog", sentidoUrl: "/sent",
    volver: "/volver" };
  const modos = ["ancho", "pantalla", "doble"].map((m) => {
    const b = new E(m); b.dataset.modo = m; return b;
  });
  els["lector-pantalla-completa"] = new E("lector-pantalla-completa");
  els["lector-pantalla-completa"].hidden = true;
  const doc = {
    querySelector: (sel) => (sel === "[data-lector]" ? root : null),
    querySelectorAll: (sel) => (sel === "[data-modo]" ? modos : []),
    getElementById: (id) => (els[id] ||= new E(id)),
    addEventListener: (t, f) => { (doc.listeners[t] ||= []).push(f); },
    listeners: {}, documentElement: new E("html"), fullscreenElement: null,
  };
  if (conPantalla) {
    doc.documentElement.requestFullscreen = () => {
      doc.fullscreenElement = doc.documentElement; return Promise.resolve();
    };
    doc.exitFullscreen = () => {
      doc.fullscreenElement = null; return Promise.resolve();
    };
  }
  const sandbox = {
    document: doc,
    window: { localStorage: { getItem: () => null, setItem: () => {} },
              location: { assign: () => {} } },
    URLSearchParams, fetch: () => Promise.resolve({ ok: true }),
    HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox);
  const fire = (el, tipo, ev = {}) => (el.listeners[tipo] || []).forEach((f) => f(ev));
  return { root, els, modos, doc, fire };
}
const con = run(true);
const sin = run(false);
const salida = {
  fullscreenConApi: con.els["lector-pantalla-completa"].hidden === false,
  fullscreenSinApi: sin.els["lector-pantalla-completa"].hidden === true,
  dobleActiva: (() => {
    con.fire(con.modos[2], "click");
    return con.root.dataset.modo === "doble" && con.els["lector-pagina-b"].hidden === false;
  })(),
  avanzaConFlecha: (() => {
    const tecla = { key: "ArrowRight", target: {}, preventDefault: () => {} };
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    return con.root.dataset.pagina !== "1";
  })(),
  fSinApiNoRompe: (() => {
    try {
      const tecla = { key: "f", target: {}, preventDefault: () => {} };
      sin.doc.listeners.keydown.forEach((f) => f(tecla));
      return true;
    } catch (_) { return false; }
  })(),
  hAlternaChrome: (() => {
    const tecla = { key: "h", target: {}, preventDefault: () => {} };
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    const oculto = con.root.dataset.chrome === "oculto";
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    return oculto && con.root.dataset.chrome === "";
  })(),
};
process.stdout.write(JSON.stringify(salida));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_lector_js_fullscreen_doble_y_teclado(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    datos = json.loads(r.stdout)
    assert datos == {
        "fullscreenConApi": True, "fullscreenSinApi": True,
        "dobleActiva": True, "avanzaConFlecha": True, "fSinApiNoRompe": True,
        "hAlternaChrome": True,
    }


HARNESS_ESTADO = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
let recargas = 0;
let consultas = 0;
const espera = { dataset: { estadoUrl: "/estado" } };
const aviso = { textContent: "" };
const sandbox = {
  document: {
    querySelector: (sel) => (sel === "[data-estado-url]" ? espera : null),
    getElementById: () => aviso,
  },
  window: { location: { reload: () => { recargas += 1; } },
            localStorage: { getItem: () => null, setItem: () => {} } },
  URLSearchParams,
  fetch: () => { consultas += 1; return Promise.resolve({
    json: () => Promise.resolve({ estado: "preparando" }) }); },
  setTimeout: (fn) => { fn(); },
  HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
};
vm.createContext(sandbox);
vm.runInContext(js, sandbox);
setTimeout(() => process.stdout.write(JSON.stringify({ recargas, consultas })), 50);
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_el_sondeo_de_preparando_reintenta_y_recarga(tmp_path):
    harness = tmp_path / "estado.js"
    harness.write_text(HARNESS_ESTADO, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    assert json.loads(r.stdout) == {"recargas": 1, "consultas": 5}


HARNESS_IMAGEN = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
function E(id) {
  this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {};
  this.hidden = false; this.disabled = false; this.complete = true;
  this.naturalWidth = 800; this.naturalHeight = 1200; this.textContent = "";
  this.value = "0"; this.checked = false; this.style = {}; this._src = null;
}
E.prototype.addEventListener = function (t, f) { (this.listeners[t] ||= []).push(f); };
E.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
E.prototype.getAttribute = function (k) { return k === "src" ? this._src : (this.attrs[k] ?? null); };
E.prototype.removeAttribute = function (k) { if (k === "src") this._src = null; else delete this.attrs[k]; };
function run(conStorage) {
  const els = {};
  const root = new E("root");
  root.dataset = { total: "8", pagina: "1", sentido: "ltr", paginaUrl: "/p/",
    progresoUrl: "/prog", sentidoUrl: "/sent", volver: "/volver" };
  const store = new Map();
  const doc = {
    querySelector: (sel) => (sel === "[data-lector]" ? root : null),
    querySelectorAll: () => [],
    getElementById: (id) => (els[id] ||= new E(id)),
    addEventListener: () => {},
    documentElement: new E("html"),
    fullscreenElement: null,
  };
  const storage = {
    getItem: (k) => { if (!conStorage) throw new Error("sin storage"); return store.get(k) || null; },
    setItem: (k, v) => { if (!conStorage) throw new Error("sin storage"); store.set(k, String(v)); },
    removeItem: (k) => { if (!conStorage) throw new Error("sin storage"); store.delete(k); },
  };
  const sandbox = {
    document: doc,
    window: { localStorage: storage, location: { assign: () => {} } },
    URLSearchParams, fetch: () => Promise.resolve({ ok: true }),
    HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox);
  const fire = (el, tipo) => (el.listeners[tipo] || []).forEach((f) => f({ target: el }));
  return { els, root, store, fire };
}
const con = run(true);
con.els["lector-brillo"].value = "20";
con.fire(con.els["lector-brillo"], "input");
const conBrillo = con.els["lector-paginas"].style.filter;
con.els["lector-sepia"].checked = true;
con.fire(con.els["lector-sepia"], "change");
const conSepia = con.els["lector-paginas"].style.filter;
const guardado = JSON.parse(con.store.get("zascarr.lector.imagen"));
con.fire(con.els["lector-imagen-reset"], "click");
const trasReset = con.els["lector-paginas"].style.filter;
const sin = run(false);
const sinStorage = sin.els["lector-paginas"].style.filter;
process.stdout.write(JSON.stringify({conBrillo, conSepia, guardado, trasReset, sinStorage}));
'''

@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_lector_ajustes_de_imagen_dom(tmp_path):
    harness = tmp_path / "imagen.js"
    harness.write_text(HARNESS_IMAGEN, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    datos = json.loads(r.stdout)
    assert datos["conBrillo"] == "brightness(1.2)"
    assert datos["conSepia"] == "brightness(1.2) sepia(1)"
    assert datos["guardado"] == {"brillo": 20, "contraste": 0, "sepia": True, "invertir": False}
    assert datos["trasReset"] == "none"
    assert datos["sinStorage"] == "none"


HARNESS_PRECARGA = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
const pedidas = [];
function E(id) {
  this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {};
  this.hidden = false; this.disabled = false; this.complete = true;
  this.naturalWidth = 800; this.naturalHeight = 1200; this.textContent = "";
  this.value = "0"; this.checked = false; this.style = {}; this._src = null;
}
E.prototype.addEventListener = function (t, f) { (this.listeners[t] ||= []).push(f); };
E.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
E.prototype.getAttribute = function (k) { return k === "src" ? this._src : (this.attrs[k] ?? null); };
E.prototype.removeAttribute = function (k) { if (k === "src") this._src = null; else delete this.attrs[k]; };
function Img() { this._src = null; }
Object.defineProperty(Img.prototype, "src", {
  set(v) { this._src = v; pedidas.push(v); },
  get() { return this._src; },
});
const els = {};
const root = new E("root");
root.dataset = { total: "8", pagina: "1", sentido: "ltr", paginaUrl: "/p/",
  progresoUrl: "/prog", sentidoUrl: "/sent", volver: "/volver" };
const doc = {
  querySelector: (sel) => (sel === "[data-lector]" ? root : null),
  querySelectorAll: () => [],
  getElementById: (id) => (els[id] ||= new E(id)),
  addEventListener: (t, f) => { (doc.listeners[t] ||= []).push(f); },
  listeners: {}, documentElement: new E("html"), fullscreenElement: null,
};
const sandbox = {
  document: doc, Image: Img,
  window: { localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
            location: { assign: () => {} } },
  URLSearchParams, fetch: () => Promise.resolve({ ok: true }),
  HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
};
vm.createContext(sandbox); vm.runInContext(js, sandbox);
const antes = pedidas.slice();
const tecla = (key) => ({ key, target: {}, preventDefault: () => {} });
doc.listeners.keydown.forEach((f) => f(tecla("ArrowRight")));
const trasAvance = pedidas.slice();
doc.listeners.keydown.forEach((f) => f(tecla("End")));
const trasFinal = pedidas.slice();
const fueraDeRango = pedidas.filter((u) => Number.parseInt(u.split("/").pop(), 10) > 8);
const duplicados = pedidas.filter((u, i) => pedidas.indexOf(u) !== i);
process.stdout.write(JSON.stringify({ antes, trasAvance, trasFinal, fueraDeRango, duplicados }));
'''

@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_lector_precarga_la_siguiente_sin_salirse_de_rango(tmp_path):
    harness = tmp_path / "precarga.js"
    harness.write_text(HARNESS_PRECARGA, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    datos = json.loads(r.stdout)
    assert datos["antes"] == ["/p/2"]
    assert datos["trasAvance"] == ["/p/2", "/p/3"]
    assert datos["fueraDeRango"] == []
    assert datos["duplicados"] == []
