/* #1044: visor de portada HD con <dialog> nativo. Sin dependencias. */
(() => {
  const dialog = document.getElementById("visor-portada");
  if (!dialog) return;
  const contenedor = dialog.querySelector(".visor-portada-imagen");
  const enlace = dialog.querySelector(".visor-portada-enlace");
  const titulo = dialog.querySelector("#visor-portada-titulo");
  const prev = dialog.querySelector("[data-visor-prev]");
  const next = dialog.querySelector("[data-visor-next]");
  let invocador = null;
  const botones = [...document.querySelectorAll("[data-visor-src]")];
  const porSrc = (src) => botones.find((b) => b.dataset.visorSrc === src);

  function imagen() {
    let img = contenedor.querySelector("img");
    if (!img) {
      img = document.createElement("img");
      img.className = "visor-portada-img";
      contenedor.prepend(img);
    }
    return img;
  }

  function pintar(boton) {
    const img = imagen();
    const src = boton.dataset.visorSrc;
    const texto = boton.dataset.visorTitulo || "Portada ampliada";
    img.src = src;
    img.alt = `Portada de ${texto}`;
    enlace.href = src;
    enlace.setAttribute("download", "");
    titulo.textContent = texto;
    const p = porSrc(boton.dataset.visorPrev || "");
    const n = porSrc(boton.dataset.visorNext || "");
    prev.disabled = !p;
    next.disabled = !n;
    prev.dataset.destino = p ? p.dataset.visorSrc : "";
    next.dataset.destino = n ? n.dataset.visorSrc : "";
  }

  document.addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-visor-src]");
    if (!boton) return;
    evento.preventDefault();
    invocador = boton;
    pintar(boton);
    dialog.showModal();
  });

  function navegar(destino) {
    const boton = porSrc(destino);
    if (boton) pintar(boton);
  }

  prev.addEventListener("click", () => navegar(prev.dataset.destino));
  next.addEventListener("click", () => navegar(next.dataset.destino));
  dialog.addEventListener("close", () => { if (invocador) invocador.focus(); });
  dialog.addEventListener("keydown", (evento) => {
    if (evento.key === "ArrowLeft") { evento.preventDefault(); navegar(prev.dataset.destino); }
    if (evento.key === "ArrowRight") { evento.preventDefault(); navegar(next.dataset.destino); }
  });
  dialog.addEventListener("click", (evento) => {
    if (evento.target === dialog) dialog.close();
  });
})();
