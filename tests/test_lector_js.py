# ruff: noqa: E501
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
  this.naturalWidth = 800; this.naturalHeight = 1200; this.writes = 0; this._text = "";
  this._src = null; this.style = {}; this.clientWidth = 1000; this.clientHeight = 800;
}
Object.defineProperty(E.prototype, "textContent", {
  get() { return this._text; }, set(value) { this._text = value; this.writes += 1; },
});
E.prototype.contains = function (other) { return other === this || other?.parent === this; };
E.prototype.closest = function () { return this.interactivo ? this : null; };
E.prototype.querySelector = function () { return this.control; };
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
  const get = doc.getElementById;
  const menu = get("lector-menu");
  const menuButton = get("lector-menu-boton");
  menu.hidden = true;
  menu.parent = get("lector-barra");
  menuButton.parent = get("lector-barra");
  menuButton.focus = () => { doc.activeElement = menuButton; };
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
  fullscreenOcultaBarra: (() => {
    con.els["lector-menu"].hidden = false;
    con.fire(con.els["lector-pantalla-completa"], "click");
    (con.doc.listeners.fullscreenchange || []).forEach((f) => f({}));
    const oculta = con.root.dataset.chrome === "oculto" &&
      con.els["lector-menu"].hidden === true;
    con.doc.fullscreenElement = null;
    (con.doc.listeners.fullscreenchange || []).forEach((f) => f({}));
    return oculta && con.root.dataset.chrome === "";
  })(),
  dobleActiva: (() => {
    con.fire(con.modos[2], "click");
    return con.root.dataset.modo === "doble" && con.els["lector-pagina-b"].hidden === false;
  })(),
  avanzaConFlecha: (() => {
    const tecla = { key: "ArrowRight", target: con.els["lector-lienzo"], preventDefault: () => {} };
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    return con.root.dataset.pagina !== "1";
  })(),
  fSinApiNoRompe: (() => {
    try {
      const tecla = { key: "f", target: sin.els["lector-lienzo"], preventDefault: () => {} };
      sin.doc.listeners.keydown.forEach((f) => f(tecla));
      return true;
    } catch (_) { return false; }
  })(),
  hAlternaChrome: (() => {
    const tecla = { key: "h", target: con.els["lector-lienzo"], preventDefault: () => {} };
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    const oculto = con.root.dataset.chrome === "oculto";
    con.doc.listeners.keydown.forEach((f) => f(tecla));
    return oculto && con.root.dataset.chrome === "";
  })(),
};
const teclado = run(true);
const get = teclado.doc.getElementById;
let interceptada = false;
const tecla = (key, target) => {
  interceptada = false;
  teclado.fire(teclado.doc, "keydown", {
    key, target, preventDefault: () => { interceptada = true; },
  });
  return interceptada;
};
salida.espacioNativo = !tecla(" ", get("lector-menu-boton")) && teclado.root.dataset.pagina === "1";
salida.atajoFuera = !tecla("f", get("lector-menu-boton")) && !teclado.doc.fullscreenElement;
salida.limiteConFoco = get("lector-anterior").getAttribute("aria-disabled") === "true"
  && !get("lector-anterior").disabled;
teclado.fire(get("lector-menu-boton"), "click");
const input = {parent: get("lector-menu"), tagName: "INPUT"};
teclado.doc.activeElement = input;
salida.escapeDesdeOpciones = tecla("Escape", input) && get("lector-menu").hidden
  && teclado.doc.activeElement === get("lector-menu-boton");
teclado.fire(get("lector-menu-boton"), "click");
teclado.fire(teclado.doc, "focusout", {target: input, relatedTarget: get("lector-lienzo")});
salida.tabFueraCierra = get("lector-menu").hidden;
const contador = get("lector-contador");
const escrituras = contador.writes;
teclado.fire(get("lector-pagina"), "load");
teclado.fire(teclado.modos[1], "click");
salida.contadorSinDuplicados = escrituras === 1 && contador.writes === escrituras;
const acciones = get("fin-acciones");
get("fin").hidden = false;
teclado.doc.activeElement = {parent: acciones};
teclado.fire(teclado.doc, "htmx:before:swap", {detail: {tasks: [{target: acciones}]}});
teclado.doc.activeElement = teclado.doc.body;
acciones.control = new E("deshacer");
acciones.control.dataset.lectorLeido = "true";
acciones.control.focus = () => { teclado.doc.activeElement = acciones.control; };
teclado.fire(acciones, "htmx:after:swap", {target: acciones});
salida.focoYAnuncioTrasGuardar = teclado.doc.activeElement === acciones.control &&
  get("lector-resultado").textContent === "Guardado: Leído.";
const tactil = run(true);
const lienzoTactil = tactil.els['lector-lienzo'];
lienzoTactil.getBoundingClientRect = () => ({left: 0, width: 1000});
tactil.root.dataset.chrome = 'oculto';
const tocar = (x, finX = x) => {
  tactil.fire(tactil.doc, 'pointerdown', {pointerType: 'touch', target: lienzoTactil});
  tactil.fire(lienzoTactil, 'touchstart', {target: lienzoTactil, touches: [{clientX: x, clientY: 100}]});
  tactil.fire(lienzoTactil, 'touchend', {target: lienzoTactil, touches: [], changedTouches: [{clientX: finX, clientY: 100}], preventDefault: () => {}});
};
tocar(850);
salida.toqueAvanzaSinBarras = tactil.root.dataset.pagina === '2' && tactil.root.dataset.chrome === 'oculto';
tocar(150);
salida.toqueRetrocedeSinBarras = tactil.root.dataset.pagina === '1' && tactil.root.dataset.chrome === 'oculto';
tocar(800, 200);
salida.deslizarSinBarras = tactil.root.dataset.pagina === '2' && tactil.root.dataset.chrome === 'oculto';
tocar(500);
salida.centroMuestra = tactil.root.dataset.chrome === '';
tocar(500);
salida.centroOculta = tactil.root.dataset.chrome === 'oculto';
const botonFin = new E('fin-boton'); botonFin.interactivo = true;
let cancelado = false;
tactil.fire(lienzoTactil, 'touchstart', {target: botonFin, touches: [{clientX: 850, clientY: 100}]});
tactil.fire(lienzoTactil, 'touchend', {target: botonFin, touches: [], changedTouches: [{clientX: 850, clientY: 100}], preventDefault: () => { cancelado = true; }});
salida.controlesTactilesNativos = !cancelado && tactil.root.dataset.pagina === '2';
tactil.fire(lienzoTactil, 'click', {target: lienzoTactil, button: 0, clientX: 500});
salida.clicCentralMuestra = tactil.root.dataset.chrome === '';
const escritorio = run(true);
escritorio.root.dataset.chrome = 'oculto';
escritorio.fire(escritorio.doc, 'mousemove', {pointerType: 'mouse', target: escritorio.els['lector-lienzo']});
escritorio.fire(escritorio.doc, 'keydown', {key: 'ArrowRight', target: escritorio.els['lector-lienzo'], preventDefault: () => {}});
salida.ratonYTeclaSinBarras = escritorio.root.dataset.pagina === '2' && escritorio.root.dataset.chrome === 'oculto';
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
        "fullscreenOcultaBarra": True,
        "dobleActiva": True, "avanzaConFlecha": True, "fSinApiNoRompe": True,
        "hAlternaChrome": True, "espacioNativo": True, "atajoFuera": True,
        "limiteConFoco": True, "escapeDesdeOpciones": True, "tabFueraCierra": True,
        "contadorSinDuplicados": True, "focoYAnuncioTrasGuardar": True,
        "toqueAvanzaSinBarras": True, "toqueRetrocedeSinBarras": True,
        "deslizarSinBarras": True, "ratonYTeclaSinBarras": True,
        "centroMuestra": True, "centroOculta": True,
        "controlesTactilesNativos": True, "clicCentralMuestra": True,
    }


HARNESS_ESTADO = r"""
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
function E(id) {
  this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {};
  this.hidden = false; this.textContent = ""; this.value = "";
}
E.prototype.addEventListener = function (t, f) { (this.listeners[t] ||= []).push(f); };
E.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
const elementos = {};
const espera = { dataset: { estadoUrl: "/estado" } };
if (process.env.ERROR_INICIAL) espera.dataset.errorInicial = "";
let recargas = 0;
let consultas = 0;
const respuestas = JSON.parse(process.env.RESPUESTAS || '["preparando"]');
const timers = new Map();
let timerId = 0;
const sandbox = {
  document: {
    querySelector: (sel) => (sel === "[data-estado-url]" ? espera : null),
    getElementById: (id) => (elementos[id] ||= new E(id)),
    addEventListener: () => {},
  },
  window: { location: { reload: () => { recargas += 1; } },
            localStorage: { getItem: () => null, setItem: () => {} } },
  URLSearchParams,
  fetch: () => {
    const estado = respuestas[Math.min(consultas, respuestas.length - 1)];
    consultas += 1;
    return Promise.resolve({ json: () => Promise.resolve({ estado, motivo: "RAR cifrado" }) });
  },
  setTimeout: (fn) => { timers.set(++timerId, fn); return timerId; },
  clearTimeout: (id) => timers.delete(id),
  HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
};
vm.createContext(sandbox);
vm.runInContext(js, sandbox);
const flush = () => new Promise((r) => setTimeout(r, 20));
(async () => {
  await flush();
  const inicial = { recargas, consultas, timers: timers.size };
  if (process.env.REINTENTO_TEMPRANO || process.env.ERROR_INICIAL) {
    elementos["lector-reintentar"].listeners.click.forEach((f) => f({}));
    await flush();
    process.stdout.write(JSON.stringify({ inicial, pendientes: timers.size, consultas }));
    return;
  }
  if (timers.size) {
    const [id, siguiente] = timers.entries().next().value;
    timers.delete(id);
    siguiente();
    await flush();
  }
  const trasError = {
    recargas, consultas, timers: timers.size,
    error: (elementos["lector-error"] || {}).textContent || "",
    errorVisible: !(elementos["lector-error"] || {}).hidden,
  };
  const boton = elementos["lector-reintentar"];
  if (boton && boton.listeners.click) boton.listeners.click.forEach((f) => f({}));
  await flush();
  const trasReintentar = { recargas, consultas, errorVisible: !(elementos["lector-error"] || {}).hidden };
  process.stdout.write(JSON.stringify({ inicial, trasError, trasReintentar }));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_el_sondeo_de_preparando_se_detiene_y_reintenta(tmp_path):
    harness = tmp_path / "estado.js"
    harness.write_text(HARNESS_ESTADO, encoding="utf-8")
    entorno = {**__import__("os").environ, "RESPUESTAS": '["preparando", "error", "error"]'}
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True, env=entorno)
    datos = json.loads(r.stdout)
    assert datos["inicial"]["consultas"] == 1
    assert datos["inicial"]["timers"] == 1
    assert datos["trasError"]["recargas"] == 0
    assert datos["trasError"]["error"] == "RAR cifrado"
    assert datos["trasError"]["errorVisible"] is True
    assert datos["trasError"]["timers"] == 0
    assert datos["trasReintentar"]["consultas"] == 3
    assert datos["trasReintentar"]["recargas"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_el_preparando_carga_una_vez_cuando_esta_listo(tmp_path):
    harness = tmp_path / "estado-listo.js"
    harness.write_text(HARNESS_ESTADO, encoding="utf-8")
    entorno = {**__import__("os").environ, "RESPUESTAS": '["listo"]'}
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True, env=entorno)
    datos = json.loads(r.stdout)
    assert datos["inicial"]["recargas"] == 1
    assert datos["inicial"]["timers"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
@pytest.mark.parametrize(("opcion", "previas"), [("REINTENTO_TEMPRANO", 1), ("ERROR_INICIAL", 0)])
def test_reintentar_reinicia_un_solo_sondeo(tmp_path, monkeypatch, opcion, previas):
    harness = tmp_path / "estado-reintento.js"
    harness.write_text(HARNESS_ESTADO, encoding="utf-8")
    monkeypatch.setenv(opcion, "1")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    datos = json.loads(r.stdout)
    assert datos["inicial"]["consultas"] == previas
    assert datos["consultas"] == previas + 1
    assert datos["pendientes"] == 1


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
E.prototype.contains = function (other) { return other === this || other?.parent === this; };
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
E.prototype.contains = function (other) { return other === this || other?.parent === this; };
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
const tecla = (key) => ({ key, target: els["lector-lienzo"], preventDefault: () => {} });
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
