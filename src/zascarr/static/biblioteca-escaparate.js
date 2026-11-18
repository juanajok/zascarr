/* #1101: flechas de los carruseles del Escaparate. Solo en Biblioteca. */
(() => {
  const reducido = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const icono = () => document.getElementById("tpl-escaparate-flecha")?.innerHTML || "";
  const navTpl = () => document.getElementById("tpl-escaparate-nav")?.innerHTML || '<div class="escaparate-nav"></div>';
  const comportamiento = () => (reducido() ? "auto" : "smooth");

  function actualizar(izq, der, lista) {
    izq.disabled = lista.scrollLeft <= 1;
    der.disabled = lista.scrollLeft + lista.clientWidth >= lista.scrollWidth - 1;
  }

  function init(raiz = document) {
    raiz.querySelectorAll(".escaparate-bloque").forEach((bloque) => {
      const lista = bloque.querySelector(".escaparate-lista");
      if (!lista || lista.dataset.flechas === "1") return;
      lista.dataset.flechas = "1";
      const nav = document.createElement("div");
      nav.innerHTML = navTpl();
      const caja = nav.firstElementChild || nav;
      const izq = document.createElement("button");
      izq.type = "button"; izq.className = "btn ghost sm"; izq.dataset.dir = "prev";
      izq.setAttribute("aria-label", "Ver anteriores"); izq.innerHTML = icono();
      const der = document.createElement("button");
      der.type = "button"; der.className = "btn ghost sm"; der.dataset.dir = "next";
      der.setAttribute("aria-label", "Ver siguientes"); der.innerHTML = icono();
      const mover = (dir) => {
        lista.scrollBy({ left: dir * lista.clientWidth * 0.8, behavior: comportamiento() });
        window.setTimeout(() => actualizar(izq, der, lista), 250);
      };
      izq.addEventListener("click", () => mover(-1));
      der.addEventListener("click", () => mover(1));
      lista.addEventListener("scroll", () => actualizar(izq, der, lista), { passive: true });
      caja.append(izq, der);
      bloque.insertBefore(caja, lista);
      actualizar(izq, der, lista);
    });
  }

  init();
  document.body.addEventListener("htmx:afterSwap", (evento) => init(evento.target));
})();
