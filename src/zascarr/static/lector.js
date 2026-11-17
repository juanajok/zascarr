/* Lector de tebeos (BL-LEC1/2, ADR 0021). Un fichero, sin dependencias. */
(() => {
  "use strict";
  const espera = document.querySelector("[data-estado-url]");
  if (espera) {
    const aviso = document.getElementById("lector-preparando");
    let intentos = 0;
    const volverAProbar = () => {
      intentos += 1;
      if (intentos >= 5) window.location.reload();
      else setTimeout(consultar, 1500);
    };
    const consultar = () => fetch(espera.dataset.estadoUrl, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((datos) => {
        if (datos.estado === "listo") window.location.reload();
        else if (datos.estado === "error") {
          aviso.textContent = datos.motivo || "No se ha podido preparar el tebeo.";
        } else { volverAProbar(); }
      }).catch(volverAProbar);
    consultar();
    return;
  }
  const raiz = document.querySelector("[data-lector]");
  if (!raiz) return;
  const total = Number.parseInt(raiz.dataset.total || "1", 10);
  let pagina = Number.parseInt(raiz.dataset.pagina || "1", 10);
  if (!Number.isFinite(pagina) || pagina < 1) pagina = 1;
  if (!Number.isFinite(total) || total < 1) return;

  const lienzo = document.getElementById("lector-lienzo");
  const imagen = document.getElementById("lector-pagina");
  const imagenB = document.getElementById("lector-pagina-b");
  const contador = document.getElementById("lector-contador");
  const anterior = document.getElementById("lector-anterior");
  const siguiente = document.getElementById("lector-siguiente");
  const menuBoton = document.getElementById("lector-menu-boton");
  const menu = document.getElementById("lector-menu");
  const desplazar = document.getElementById("lector-desplazar");
  const botonSentido = document.getElementById("lector-sentido");
  const botonPantalla = document.getElementById("lector-pantalla-completa");
  const urlPagina = raiz.dataset.paginaUrl;
  const urlProgreso = raiz.dataset.progresoUrl;
  const urlSentido = raiz.dataset.sentidoUrl;
  const volver = raiz.dataset.volver;

  let sentido = raiz.dataset.sentido === "rtl" ? "rtl" : "ltr";
  let modo = "ancho";
  let desplazamiento = 0;
  let paginaBVisible = false;

  try {
    const guardado = window.localStorage.getItem("zascarr.lector.modo");
    if (guardado === "ancho" || guardado === "pantalla" || guardado === "doble") modo = guardado;
  } catch (_) { /* sin localStorage el lector funciona igual */ }

  const esApaisada = (img) => img.naturalWidth > img.naturalHeight;
  const pareja = () => {
    const base = pagina - ((pagina - 1) % 2) + desplazamiento;
    return Math.max(1, Math.min(total - 1, base));
  };
  const paginasVisibles = () => {
    if (modo !== "doble" || paginaBVisible === false) return [pagina];
    const a = pareja();
    return a + 1 <= total ? [a, a + 1] : [a];
  };

  const pinta = () => {
    const visibles = paginasVisibles();
    const fuenteA = urlPagina + visibles[0];
    if (imagen.getAttribute("src") !== fuenteA) imagen.src = fuenteA;
    imagen.alt = `Página ${visibles[0]} de ${total}`;
    if (visibles.length > 1) {
      const fuenteB = urlPagina + visibles[1];
      if (imagenB.getAttribute("src") !== fuenteB) imagenB.src = fuenteB;
      imagenB.alt = `Página ${visibles[1]} de ${total}`;
      imagenB.hidden = false;
    } else {
      imagenB.hidden = true;
      imagenB.removeAttribute("src");
      imagenB.alt = "";
    }
    contador.textContent = visibles.length > 1
      ? `Páginas ${visibles[0]}–${visibles[1]} de ${total}`
      : `Página ${visibles[0]} de ${total}`;
    anterior.disabled = visibles[0] <= 1;
    siguiente.disabled = visibles[visibles.length - 1] >= total;
    raiz.dataset.modo = modo;
    raiz.dataset.sentido = sentido;
    raiz.dataset.desplazamiento = String(desplazamiento);
    raiz.dataset.pagina = String(pagina);
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
    desplazar.hidden = modo !== "doble";
    for (const boton of document.querySelectorAll("[data-modo]")) {
      boton.setAttribute("aria-pressed", String(boton.dataset.modo === modo));
    }
    botonSentido.textContent = `Sentido: ${sentido === "rtl" ? "derecha a izquierda" : "izquierda a derecha"}`;
    anterior.textContent = sentido === "rtl" ? "Anterior →" : "← Anterior";
    siguiente.textContent = sentido === "rtl" ? "← Siguiente" : "Siguiente →";
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
  const avanzar = () => {
    if (modo === "doble" && paginaBVisible) ir(pagina + 2);
    else ir(pagina + 1);
  };
  const retroceder = () => {
    if (modo === "doble" && paginaBVisible) ir(pagina - 2);
    else ir(pagina - 1);
  };
  const alternarMenu = () => {
    menu.hidden = !menu.hidden;
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
  };
  const cambiarModo = (nuevo) => {
    if (nuevo !== "ancho" && nuevo !== "pantalla" && nuevo !== "doble") return;
    modo = nuevo;
    if (modo !== "doble") { desplazamiento = 0; paginaBVisible = false; }
    else decidirPareja();
    try { window.localStorage.setItem("zascarr.lector.modo", modo); } catch (_) { /* igual */ }
    pinta();
  };
  const cambiarSentido = () => {
    const anteriorSentido = sentido;
    sentido = sentido === "rtl" ? "ltr" : "rtl";
    const aviso = document.getElementById("lector-origen-sentido");
    fetch(urlSentido, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ sentido }).toString(),
      credentials: "same-origin",
    }).then((respuesta) => {
      if (!respuesta.ok) throw new Error("no guardado");
      if (aviso) aviso.textContent = "Sentido guardado para esta serie.";
    }).catch(() => {
      sentido = anteriorSentido;
      if (aviso) aviso.textContent = "No se pudo guardar el sentido; sigue valiendo el anterior.";
    }).finally(pinta);
    pinta();
  };

  const decidirPareja = () => {
    if (modo !== "doble" || !imagen.naturalWidth) { paginaBVisible = false; return; }
    paginaBVisible = !esApaisada(imagen);
  };
  imagen.addEventListener("load", () => {
    decidirPareja();
    pinta();
  });
  imagenB.addEventListener("load", () => {
    if (modo === "doble" && paginaBVisible && esApaisada(imagenB)) {
      paginaBVisible = false;
      pinta();
    }
  });
  anterior.addEventListener("click", retroceder);
  siguiente.addEventListener("click", avanzar);
  menuBoton.addEventListener("click", alternarMenu);
  for (const boton of document.querySelectorAll("[data-modo]")) {
    boton.addEventListener("click", () => cambiarModo(boton.dataset.modo));
  }
  desplazar.addEventListener("click", () => {
    desplazamiento = desplazamiento === 0 ? 1 : 0;
    pinta();
  });
  botonSentido.addEventListener("click", cambiarSentido);
  const pantallaDisponible = typeof document.documentElement.requestFullscreen === "function";
  const alternarPantalla = () => {
    if (!pantallaDisponible) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    } else {
      document.documentElement.requestFullscreen?.().catch(() => {});
    }
  };
  if (botonPantalla && pantallaDisponible) {
    botonPantalla.hidden = false;
    botonPantalla.addEventListener("click", alternarPantalla);
  }

  document.addEventListener("keydown", (evento) => {
    if (evento.target instanceof HTMLInputElement || evento.target instanceof HTMLTextAreaElement) return;
    const siguienteTecla = sentido === "rtl" ? "ArrowLeft" : "ArrowRight";
    const anteriorTecla = sentido === "rtl" ? "ArrowRight" : "ArrowLeft";
    if (evento.key === siguienteTecla || evento.key === "PageDown") { evento.preventDefault(); avanzar(); }
    else if (evento.key === anteriorTecla || evento.key === "PageUp") { evento.preventDefault(); retroceder(); }
    else if (evento.key === " ") { evento.preventDefault(); evento.shiftKey ? retroceder() : avanzar(); }
    else if (evento.key === "f") { evento.preventDefault(); alternarPantalla(); }
    else if (evento.key === "m") { evento.preventDefault(); cambiarModo(modo === "ancho" ? "pantalla" : modo === "pantalla" ? "doble" : "ancho"); }
    else if (evento.key === "Escape") { if (menu.hidden) window.location.assign(volver); else alternarMenu(); }
    else if (evento.key === "Home") { evento.preventDefault(); ir(1); }
    else if (evento.key === "End") { evento.preventDefault(); ir(total); }
  });

  let toqueInicio = null;
  lienzo.addEventListener("touchstart", (evento) => {
    if (evento.touches.length !== 1) return;
    const t = evento.touches[0];
    toqueInicio = { x: t.clientX, y: t.clientY, ancho: lienzo.clientWidth };
  }, { passive: true });
  lienzo.addEventListener("touchend", (evento) => {
    if (!toqueInicio || !evento.changedTouches.length) return;
    const t = evento.changedTouches[0];
    const dx = t.clientX - toqueInicio.x;
    const dy = t.clientY - toqueInicio.y;
    const origen = toqueInicio;
    toqueInicio = null;
    if (Math.abs(dx) >= 50 && Math.abs(dx) > 2 * Math.abs(dy)) {
      const adelante = (dx < 0) !== (sentido === "rtl");
      adelante ? avanzar() : retroceder();
      return;
    }
    if (Math.abs(dx) > 12 || Math.abs(dy) > 12) return;
    const zona = t.clientX / origen.ancho;
    if (zona < 0.3) (sentido === "rtl" ? avanzar : retroceder)();
    else if (zona > 0.7) (sentido === "rtl" ? retroceder : avanzar)();
    else alternarMenu();
  }, { passive: true });

  pinta();
  if (imagen.complete && imagen.naturalWidth) decidirPareja();
  pinta();
})();
