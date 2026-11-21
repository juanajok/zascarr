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
    // Como el DOM real: la raíz también lleva data-modo, así que «[data-modo]» a secas la incluye.
    querySelectorAll: (sel) => (sel === "button[data-modo]" ? modos
      : sel === "[data-modo]" ? [root, ...modos] : []),
    getElementById: (id) => (els[id] ||= new E(id)),
    addEventListener: (t, f) => { (doc.listeners[t] ||= []).push(f); },
    listeners: {}, documentElement: new E("html"), fullscreenElement: null, body: new E("body"),
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
// #1118: el cierre propio del panel devuelve el foco al disparador y no toca página ni modo.
teclado.fire(get("lector-menu-boton"), "click");
const paginaAntes = teclado.root.dataset.pagina, modoAntes = teclado.root.dataset.modo;
teclado.doc.activeElement = get("lector-menu-cerrar");
teclado.fire(get("lector-menu-cerrar"), "click");
salida.cerrarDelPanel = get("lector-menu").hidden && teclado.doc.activeElement === get("lector-menu-boton")
  && get("lector-menu-boton").attrs["aria-expanded"] === "false"
  && teclado.root.dataset.pagina === paginaAntes && teclado.root.dataset.modo === modoAntes;
// La raíz no es un botón de modo: ni escucha clics (cerraba Opciones al abrirla) ni recibe aria-pressed.
salida.raizNoEsBotonDeModo = !(teclado.root.listeners.click || []).length
  && teclado.root.attrs["aria-pressed"] === undefined;
// #1119 (WCAG 2.1.4): + − 0 solo actúan con el foco en la zona de lectura, no con el foco en el
// cuerpo ni en otro control; con el foco en ella siguen funcionando.
const zoomTexto = () => get("lector-zoom-valor").textContent;
const pulsarZoom = (key, target) => teclado.fire(teclado.doc, "keydown", { key, target, preventDefault: () => {} });
const zoom0 = zoomTexto();
pulsarZoom("=", teclado.doc.body);
pulsarZoom("-", get("lector-brillo"));
pulsarZoom("0", teclado.doc.body);
salida.zoomSinFocoNoActua = zoomTexto() === zoom0;
pulsarZoom("=", get("lector-lienzo"));
salida.zoomConFocoActua = zoomTexto() !== zoom0;
pulsarZoom("0", get("lector-lienzo"));
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
        "cerrarDelPanel": True, "raizNoEsBotonDeModo": True,
        "zoomSinFocoNoActua": True, "zoomConFocoActua": True,
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


# BL-LEC3 decisión D (#826): el final del lector es una PÁGINA que solo se abre con intención de
# avanzar desde la última página; al llegar no se muestra nada y la vuelta no cambia el contador.
HARNESS_FIN = r'''
const fs = require("fs");
const vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8");
function E(id) {
  this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {};
  this.hidden = false; this.disabled = false; this.complete = true;
  this.naturalWidth = 800; this.naturalHeight = 1200; this.textContent = ""; this.style = {};
  this._src = null; this.clientWidth = 1000; this.clientHeight = 800;
}
Object.defineProperty(E.prototype, "src", {
  get() { return this._src; }, set(v) { this._src = v; },
});
E.prototype.contains = function (other) { return other === this || other?.parent === this; };
E.prototype.closest = function () { return this.interactivo ? this : null; };
E.prototype.querySelector = function () { return this.control; };
E.prototype.appendChild = function (hijo) { (this.hijos ||= []).push(hijo); };
E.prototype.addEventListener = function (t, f) { (this.listeners[t] ||= []).push(f); };
E.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
E.prototype.getAttribute = function (k) {
  return k === "src" ? this._src : (this.attrs[k] ?? null);
};
E.prototype.removeAttribute = function (k) {
  if (k === "src") this._src = null; else delete this.attrs[k];
};
function run(op) {
  op = op || {};
  const total = op.total || 4;
  const pagina = op.pagina || 1;
  const els = {};
  const llamadas = [];
  const navegaciones = [];
  const root = new E("root");
  root.dataset = { total: String(total), pagina: String(pagina),
    sentido: op.sentido || "ltr", paginaUrl: "/p/", progresoUrl: "/prog",
    sentidoUrl: "/sent", volver: "/volver" };
  const modos = ["ancho", "pantalla", "doble"].map((m) => {
    const b = new E(m); b.dataset.modo = m; return b;
  });
  const doc = {
    querySelector: (sel) => (sel === "[data-lector]" ? root : null),
    querySelectorAll: (sel) => (sel === "button[data-modo]" ? modos : []),
    getElementById: (id) => (els[id] ||= new E(id)),
    createElement: (tag) => new E(tag),
    addEventListener: (t, f) => { (doc.listeners[t] ||= []).push(f); },
    listeners: {}, documentElement: new E("html"), fullscreenElement: null, body: new E("body"),
    activeElement: undefined,
  };
  if (op.pantalla) {
    doc.documentElement.requestFullscreen = () => {
      doc.fullscreenElement = doc.documentElement; return Promise.resolve();
    };
    doc.exitFullscreen = () => { doc.fullscreenElement = null; return Promise.resolve(); };
  }
  const get = doc.getElementById;
  // Como el servidor: la página de fin y el panel de Opciones llegan ocultos; las páginas, visible.
  get("fin").hidden = true;
  get("lector-menu").hidden = true;
  get("lector-paginas").hidden = false;
  const lienzo = get("lector-lienzo");
  lienzo.focus = () => { doc.activeElement = lienzo; };
  lienzo.getBoundingClientRect = () => ({ left: 0, width: 1000 });
  const fin = get("fin");
  fin.getBoundingClientRect = () => ({ left: 0, width: 1000 });
  const finTitulo = get("fin-titulo");
  finTitulo.focus = () => { doc.activeElement = finTitulo; };
  finTitulo.parent = fin;
  const finQuedarme = get("fin-quedarme");
  finQuedarme.focus = () => { doc.activeElement = finQuedarme; };
  finQuedarme.parent = fin;
  const finPortada = get("fin-portada");
  let marcoPortada = null;
  if (op.portada) {
    marcoPortada = new E("portada");
    finPortada.control = marcoPortada;
    finPortada.dataset.portadaUrl = "/portada.jpg";
  }
  const almacen = { getItem: (k) => (k === "zascarr.lector.modo" ? (op.modo || null) : null),
                    setItem: () => {}, removeItem: () => {} };
  const sandbox = {
    document: doc,
    window: { localStorage: almacen,
              location: { assign: (url) => navegaciones.push(url) },
              addEventListener: () => {} },
    URLSearchParams,
    fetch: (url) => { llamadas.push(url); return Promise.resolve({ ok: true }); },
    HTMLInputElement: function () {}, HTMLTextAreaElement: function () {}, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox);
  const fire = (el, tipo, ev = {}) => (el.listeners[tipo] || []).forEach((f) => f(ev));
  return { root, els, modos, doc, fire, llamadas, navegaciones, fin, lienzo,
           paginas: get("lector-paginas"), finTitulo, finQuedarme, finPortada, marcoPortada };
}
const tecla = (banco, key, target, extra = {}) => {
  let interceptada = false;
  banco.fire(banco.doc, "keydown", { key, target: target || banco.lienzo,
    preventDefault: () => { interceptada = true; }, ...extra });
  return interceptada;
};
const salida = {};

// AC-1: llegar a la última página no abre nada ni mueve el foco; se ve la página y el contador N/N.
const camino = run({ total: 4, pagina: 3 });
camino.lienzo.focus();
tecla(camino, "ArrowRight");
camino.fire(camino.els["lector-pagina"], "load");
salida.finOcultoAlLlegar = camino.fin.hidden === true
  && camino.paginas.hidden === false && camino.lienzo.hidden === false
  && camino.root.dataset.pagina === "4"
  && camino.els["lector-contador"].textContent === "Página 4 de 4"
  && camino.doc.activeElement === camino.lienzo
  && camino.llamadas.length === 1;   // solo el POST /progreso del pase de página

// El avance en la última página sigue disponible y se anuncia como «Ver el final».
const disponible = run({ total: 4, pagina: 4 });
salida.avanceDisponibleEnUltima = disponible.els["lector-siguiente"].getAttribute("aria-disabled") === "false"
  && disponible.els["lector-siguiente"].getAttribute("aria-label") === "Ver el final"
  && disponible.els["lector-anterior"].getAttribute("aria-label") === "Página anterior";

// AC-2: avanzar abre la página de fin completa, foco en el h2, anuncio y contador intacto.
const avance = run({ total: 4, pagina: 4 });
const peticionesAntesDeAbrir = avance.llamadas.length;
avance.fire(avance.els["lector-siguiente"], "click");
salida.avanzarAbreFin = avance.fin.hidden === false
  && avance.doc.activeElement === avance.finTitulo
  && avance.paginas.hidden === true
  && avance.lienzo.hidden === true
  && avance.els["lector-resultado"].textContent === "Fin del número.";
// En la última página no hay página siguiente: avanzar abre el final y no pasa página ni guarda.
salida.siguienteNoDisponibleEnUltima = avance.root.dataset.pagina === "4"
  && avance.els["lector-contador"].textContent === "Página 4 de 4";
salida.avanzarNoPideNiGuarda = avance.llamadas.length === peticionesAntesDeAbrir;

// Teclado y gesto: →, espacio, PageDown y el deslizamiento de avance abren la página de fin.
const porIntencion = run({ total: 4, pagina: 4 });
tecla(porIntencion, "ArrowRight");
const conFlecha = porIntencion.fin.hidden === false && porIntencion.doc.activeElement === porIntencion.finTitulo;
tecla(porIntencion, "Escape", porIntencion.finTitulo);
const cerrada = porIntencion.fin.hidden === true;
tecla(porIntencion, " ");
const conEspacio = porIntencion.fin.hidden === false;
tecla(porIntencion, "Escape", porIntencion.finTitulo);
tecla(porIntencion, "PageDown");
const conPageDown = porIntencion.fin.hidden === false;
tecla(porIntencion, "Escape", porIntencion.finTitulo);
porIntencion.fire(porIntencion.lienzo, "touchstart",
  { target: porIntencion.lienzo, touches: [{ clientX: 800, clientY: 200 }], preventDefault: () => {} });
porIntencion.fire(porIntencion.lienzo, "touchend",
  { target: porIntencion.lienzo, touches: [], changedTouches: [{ clientX: 200, clientY: 200 }], preventDefault: () => {} });
const conGesto = porIntencion.fin.hidden === false;
salida.avanzarPorIntencion = conFlecha && cerrada && conEspacio && conPageDown && conGesto;

// AC-3: avanzar estando en la página de fin no hace nada (ni petición ni foco ni página).
const quieto = run({ total: 4, pagina: 4 });
quieto.fire(quieto.els["lector-siguiente"], "click");
const focoAntes = quieto.doc.activeElement;
const peticionesQuieto = quieto.llamadas.length;
tecla(quieto, "ArrowRight", quieto.finTitulo);
tecla(quieto, "PageDown", quieto.finTitulo);
tecla(quieto, " ", quieto.finTitulo);
salida.avanzarEnFinNoHaceNada = quieto.fin.hidden === false
  && quieto.doc.activeElement === focoAntes
  && quieto.root.dataset.pagina === "4"
  && quieto.llamadas.length === peticionesQuieto
  && quieto.els["lector-resultado"].textContent === "Fin del número.";

// AC-4/AC-5: «Quedarme», ←/PageUp/Shift+Espacio, deslizamiento contrario y Escape vuelven a la
// última página sin recargar ni cambiar el contador; Escape no cierra el lector.
const quedarme = run({ total: 4, pagina: 4 });
quedarme.fire(quedarme.els["lector-siguiente"], "click");
quedarme.fire(quedarme.finQuedarme, "click");
salida.volverConQuedarme = quedarme.fin.hidden === true
  && quedarme.doc.activeElement === quedarme.lienzo
  && quedarme.els["lector-resultado"].textContent === "Página 4 de 4."
  && quedarme.root.dataset.pagina === "4";
const vuelta = run({ total: 4, pagina: 4 });
vuelta.fire(vuelta.els["lector-siguiente"], "click");
const imagenAntes = vuelta.els["lector-pagina"].getAttribute("src");
tecla(vuelta, "ArrowLeft", vuelta.finTitulo);
salida.volverConAnterior = vuelta.fin.hidden === true
  && vuelta.paginas.hidden === false && vuelta.lienzo.hidden === false
  && vuelta.doc.activeElement === vuelta.lienzo
  && vuelta.els["lector-resultado"].textContent === "Página 4 de 4."
  && vuelta.root.dataset.pagina === "4"
  && vuelta.els["lector-pagina"].getAttribute("src") === imagenAntes;
const escape = run({ total: 4, pagina: 4 });
escape.fire(escape.els["lector-siguiente"], "click");
tecla(escape, "Escape", escape.finTitulo);
const escapeCierra = escape.fin.hidden === true && escape.navegaciones.length === 0;
escape.fire(escape.els["lector-siguiente"], "click");
escape.doc.activeElement = escape.doc.body;
tecla(escape, "Escape", escape.doc.body);
salida.volverConEscape = escapeCierra && escape.fin.hidden === true;
const gestoVuelta = run({ total: 4, pagina: 4 });
gestoVuelta.fire(gestoVuelta.els["lector-siguiente"], "click");
gestoVuelta.fire(gestoVuelta.fin, "touchstart",
  { target: gestoVuelta.fin, touches: [{ clientX: 100, clientY: 300 }], preventDefault: () => {} });
gestoVuelta.fire(gestoVuelta.fin, "touchend",
  { target: gestoVuelta.fin, touches: [], changedTouches: [{ clientX: 300, clientY: 300 }], preventDefault: () => {} });
salida.volverConGesto = gestoVuelta.fin.hidden === true
  && gestoVuelta.root.dataset.pagina === "4";

// FR-8: reentrada, una intención = una transición.
const reentrada = run({ total: 4, pagina: 4 });
reentrada.fire(reentrada.els["lector-siguiente"], "click");
const primera = reentrada.fin.hidden === false;
reentrada.fire(reentrada.finQuedarme, "click");
tecla(reentrada, "ArrowRight");
salida.reentrada = primera && reentrada.fin.hidden === false
  && reentrada.root.dataset.pagina === "4";

// FR-6: repintar (carga de imagen, cambio de modo) ni abre ni cierra la página de fin.
const repintar = run({ total: 4, pagina: 4 });
repintar.fire(repintar.els["lector-pagina"], "load");
const noSeAbreSolo = repintar.fin.hidden === true;
repintar.fire(repintar.els["lector-siguiente"], "click");
repintar.fire(repintar.els["lector-pagina"], "load");
repintar.fire(repintar.modos[2], "click");
salida.repintarNoAbreNiCierraFin = noSeAbreSolo && repintar.fin.hidden === false
  && repintar.root.dataset.pagina === "4";

// AC-11: en modo doble, avanzar con la última pareja visible abre la página de fin sin cambiar
// `data-pagina` y la vuelta deja la misma pareja.
const doble = run({ total: 8, pagina: 7, modo: "doble" });
const parejaAntes = doble.els["lector-pagina-b"].hidden === false;
doble.fire(doble.els["lector-siguiente"], "click");
const abiertaEnPareja = doble.fin.hidden === false && doble.root.dataset.pagina === "7";
tecla(doble, "Escape", doble.finTitulo);
salida.dobleUltimaParejaAbreFin = parejaAntes && abiertaEnPareja
  && doble.fin.hidden === true && doble.root.dataset.pagina === "7"
  && doble.els["lector-pagina-b"].hidden === false;

// AC-12: en RTL el avance es la flecha izquierda y la vuelta, la derecha.
const rtl = run({ total: 4, pagina: 4, sentido: "rtl" });
const avanceRtl = rtl.els["lector-anterior"];
const etiquetaRtl = avanceRtl.getAttribute("aria-label") === "Ver el final"
  && avanceRtl.getAttribute("aria-disabled") === "false";
rtl.fire(avanceRtl, "click");
const abiertaRtl = rtl.fin.hidden === false;
tecla(rtl, "ArrowRight", rtl.finTitulo);
salida.rtlAvanceYVuelta = etiquetaRtl && abiertaRtl && rtl.fin.hidden === true
  && rtl.root.dataset.pagina === "4";

// AC-13: con zoom, el gesto mueve la imagen y no abre la página de fin; la tecla sí la abre y el
// zoom se conserva al volver.
const zoom = run({ total: 4, pagina: 4 });
for (let i = 0; i < 4; i += 1) tecla(zoom, "+", zoom.lienzo);
const conZoom = zoom.root.dataset.zoom === "200";
zoom.fire(zoom.lienzo, "touchstart",
  { target: zoom.lienzo, touches: [{ clientX: 800, clientY: 200 }], preventDefault: () => {} });
zoom.fire(zoom.lienzo, "touchend",
  { target: zoom.lienzo, touches: [], changedTouches: [{ clientX: 200, clientY: 200 }], preventDefault: () => {} });
const gestoNoAbre = zoom.fin.hidden === true;
tecla(zoom, "ArrowRight", zoom.lienzo);
const teclaAbre = zoom.fin.hidden === false;
tecla(zoom, "Escape", zoom.finTitulo);
salida.zoomNoAbreFinConGestoYSiConTecla = conZoom && gestoNoAbre && teclaAbre
  && zoom.root.dataset.zoom === "200";

// AC-14: la pantalla completa no se pierde al abrir la página de fin, y Esc en pantalla completa
// no la cierra (es del navegador).
const pantalla = run({ total: 4, pagina: 4, pantalla: true });
pantalla.fire(pantalla.els["lector-pantalla-completa"], "click");
(pantalla.doc.listeners.fullscreenchange || []).forEach((f) => f({}));
const enPantalla = pantalla.doc.fullscreenElement === pantalla.doc.documentElement;
pantalla.fire(pantalla.els["lector-siguiente"], "click");
const abiertaEnPantalla = pantalla.fin.hidden === false
  && pantalla.doc.fullscreenElement === pantalla.doc.documentElement;
tecla(pantalla, "Escape", pantalla.finTitulo);
const sigueAbierta = pantalla.fin.hidden === false;
pantalla.doc.fullscreenElement = null;
tecla(pantalla, "Escape", pantalla.finTitulo);
salida.pantallaCompletaNoCierraFin = enPantalla && abiertaEnPantalla && sigueAbierta
  && pantalla.fin.hidden === true;

// AC-15: en la página de fin Home/End y el avance no actúan; Espacio sobre un control no se
// intercepta (actúa de forma nativa).
const teclado = run({ total: 4, pagina: 4 });
teclado.fire(teclado.els["lector-siguiente"], "click");
teclado.finQuedarme.interactivo = true;
const home = tecla(teclado, "Home", teclado.finTitulo);
const end = tecla(teclado, "End", teclado.finTitulo);
const espacioControl = tecla(teclado, " ", teclado.finQuedarme);
salida.tecladoEnFin = !home && !end && !espacioControl
  && teclado.root.dataset.pagina === "4"
  && teclado.fin.hidden === false
  && teclado.doc.activeElement === teclado.finTitulo;

// FR-12: la portada del siguiente no se pide al llegar; se hidrata al abrir una sola vez y un
// error deja el marcador (imagen oculta), nunca una imagen rota.
const portada = run({ total: 4, pagina: 4, portada: true });
const sinPortadaAntes = (portada.marcoPortada.hijos || []).length === 0;
portada.fire(portada.els["lector-siguiente"], "click");
const hijos = portada.marcoPortada.hijos || [];
const unaPortada = hijos.length === 1 && hijos[0].getAttribute("src") === "/portada.jpg"
  && hijos[0].alt === "";
portada.fire(portada.finQuedarme, "click");
portada.fire(portada.els["lector-siguiente"], "click");
const unaSolaVez = (portada.marcoPortada.hijos || []).length === 1;
(hijos[0]?.listeners.error || []).forEach((f) => f({}));
salida.portadaSeHidrataAlAbrirYSoloUnaVez = sinPortadaAntes && unaPortada && unaSolaVez
  && hijos[0]?.hidden === true && hijos[0]?.getAttribute("src") === null;

// FR-15: tras «Añadir a Deseados» la página sigue abierta, el foco no se queda en el body y el
// resultado se anuncia por la región viva, sin borrar la vuelta.
const deseo = run({ total: 4, pagina: 4 });
deseo.fire(deseo.els["lector-siguiente"], "click");
const finDeseo = deseo.doc.getElementById("fin-deseo");
finDeseo.parent = deseo.els["fin-acciones"];
deseo.doc.activeElement = deseo.doc.body;
finDeseo.textContent = "Añadido a Deseados.";
deseo.fire(deseo.els["fin-acciones"], "htmx:after:swap", { target: finDeseo });
salida.deseoMantieneLaVueltaYAnuncia = deseo.fin.hidden === false
  && deseo.doc.activeElement === deseo.finQuedarme
  && deseo.els["lector-resultado"].textContent === "Añadido a Deseados.";

process.stdout.write(JSON.stringify(salida));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node para ejecutar el JS")
def test_lector_js_pagina_de_fin_bajo_intencion(tmp_path):
    """BL-LEC3 decisión D: el final es una página que se abre al avanzar, no una tarjeta automática."""
    harness = tmp_path / "harness-fin.js"
    harness.write_text(HARNESS_FIN, encoding="utf-8")
    r = subprocess.run(["node", str(harness), str(JS)], capture_output=True, text=True,
                       timeout=30, check=True)
    datos = json.loads(r.stdout)
    assert datos == {
        "finOcultoAlLlegar": True,
        "avanceDisponibleEnUltima": True,
        "avanzarAbreFin": True,
        "siguienteNoDisponibleEnUltima": True,
        "avanzarNoPideNiGuarda": True,
        "avanzarPorIntencion": True,
        "avanzarEnFinNoHaceNada": True,
        "volverConQuedarme": True,
        "volverConAnterior": True,
        "volverConEscape": True,
        "volverConGesto": True,
        "reentrada": True,
        "repintarNoAbreNiCierraFin": True,
        "dobleUltimaParejaAbreFin": True,
        "rtlAvanceYVuelta": True,
        "zoomNoAbreFinConGestoYSiConTecla": True,
        "pantallaCompletaNoCierraFin": True,
        "tecladoEnFin": True,
        "portadaSeHidrataAlAbrirYSoloUnaVez": True,
        "deseoMantieneLaVueltaYAnuncia": True,
    }
