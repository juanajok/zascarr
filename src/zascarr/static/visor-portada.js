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
  let actual = { src: "", titulo: "", prev: "", next: "" };

  function imagen() {
    let img = contenedor.querySelector("img");
    if (!img) {
      img = document.createElement("img");
      img.className = "visor-portada-img";
      contenedor.prepend(img);
    }
    return img;
  }

  function pintar() {
    const img = imagen();
    img.src = actual.src;
    img.alt = actual.titulo ? `Portada de ${actual.titulo}` : "Portada ampliada";
    enlace.href = actual.src;
    titulo.textContent = actual.titulo || "Portada ampliada";
    prev.disabled = !actual.prev;
    next.disabled = !actual.next;
    prev.dataset.destino = actual.prev || "";
    next.dataset.destino = actual.next || "";
  }

  document.addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-visor-src]");
    if (!boton) return;
    evento.preventDefault();
    invocador = boton;
    actual = {
      src: boton.dataset.visorSrc,
      titulo: boton.dataset.visorTitulo || "",
      prev: boton.dataset.visorPrev || "",
      next: boton.dataset.visorNext || "",
    };
    pintar();
    dialog.showModal();
  });

  function navegar(destino) {
    if (!destino) return;
    const img = imagen();
    img.src = destino;
    enlace.href = destino;
    actual.src = destino;
    img.alt = "Portada ampliada";
  }

  prev.addEventListener("click", () => navegar(prev.dataset.destino));
  next.addEventListener("click", () => navegar(next.dataset.destino));
  dialog.addEventListener("close", () => {
    if (invocador) invocador.focus();
  });
  dialog.addEventListener("keydown", (evento) => {
    if (evento.key === "ArrowLeft") { evento.preventDefault(); navegar(prev.dataset.destino); }
    if (evento.key === "ArrowRight") { evento.preventDefault(); navegar(next.dataset.destino); }
  });
  dialog.addEventListener("click", (evento) => {
    if (evento.target === dialog) dialog.close();
  });
})();
