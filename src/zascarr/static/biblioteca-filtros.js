/* #1115: panel de filtros debajo del disparador y cierre por fuera/Escape. */
(() => {
  const panel = document.getElementById("panel-filtros");
  if (!panel) return;
  const boton = panel.querySelector("summary");
  const escritorio = window.matchMedia("(min-width: 861px)");

  function colocar() {
    // El OOB de HTMX sustituye #filtros-campos: se reconsulta en cada llamada.
    const caja = panel.querySelector(".barra-panel-campos");
    if (!panel.open || !caja || !boton) return;
    if (!escritorio.matches) { caja.style.removeProperty("--panel-filtros-top"); return; }
    const borde = boton.getBoundingClientRect().bottom + 8;
    caja.style.setProperty("--panel-filtros-top", `${Math.round(borde)}px`);
  }

  panel.addEventListener("toggle", colocar);
  window.addEventListener("resize", colocar);
  window.addEventListener("scroll", colocar, { passive: true });
  document.body.addEventListener("htmx:afterSwap", colocar);
  document.addEventListener("click", (evento) => {
    // UXA-08: «Cerrar filtros» (delegado: el OOB de HTMX sustituye el contenido del panel).
    const cerrar = evento.target instanceof Element ? evento.target.closest("[data-cerrar-filtros]") : null;
    if (cerrar && panel.contains(cerrar)) {
      panel.open = false;
      boton.focus();
      return;
    }
    if (panel.open && !panel.contains(evento.target)) panel.open = false;
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key !== "Escape" || !panel.open) return;
    panel.open = false;
    boton.focus();
  });
})();

/* #1120: si una petición que actualiza la rejilla falla (red caída, 4xx/5xx), la lista anterior
   no pasa por resultado: se avisa, se marca como anterior y se puede repetir la misma petición.
   htmx 4 sustituye por defecto las respuestas 4xx/5xx, así que aquí se cancela ese intercambio. */
(() => {
  const region = document.getElementById("busqueda-fallo");
  const plantilla = document.getElementById("busqueda-fallo-plantilla");
  const rejilla = document.getElementById("rejilla");
  if (!region || !plantilla || !rejilla || !window.htmx) return;

  let ultima = null;
  let pendientes = 0;
  const esDeLaRejilla = (ctx) => {
    if (!ctx) return false;
    const destino = typeof ctx.target === "string" ? document.querySelector(ctx.target) : ctx.target;
    return destino === rejilla;
  };
  const ocultar = () => {
    region.replaceChildren();
    delete rejilla.dataset.obsoleta;
  };
  const mostrar = () => {
    const habiaFoco = region.contains(document.activeElement);
    region.replaceChildren(plantilla.content.cloneNode(true));
    const campo = document.getElementById("f-q");
    const consulta = region.querySelector("[data-consulta]");
    if (consulta && campo && campo.value.trim()) consulta.textContent = ` «${campo.value.trim()}»`;
    rejilla.dataset.obsoleta = "true";
    const boton = region.querySelector("[data-reintentar]");
    if (!boton) return;
    boton.addEventListener("click", () => {
      if (!ultima) return;
      boton.disabled = true;
      boton.textContent = "Reintentando…";
      window.htmx.ajax("GET", ultima, { target: "#rejilla", swap: "innerHTML" });
    });
    if (habiaFoco) boton.focus();
  };

  document.addEventListener("htmx:before:request", (evento) => {
    const ctx = evento.detail && evento.detail.ctx;
    if (!esDeLaRejilla(ctx)) return;
    ultima = ctx.request && ctx.request.action;
    pendientes += 1;
    rejilla.setAttribute("aria-busy", "true");
  });
  document.addEventListener("htmx:finally:request", (evento) => {
    if (!esDeLaRejilla(evento.detail && evento.detail.ctx)) return;
    pendientes = Math.max(0, pendientes - 1);
    if (!pendientes) rejilla.removeAttribute("aria-busy");
  });
  document.addEventListener("htmx:after:request", (evento) => {
    const ctx = evento.detail && evento.detail.ctx;
    if (esDeLaRejilla(ctx) && ctx.response && ctx.response.status < 400) ocultar();
  });
  document.addEventListener("htmx:response:error", (evento) => {
    const ctx = evento.detail && evento.detail.ctx;
    if (!esDeLaRejilla(ctx)) return;
    ctx.swap = "none";
    mostrar();
  });
  document.addEventListener("htmx:error", (evento) => {
    const { ctx, error } = evento.detail || {};
    // Una petición cancelada por otra más reciente (hx-sync="replace") no es un fallo.
    if (!esDeLaRejilla(ctx) || (error && error.name === "AbortError")) return;
    mostrar();
  });
})();
