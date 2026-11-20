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
      if (aviso) aviso.textContent = "";
      if (nota) nota.hidden = true;
      if (error) error.textContent = motivo || "No se ha podido preparar el tebeo.";
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
      temporizador = null;
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
      if (consultando) return;
      parar();
      detenido = false;
      consultas = 0;
      if (error) error.textContent = "";
      if (aviso) aviso.textContent = "Preparando el tebeo…";
      if (nota) nota.hidden = false;
      consultar();
    };
    if (reintentar) reintentar.addEventListener("click", reintentarAhora);
    if (!("errorInicial" in espera.dataset)) consultar();
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
  const resultado = document.getElementById("lector-resultado");
  const fin = document.getElementById("fin");
  const accionesFin = document.getElementById("fin-acciones");
  const paginas = document.getElementById("lector-paginas");
  const zoomMenos = document.getElementById("lector-zoom-menos");
  const zoomMas = document.getElementById("lector-zoom-mas");
  const zoomReset = document.getElementById("lector-zoom-reset");
  const zoomValor = document.getElementById("lector-zoom-valor");
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
  // Zoom propio: el navegador no puede ampliar el lienzo fijo del lector de forma útil.
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let punteroZoom = null;
  let pinchZoom = null;
  let movioAlArrastrar = false;
  const ZOOM_MIN = 1;
  const ZOOM_MAX = 4;
  const ZOOM_PASO = 0.25;

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
    const paginasLeidas = visibles.length > 1
      ? `Páginas ${visibles[0]}–${visibles[1]} de ${total}`
      : `Página ${visibles[0]} de ${total}`;
    if (contador.textContent !== paginasLeidas) contador.textContent = paginasLeidas;
    const enInicio = visibles[0] <= 1;
    const enFin = visibles[visibles.length - 1] >= total;
    // Las flechas izquierda/derecha cambian de significado en RTL: el botón
    // izquierdo avanza cuando se lee de derecha a izquierda.
    anterior.setAttribute("aria-disabled", String(sentido === "rtl" ? enFin : enInicio));
    siguiente.setAttribute("aria-disabled", String(sentido === "rtl" ? enInicio : enFin));
    anterior.setAttribute("aria-label",
      sentido === "rtl" ? "Página siguiente" : "Página anterior");
    siguiente.setAttribute("aria-label",
      sentido === "rtl" ? "Página anterior" : "Página siguiente");
    raiz.dataset.modo = modo;
    raiz.dataset.sentido = sentido;
    raiz.dataset.desplazamiento = String(desplazamiento);
    raiz.dataset.pagina = String(pagina);
    if (fin && fin.hidden !== !enFin) {
      if (!enFin && fin.contains(document.activeElement)) lienzo.focus();
      fin.hidden = !enFin;
    }
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
    desplazar.hidden = modo !== "doble";
    for (const boton of document.querySelectorAll("[data-modo]")) {
      boton.setAttribute("aria-pressed", String(boton.dataset.modo === modo));
    }
    botonSentido.textContent = `Sentido: ${sentido === "rtl" ? "derecha a izquierda" : "izquierda a derecha"}`;
    aplicarZoom();
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
    if (zoom > 1) { panX = 0; panY = 0; }
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
  const focoEnChrome = () => {
    const activo = document.activeElement;
    if (!activo) return false;
    return (barra && barra.contains(activo)) || (menu && menu.contains(activo));
  };
  const programaOculto = () => {
    if (typeof setTimeout !== "function") return;
    if (temporizadorChrome !== null && typeof clearTimeout === "function") {
      clearTimeout(temporizadorChrome);
    }
    temporizadorChrome = null;
    if (!menu.hidden || focoEnChrome()) return;  // Opciones abiertas o foco dentro: no ocultar
    temporizadorChrome = setTimeout(() => {
      if (!menu.hidden || focoEnChrome()) return; // opciones o foco dentro: no ocultar
      raiz.dataset.chrome = "oculto";
    }, 3000);
  };
  const despertarChrome = () => {
    raiz.dataset.chrome = "";
    programaOculto();
  };
  const cambiarMenu = (abierto, devolverFoco = false) => {
    menu.hidden = !abierto;
    menuBoton.setAttribute("aria-expanded", String(abierto));
    if (devolverFoco) menuBoton.focus();
    despertarChrome();
  };
  const alternarMenu = () => cambiarMenu(menu.hidden, menu.contains(document.activeElement));
  const alternarChrome = () => {
    if (!menu.hidden || focoEnChrome()) return;
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
  const anunciar = (mensaje) => {
    if (resultado && resultado.textContent !== mensaje) resultado.textContent = mensaje;
  };
  let guardandoSentido = false;
  const cambiarSentido = () => {
    if (guardandoSentido) return;
    guardandoSentido = true;
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
      const mensaje = "Sentido guardado para esta serie.";
      if (aviso) aviso.textContent = mensaje;
      anunciar(sentido === "rtl"
        ? "Sentido guardado: de derecha a izquierda."
        : "Sentido guardado: de izquierda a derecha.");
    }).catch(() => {
      sentido = anteriorSentido;
      const mensaje = "No se pudo guardar el sentido; sigue valiendo el anterior.";
      if (aviso) aviso.textContent = mensaje;
      anunciar(mensaje);
    }).finally(() => {
      guardandoSentido = false;
      pinta();
    });
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
  anterior.addEventListener("click", () => {
    if (anterior.getAttribute("aria-disabled") !== "true") {
      sentido === "rtl" ? avanzar() : retroceder();
    }
  });
  siguiente.addEventListener("click", () => {
    if (siguiente.getAttribute("aria-disabled") !== "true") {
      sentido === "rtl" ? retroceder() : avanzar();
    }
  });
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
  const acotarPan = () => {
    const ancho = lienzo.clientWidth || 1;
    const alto = lienzo.clientHeight || 1;
    const maxX = Math.max(0, (ancho * (zoom - 1)) / 2);
    const maxY = Math.max(0, (alto * (zoom - 1)) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
  };
  const aplicarZoom = () => {
    if (!paginas || !paginas.style) return;
    if (zoom <= ZOOM_MIN) { zoom = ZOOM_MIN; panX = 0; panY = 0; }
    acotarPan();
    paginas.style.transform = zoom === 1 ? "" : `translate(${panX}px, ${panY}px) scale(${zoom})`;
    paginas.style.transformOrigin = "center center";
    raiz.dataset.zoom = String(Math.round(zoom * 100));
    if (zoomValor) zoomValor.textContent = `${Math.round(zoom * 100)} %`;
    if (zoomMenos) zoomMenos.disabled = zoom <= ZOOM_MIN;
    if (zoomMas) zoomMas.disabled = zoom >= ZOOM_MAX;
  };
  const cambiarZoom = (nuevo) => {
    zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(nuevo * 100) / 100));
    if (zoom === 1) { panX = 0; panY = 0; }
    aplicarZoom();
    anunciar(zoom === 1 ? "Vista ajustada." : `Zoom ${Math.round(zoom * 100)} %.`);
  };
  const restablecerZoom = () => {
    zoom = 1; panX = 0; panY = 0; aplicarZoom(); anunciar("Vista ajustada.");
  };
  if (zoomMenos) zoomMenos.addEventListener("click", () => cambiarZoom(zoom - ZOOM_PASO));
  if (zoomMas) zoomMas.addEventListener("click", () => cambiarZoom(zoom + ZOOM_PASO));
  if (zoomReset) zoomReset.addEventListener("click", restablecerZoom);
  if (lienzo) {
    lienzo.addEventListener("wheel", (evento) => {
      if (evento.ctrlKey || evento.metaKey) {
        evento.preventDefault();
        cambiarZoom(zoom + (evento.deltaY < 0 ? ZOOM_PASO : -ZOOM_PASO));
      } else if (zoom > 1) {
        // Con la página ampliada la rueda desplaza la imagen, no cambia de página.
        evento.preventDefault();
        panY -= evento.deltaY;
        panX -= evento.shiftKey ? evento.deltaY : 0;
        aplicarZoom();
      }
    }, { passive: false });
  }
  if (lienzo) {
    lienzo.addEventListener("pointerdown", (evento) => {
      if (zoom <= 1 || evento.button !== 0) return;
      if (evento.target.closest("a, button, input, select, textarea, [contenteditable], [role='button']")) return;
      punteroZoom = { id: evento.pointerId, x: evento.clientX, y: evento.clientY, px: panX, py: panY };
      movioAlArrastrar = false;
      lienzo.setPointerCapture?.(evento.pointerId);
    });
    lienzo.addEventListener("pointermove", (evento) => {
      if (!punteroZoom || evento.pointerId !== punteroZoom.id) return;
      const dx = evento.clientX - punteroZoom.x;
      const dy = evento.clientY - punteroZoom.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) movioAlArrastrar = true;
      panX = punteroZoom.px + dx;
      panY = punteroZoom.py + dy;
      aplicarZoom();
    });
    const soltarPuntero = (evento) => {
      if (!punteroZoom || (evento && evento.pointerId !== punteroZoom.id)) return;
      if (evento && evento.type === "pointerup" && movioAlArrastrar) {
        // Evita que el clic posterior del arrastre cambie los controles.
        setTimeout(() => { movioAlArrastrar = false; }, 0);
      }
      punteroZoom = null;
    };
    lienzo.addEventListener("pointerup", soltarPuntero);
    lienzo.addEventListener("pointercancel", soltarPuntero);
  }

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
  document.addEventListener("fullscreenchange", aplicarZoom);
  if (typeof window.addEventListener === "function") window.addEventListener("resize", aplicarZoom);

  // Chrome auto-oculto. Sin JS la barra se queda visible (degradación honesta).
  document.addEventListener("focusin", () => {
    if (focoEnChrome()) despertarChrome();
  });
  document.addEventListener("focusout", (evento) => {
    if ((barra && barra.contains(evento.target)) || (menu && menu.contains(evento.target))) {
      programaOculto();
    }
    if (menu.hidden || !evento.relatedTarget) return;
    const estabaEnOpciones = evento.target === menuBoton || menu.contains(evento.target);
    const sigueEnOpciones = evento.relatedTarget === menuBoton || menu.contains(evento.relatedTarget);
    if (estabaEnOpciones && !sigueEnOpciones) cambiarMenu(false);
  });
  if (typeof setTimeout === "function") programaOculto();

  document.addEventListener("keydown", (evento) => {
    if (evento.defaultPrevented || evento.ctrlKey || evento.altKey || evento.metaKey || evento.isComposing) return;
    const { key, target } = evento;
    if (key === "Escape") {
      if (document.fullscreenElement) return;
      evento.preventDefault();
      if (!menu.hidden) cambiarMenu(false, menu.contains(target));
      else if (raiz.dataset.chrome === "oculto") despertarChrome();
      else window.location.assign(volver);
      return;
    }
    const enLienzo = target === lienzo;
    if (key === "+" || key === "=" || key === "NumpadAdd") {
      if (target === lienzo || target === document.body) { evento.preventDefault(); cambiarZoom(zoom + ZOOM_PASO); return; }
    }
    if (key === "-" || key === "NumpadSubtract") {
      if (target === lienzo || target === document.body) { evento.preventDefault(); cambiarZoom(zoom - ZOOM_PASO); return; }
    }
    if (key === "0" || key === "Numpad0") {
      if (target === lienzo || target === document.body) { evento.preventDefault(); restablecerZoom(); return; }
    }
    if (enLienzo && (key === "f" || key === "h" || key === "m")) {
      evento.preventDefault();
      if (key === "f") alternarPantalla();
      else if (key === "h") alternarChrome();
      else cambiarModo(modo === "ancho" ? "pantalla" : modo === "pantalla" ? "doble" : "ancho");
      return;
    }
    const enFlecha = target === anterior || target === siguiente;
    if (!enLienzo && !enFlecha && target !== document.body) return;
    const siguienteTecla = sentido === "rtl" ? "ArrowLeft" : "ArrowRight";
    const anteriorTecla = sentido === "rtl" ? "ArrowRight" : "ArrowLeft";
    if (key === siguienteTecla || key === "PageDown") { evento.preventDefault(); avanzar(); }
    else if (key === anteriorTecla || key === "PageUp") { evento.preventDefault(); retroceder(); }
    else if (key === " " && !enFlecha) { evento.preventDefault(); evento.shiftKey ? retroceder() : avanzar(); }
    else if (key === "Home") { evento.preventDefault(); ir(1); }
    else if (key === "End") { evento.preventDefault(); ir(total); }
  });

  if (accionesFin) {
    let restaurarFoco = false;
    document.addEventListener("htmx:before:swap", (evento) => {
      if (evento.detail.tasks.some((tarea) => tarea.target === accionesFin)) {
        restaurarFoco = accionesFin.contains(document.activeElement);
      }
    });
    accionesFin.addEventListener("htmx:after:swap", (evento) => {
      // HTMX emite el evento desde la diana cuando el formulario se ha sustituido.
      if (evento.target !== accionesFin) return;
      const control = accionesFin.querySelector("[data-lector-leido]");
      if (restaurarFoco && document.activeElement === document.body && !fin.hidden) {
        (control || document.getElementById("fin-titulo")).focus();
      }
      restaurarFoco = false;
      if (control) anunciar(control.dataset.lectorLeido === "true" ? "Guardado: Leído." : "Guardado: En lectura.");
    });
  }

  let toqueInicio = null;
  const distanciaToques = (a, b) => Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
  lienzo.addEventListener("touchstart", (evento) => {
    if (evento.target.closest("a, button, input, select, textarea, [contenteditable], [role='button']")) {
      toqueInicio = null; pinchZoom = null; return;
    }
    if (evento.touches.length === 2) {
      toqueInicio = null;
      pinchZoom = { distancia: distanciaToques(evento.touches[0], evento.touches[1]),
                    zoom: zoom };
      evento.preventDefault();
      return;
    }
    if (evento.touches.length !== 1) { toqueInicio = null; return; }
    const t = evento.touches[0];
    const rect = lienzo.getBoundingClientRect();
    toqueInicio = { x: t.clientX, y: t.clientY, izquierda: rect.left, ancho: rect.width,
                    px: panX, py: panY, movido: false };
    if (zoom > 1) evento.preventDefault();
  }, { passive: false });
  lienzo.addEventListener("touchmove", (evento) => {
    if (pinchZoom && evento.touches.length === 2) {
      evento.preventDefault();
      const distancia = distanciaToques(evento.touches[0], evento.touches[1]);
      if (pinchZoom.distancia > 0) cambiarZoom(pinchZoom.zoom * distancia / pinchZoom.distancia);
      return;
    }
    if (!toqueInicio || zoom <= 1 || evento.touches.length !== 1) return;
    evento.preventDefault();
    const t = evento.touches[0];
    const dx = t.clientX - toqueInicio.x;
    const dy = t.clientY - toqueInicio.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) toqueInicio.movido = true;
    panX = toqueInicio.px + dx;
    panY = toqueInicio.py + dy;
    aplicarZoom();
  }, { passive: false });
  lienzo.addEventListener("touchend", (evento) => {
    if (pinchZoom) {
      if (evento.touches.length < 2) pinchZoom = null;
      return;
    }
    if (!toqueInicio || !evento.changedTouches.length) return;
    if (evento.touches.length) { toqueInicio = null; return; }
    const t = evento.changedTouches[0];
    const dx = t.clientX - toqueInicio.x;
    const dy = t.clientY - toqueInicio.y;
    const origen = toqueInicio;
    toqueInicio = null;
    if (zoom > 1) return;  // ampliada: el gesto es para moverse, no para pasar página
    if (Math.abs(dx) >= 50 && Math.abs(dx) > 2 * Math.abs(dy)) {
      evento.preventDefault(); // evita también el clic sintético posterior al gesto
      const adelante = (dx < 0) !== (sentido === "rtl");
      adelante ? avanzar() : retroceder();
      return;
    }
    if (Math.abs(dx) > 12 || Math.abs(dy) > 12) return;
    evento.preventDefault(); // el toque ya se ha atendido; no repetirlo como clic
    const zona = (t.clientX - origen.izquierda) / origen.ancho;
    if (zona < 0.3) (sentido === "rtl" ? avanzar : retroceder)();
    else if (zona > 0.7) (sentido === "rtl" ? retroceder : avanzar)();
    else alternarChrome();
  }, { passive: false });
  lienzo.addEventListener("touchcancel", () => { toqueInicio = null; pinchZoom = null; });
  lienzo.addEventListener("click", (evento) => {
    if (movioAlArrastrar) { movioAlArrastrar = false; return; }
    // Las flechas y otros controles conservan su comportamiento nativo.
    if (evento.button !== 0 || zoom > 1 || ![lienzo, paginas, imagen, imagenB].includes(evento.target)) return;
    const rect = lienzo.getBoundingClientRect();
    const zona = (evento.clientX - rect.left) / rect.width;
    if (zona >= 0.3 && zona <= 0.7) alternarChrome();
  });

  if (imagen.complete && imagen.naturalWidth) decidirPareja();
  aplicarZoom();
  pinta();
})();
