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
    if (panel.open && !panel.contains(evento.target)) panel.open = false;
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key !== "Escape" || !panel.open) return;
    panel.open = false;
    boton.focus();
  });
})();
