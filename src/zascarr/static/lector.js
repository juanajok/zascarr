/* Lector de tebeos (BL-LEC1/2, ADR 0021). Un fichero, sin dependencias. */
(() => {
  "use strict";
  const espera = document.querySelector("[data-estado-url]");
  if (espera) {
    const aviso = document.getElementById("lector-preparando");
    const nota = document.getElementById("lector-espera-nota");
    const error = document.getElementById("lector-error");
    const reintentar = document.getElementById("lector-reintentar");
    const MAX_CONSULTAS = 10;
    let consultas = 0;
    let temporizador = null;
    let consultando = false;
    let detenido = false;
    const parar = () => {
      detenido = true;
      if (temporizador !== null && typeof clearTimeout === "function") {
        clearTimeout(temporizador);
      }
      temporizador = null;
    };
    const mostrarError = (motivo) => {
      parar();
      if (aviso) aviso.hidden = true;
      if (nota) nota.hidden = true;
      if (error) {
        error.hidden = false;
        error.textContent = motivo || "No se ha podido preparar el tebeo.";
      }
    };
    const volverAProbar = () => {
      if (consultas >= MAX_CONSULTAS) {
        parar();
        if (aviso) aviso.textContent = "El tebeo sigue preparándose; puedes reintentar cuando quieras.";
        return;
      }
      consultas += 1;
      if (typeof setTimeout === "function") {
        temporizador = setTimeout(consultar, 1500);
      }
    };
    const consultar = () => {
      if (detenido || consultando) return;
      consultando = true;
      fetch(espera.dataset.estadoUrl, { credentials: "same-origin" })
        .then((r) => r.json())
        .then((datos) => {
          if (datos.estado === "listo") {
            parar();
            window.location.reload();
          } else if (datos.estado === "error") {
            mostrarError(datos.motivo);
          } else {
            volverAProbar();
          }
        })
        .catch(() => mostrarError("No se ha podido consultar el estado del tebeo. Reintenta."))
        .finally(() => { consultando = false; });
    };
    const reintentarAhora = () => {
      detenido = false;
      consultas = 0;
      if (error) { error.hidden = true; error.textContent = ""; }
      if (aviso) { aviso.hidden = false; aviso.textContent = "Preparando el tebeo…"; }
      if (nota) nota.hidden = false;
      consultar();
    };
    if (reintentar) reintentar.addEventListener("click", reintentarAhora);
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
  const barra = document.getElementById("lector-barra");
  const paginas = document.getElementById("lector-paginas");
  const brilloControl = document.getElementById("lector-brillo");
  const contrasteControl = document.getElementById("lector-contraste");
  const sepiaControl = document.getElementById("lector-sepia");
  const invertirControl = document.getElementById("lector-invertir");
  const brilloValor = document.getElementById("lector-brillo-valor");
  const contrasteValor = document.getElementById("lector-contraste-valor");
  const resetImagen = document.getElementById("lector-imagen-reset");
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

  const IMAGEN_KEY = "zascarr.lector.imagen";
  const ajustesImagen = { brillo: 0, contraste: 0, sepia: false, invertir: false };
  const numeroAcotado = (valor) => {
    const n = Number.parseInt(valor, 10);
    return Number.isFinite(n) ? Math.max(-40, Math.min(40, n)) : 0;
  };
  const cargarImagen = () => {
    try {
      const guardado = JSON.parse(window.localStorage.getItem(IMAGEN_KEY) || "null");
      if (guardado && typeof guardado === "object") {
        ajustesImagen.brillo = numeroAcotado(guardado.brillo);
        ajustesImagen.contraste = numeroAcotado(guardado.contraste);
        ajustesImagen.sepia = guardado.sepia === true;
        ajustesImagen.invertir = guardado.invertir === true;
      }
    } catch (_) { /* sin localStorage o JSON roto: valores neutros */ }
  };
  const filtroImagen = () => {
    const partes = [];
    if (ajustesImagen.brillo) partes.push(`brightness(${(100 + ajustesImagen.brillo) / 100})`);
    if (ajustesImagen.contraste) partes.push(`contrast(${(100 + ajustesImagen.contraste) / 100})`);
    if (ajustesImagen.sepia) partes.push("sepia(1)");
    if (ajustesImagen.invertir) partes.push("invert(1)");
    return partes.length ? partes.join(" ") : "none";
  };
  const aplicarImagen = () => {
    if (paginas && paginas.style) paginas.style.filter = filtroImagen();
    if (brilloControl) brilloControl.value = String(ajustesImagen.brillo);
    if (contrasteControl) contrasteControl.value = String(ajustesImagen.contraste);
    if (sepiaControl) sepiaControl.checked = ajustesImagen.sepia;
    if (invertirControl) invertirControl.checked = ajustesImagen.invertir;
    if (brilloValor) brilloValor.textContent = String(ajustesImagen.brillo);
    if (contrasteValor) contrasteValor.textContent = String(ajustesImagen.contraste);
  };
  const guardarImagen = () => {
    try { window.localStorage.setItem(IMAGEN_KEY, JSON.stringify(ajustesImagen)); } catch (_) { /* igual */ }
  };
  const cambiarImagen = (cambio) => {
    Object.assign(ajustesImagen, cambio);
    aplicarImagen();
    guardarImagen();
  };

  try {
    const guardado = window.localStorage.getItem("zascarr.lector.modo");
    if (guardado === "ancho" || guardado === "pantalla" || guardado === "doble") modo = guardado;
  } catch (_) { /* sin localStorage el lector funciona igual */ }
  cargarImagen();

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

  const precargadas = new Map();
  const precargar = () => {
    // La precarga es una mejora: si el navegador no permite Image o no hay
    // siguiente, no cambia nada. Las imágenes viven fuera del DOM y usan la
    // misma URL/caché privada que la página actual.
    if (typeof Image !== "function") return;
    const visibles = paginasVisibles();
    const ultima = visibles[visibles.length - 1];
    const candidatas = [];
    if (modo === "doble" && paginaBVisible) {
      if (ultima + 1 <= total) candidatas.push(ultima + 1);
      if (ultima + 2 <= total) candidatas.push(ultima + 2);
    } else if (ultima + 1 <= total) {
      candidatas.push(ultima + 1);
    }
    const queridas = new Set(candidatas);
    for (const [numero, img] of precargadas) {
      if (!queridas.has(numero)) precargadas.delete(numero);
    }
    for (const numero of candidatas.slice(0, 2)) {
      if (precargadas.has(numero)) continue;
      const img = new Image();
      img.src = urlPagina + numero;
      precargadas.set(numero, img);
    }
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
    const enInicio = visibles[0] <= 1;
    const enFin = visibles[visibles.length - 1] >= total;
    // Las flechas izquierda/derecha cambian de significado en RTL: el botón
    // izquierdo avanza cuando se lee de derecha a izquierda.
    anterior.disabled = sentido === "rtl" ? enFin : enInicio;
    siguiente.disabled = sentido === "rtl" ? enInicio : enFin;
    anterior.setAttribute("aria-label",
      sentido === "rtl" ? "Página siguiente" : "Página anterior");
    siguiente.setAttribute("aria-label",
      sentido === "rtl" ? "Página anterior" : "Página siguiente");
    anterior.textContent = "‹";
    siguiente.textContent = "›";
    raiz.dataset.modo = modo;
    raiz.dataset.sentido = sentido;
    raiz.dataset.desplazamiento = String(desplazamiento);
    raiz.dataset.pagina = String(pagina);
    const fin = document.getElementById("fin");
    if (fin) fin.hidden = visibles[visibles.length - 1] < total;
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
    desplazar.hidden = modo !== "doble";
    for (const boton of document.querySelectorAll("[data-modo]")) {
      boton.setAttribute("aria-pressed", String(boton.dataset.modo === modo));
    }
    botonSentido.textContent = `Sentido: ${sentido === "rtl" ? "derecha a izquierda" : "izquierda a derecha"}`;
    precargar();
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
  let temporizadorChrome = null;
  const programaOculto = () => {
    if (typeof setTimeout !== "function") return;
    if (temporizadorChrome !== null && typeof clearTimeout === "function") {
      clearTimeout(temporizadorChrome);
    }
    temporizadorChrome = null;
    if (!menu.hidden) return;               // con Opciones abiertas no se oculta
    temporizadorChrome = setTimeout(() => {
      raiz.dataset.chrome = "oculto";
    }, 3000);
  };
  const despertarChrome = () => {
    raiz.dataset.chrome = "";
    programaOculto();
  };
  const alternarMenu = () => {
    menu.hidden = !menu.hidden;
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
    despertarChrome();
  };
  const alternarChrome = () => {
    raiz.dataset.chrome = raiz.dataset.chrome === "oculto" ? "" : "oculto";
    if (raiz.dataset.chrome === "oculto") {
      if (temporizadorChrome !== null && typeof clearTimeout === "function") {
        clearTimeout(temporizadorChrome);
      }
      temporizadorChrome = null;
    } else {
      programaOculto();
    }
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
  anterior.addEventListener("click", () => (sentido === "rtl" ? avanzar() : retroceder()));
  siguiente.addEventListener("click", () => (sentido === "rtl" ? retroceder() : avanzar()));
  menuBoton.addEventListener("click", alternarMenu);
  for (const boton of document.querySelectorAll("[data-modo]")) {
    boton.addEventListener("click", () => cambiarModo(boton.dataset.modo));
  }
  desplazar.addEventListener("click", () => {
    desplazamiento = desplazamiento === 0 ? 1 : 0;
    pinta();
  });
  botonSentido.addEventListener("click", cambiarSentido);
  if (brilloControl) brilloControl.addEventListener("input", () =>
    cambiarImagen({ brillo: numeroAcotado(brilloControl.value) }));
  if (contrasteControl) contrasteControl.addEventListener("input", () =>
    cambiarImagen({ contraste: numeroAcotado(contrasteControl.value) }));
  if (sepiaControl) sepiaControl.addEventListener("change", () =>
    cambiarImagen({ sepia: !!sepiaControl.checked }));
  if (invertirControl) invertirControl.addEventListener("change", () =>
    cambiarImagen({ invertir: !!invertirControl.checked }));
  if (resetImagen) resetImagen.addEventListener("click", () => {
    ajustesImagen.brillo = 0; ajustesImagen.contraste = 0; ajustesImagen.sepia = false; ajustesImagen.invertir = false;
    aplicarImagen();
    try { window.localStorage.removeItem(IMAGEN_KEY); } catch (_) { /* igual */ }
  });
  aplicarImagen();
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

  // Chrome auto-oculto. Sin JS la barra se queda visible (degradación honesta).
  const despertarPorEvento = () => despertarChrome();
  document.addEventListener("mousemove", despertarPorEvento, { passive: true });
  document.addEventListener("pointerdown", despertarPorEvento, { passive: true });
  document.addEventListener("focusin", despertarPorEvento);
  document.addEventListener("fullscreenchange", despertarPorEvento);
  if (typeof setTimeout === "function") programaOculto();

  document.addEventListener("keydown", (evento) => {
    if (evento.target instanceof HTMLInputElement || evento.target instanceof HTMLTextAreaElement) return;
    if (evento.key !== "h") despertarChrome();
    const siguienteTecla = sentido === "rtl" ? "ArrowLeft" : "ArrowRight";
    const anteriorTecla = sentido === "rtl" ? "ArrowRight" : "ArrowLeft";
    if (evento.key === siguienteTecla || evento.key === "PageDown") { evento.preventDefault(); avanzar(); }
    else if (evento.key === anteriorTecla || evento.key === "PageUp") { evento.preventDefault(); retroceder(); }
    else if (evento.key === " ") { evento.preventDefault(); evento.shiftKey ? retroceder() : avanzar(); }
    else if (evento.key === "f") { evento.preventDefault(); alternarPantalla(); }
    else if (evento.key === "h") { evento.preventDefault(); alternarChrome(); }
    else if (evento.key === "m") { evento.preventDefault(); cambiarModo(modo === "ancho" ? "pantalla" : modo === "pantalla" ? "doble" : "ancho"); }
    else if (evento.key === "Escape") {
      if (document.fullscreenElement) return;       // el navegador sale del fullscreen
      if (!menu.hidden) { alternarMenu(); return; }
      if (raiz.dataset.chrome === "oculto") { despertarChrome(); return; }
      window.location.assign(volver);
    }
    else if (evento.key === "Home") { evento.preventDefault(); ir(1); }
    else if (evento.key === "End") { evento.preventDefault(); ir(total); }
  });

  let toqueInicio = null;
  lienzo.addEventListener("touchstart", (evento) => {
    despertarChrome();
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
