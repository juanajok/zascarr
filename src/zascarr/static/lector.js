/* Lector de tebeos (BL-LEC1, ADR 0021). Un fichero, sin dependencias. */
(() => {
  "use strict";
  const raiz = document.querySelector("[data-lector]");
  if (!raiz) return;
  const total = Number.parseInt(raiz.dataset.total || "1", 10);
  let pagina = Number.parseInt(raiz.dataset.pagina || "1", 10);
  if (!Number.isFinite(pagina) || pagina < 1) pagina = 1;
  if (!Number.isFinite(total) || total < 1) return;
  const imagen = document.getElementById("lector-pagina");
  const contador = document.getElementById("lector-contador");
  const anterior = document.getElementById("lector-anterior");
  const siguiente = document.getElementById("lector-siguiente");
  const urlPagina = raiz.dataset.paginaUrl;
  const urlProgreso = raiz.dataset.progresoUrl;

  const pinta = () => {
    imagen.src = urlPagina + pagina;
    imagen.alt = `Página ${pagina} de ${total}`;
    contador.textContent = `Página ${pagina} de ${total}`;
    anterior.disabled = pagina <= 1;
    siguiente.disabled = pagina >= total;
  };

  const guarda = () => {
    const cuerpo = new URLSearchParams({ pagina: String(pagina) });
    fetch(urlProgreso, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: cuerpo.toString(),
      credentials: "same-origin",
    }).catch(() => {});
  };

  const ir = (n) => {
    const destino = Math.max(1, Math.min(total, n));
    if (destino === pagina) return;
    pagina = destino;
    pinta();
    guarda();
  };

  anterior.addEventListener("click", () => ir(pagina - 1));
  siguiente.addEventListener("click", () => ir(pagina + 1));
  document.addEventListener("keydown", (evento) => {
    if (evento.target instanceof HTMLInputElement || evento.target instanceof HTMLTextAreaElement) return;
    if (evento.key === "ArrowRight" || evento.key === "PageDown") { evento.preventDefault(); ir(pagina + 1); }
    if (evento.key === "ArrowLeft" || evento.key === "PageUp") { evento.preventDefault(); ir(pagina - 1); }
    if (evento.key === "Home") { evento.preventDefault(); ir(1); }
    if (evento.key === "End") { evento.preventDefault(); ir(total); }
  });
  pinta();
})();
