/* #1101: flechas de los carruseles del Escaparate. Solo en Biblioteca. */
(() => {
  document.querySelectorAll(".escaparate-bloque").forEach((bloque) => {
    const lista = bloque.querySelector(".escaparate-lista");
    if (!lista || lista.dataset.flechas === "1") return;
    lista.dataset.flechas = "1";
    const nav = document.createElement("div");
    nav.className = "escaparate-nav";
    const izq = document.createElement("button");
    izq.type = "button"; izq.className = "btn ghost sm"; izq.textContent = "←";
    izq.setAttribute("aria-label", "Ver anteriores");
    const der = document.createElement("button");
    der.type = "button"; der.className = "btn ghost sm"; der.textContent = "→";
    der.setAttribute("aria-label", "Ver siguientes");
    izq.addEventListener("click", () => lista.scrollBy({ left: -lista.clientWidth * 0.8, behavior: "smooth" }));
    der.addEventListener("click", () => lista.scrollBy({ left: lista.clientWidth * 0.8, behavior: "smooth" }));
    nav.append(izq, der);
    bloque.insertBefore(nav, lista);
  });
})();
