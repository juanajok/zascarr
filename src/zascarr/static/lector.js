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
  // Solo los botones: la raíz también lleva data-modo y, tomada por botón, cerraba Opciones al
  // abrirla (el clic subía hasta ella y repetía cambiarModo) y recibía aria-pressed (#1118).
  const BOTONES_MODO = "button[data-modo]";
  const menuBoton = document.getElementById("lector-menu-boton");
  const menu = document.getElementById("lector-menu");
  const barra = document.getElementById("lector-barra");
  const asa = document.getElementById("lector-asa");
  const resultado = document.getElementById("lector-resultado");
  const fin = document.getElementById("fin");
  const accionesFin = document.getElementById("fin-acciones");
  const tituloFin = document.getElementById("fin-titulo");
  const quedarmeFin = document.getElementById("fin-quedarme");
  const portadaFin = document.getElementById("fin-portada");
  // BL-LEC3 decisión D (#826): la página de fin solo se abre con intención de avanzar desde la
  // última página. Al llegar no se muestra nada.
  let finAbierto = false;
  let chromeAntesDeFin = false;
  let portadaFinPedida = false;
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
  // El lector abre ajustado a la pantalla; el resto de modos siguen disponibles.
  let modo = "pantalla";
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
  const textoPaginas = (visibles) => (visibles.length > 1
    ? `Páginas ${visibles[0]}–${visibles[1]} de ${total}`
    : `Página ${visibles[0]} de ${total}`);
  const enUltimaPagina = () => {
    const visibles = paginasVisibles();
    return visibles[visibles.length - 1] >= total;
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
    const paginasLeidas = textoPaginas(visibles);
    if (contador.textContent !== paginasLeidas) contador.textContent = paginasLeidas;
    const enInicio = visibles[0] <= 1;
    const enFin = visibles[visibles.length - 1] >= total;
    // Las flechas izquierda/derecha cambian de significado en RTL: el botón
    // izquierdo avanza cuando se lee de derecha a izquierda. En la última página el avance sigue
    // operativo y se llama «Ver el final»: abre la página de fin (no hay página N+1).
    const etiquetaAvance = enFin ? "Ver el final" : "Página siguiente";
    anterior.setAttribute("aria-disabled",
      String(sentido === "rtl" ? false : enInicio));
    siguiente.setAttribute("aria-disabled",
      String(sentido === "rtl" ? enInicio : false));
    anterior.setAttribute("aria-label",
      sentido === "rtl" ? etiquetaAvance : "Página anterior");
    siguiente.setAttribute("aria-label",
      sentido === "rtl" ? "Página anterior" : etiquetaAvance);
    raiz.dataset.modo = modo;
    raiz.dataset.sentido = sentido;
    raiz.dataset.desplazamiento = String(desplazamiento);
    raiz.dataset.pagina = String(pagina);
    menuBoton.setAttribute("aria-expanded", String(!menu.hidden));
    desplazar.hidden = modo !== "doble";
    for (const boton of document.querySelectorAll(BOTONES_MODO)) {
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

  const anunciar = (mensaje) => {
    if (resultado && resultado.textContent !== mensaje) resultado.textContent = mensaje;
  };
  // La portada del siguiente número se pide SOLO al abrir la página de fin y una sola vez por
  // carga; el HTML inicial no lleva `src`. Si falla, se oculta la imagen y queda el marcador de
  // `ui.portada` (sin mensaje de error ni imagen rota).
  const hidratarPortadaFin = () => {
    if (portadaFinPedida || !portadaFin) return;
    const url = portadaFin.dataset ? portadaFin.dataset.portadaUrl : null;
    const marco = typeof portadaFin.querySelector === "function"
      ? portadaFin.querySelector(".portada") : null;
    if (!url || !marco || typeof document.createElement !== "function") return;
    portadaFinPedida = true;
    const img = document.createElement("img");
    img.alt = "";
    img.decoding = "async";
    img.addEventListener("error", () => {
      img.hidden = true;
      img.removeAttribute("src");
    });
    img.src = url;
    if (typeof marco.appendChild === "function") marco.appendChild(img);
  };
  const abrirFin = () => {
    if (!fin || finAbierto) return;
    finAbierto = true;
    // La barra flotante taparía el título en móviles: en la página de fin se oculta y se
    // restaura al volver (solo si estaba visible antes de entrar).
    chromeAntesDeFin = raiz.dataset.chrome === "oculto";
    ocultarBarraInmersiva(false);
    fin.hidden = false;
    sincronizarAsa();
    if (typeof fin.scrollTop === "number") fin.scrollTop = 0;
    paginas.hidden = true;
    if (lienzo) lienzo.hidden = true;
    if (anterior) anterior.hidden = true;
    if (siguiente) siguiente.hidden = true;
    hidratarPortadaFin();
    if (tituloFin && typeof tituloFin.focus === "function") {
      tituloFin.focus({ preventScroll: true });
    }
    anunciar("Fin del número.");
  };
  const cerrarFin = () => {
    if (!fin || !finAbierto) return;
    finAbierto = false;
    // Primero se recupera la página (y el foco) y solo después se oculta el fin: nunca se oculta
    // #fin con el foco dentro (FR-22).
    paginas.hidden = false;
    if (anterior) anterior.hidden = false;
    if (siguiente) siguiente.hidden = false;
    if (lienzo) {
      lienzo.hidden = false;
      if (typeof lienzo.focus === "function") lienzo.focus({ preventScroll: true });
    }
    fin.hidden = true;
    if (!chromeAntesDeFin) despertarChrome();
    else sincronizarAsa();
    anunciar(`${textoPaginas(paginasVisibles())}.`);
  };

  const ir = (n) => {
    if (finAbierto) return;
    const destino = Math.max(1, Math.min(total, n));
    if (destino === pagina) return;
    pagina = destino;
    if (zoom > 1) { panX = 0; panY = 0; }
    pinta();
    guarda();
  };
  const avanzar = () => {
    if (finAbierto) return;
    if (enUltimaPagina()) { abrirFin(); return; }
    if (modo === "doble" && paginaBVisible) ir(pagina + 2);
    else ir(pagina + 1);
  };
  const retroceder = () => {
    if (finAbierto) { cerrarFin(); return; }
    if (modo === "doble" && paginaBVisible) ir(pagina - 2);
    else ir(pagina - 1);
  };
  let temporizadorChrome = null;
  const focoEnChrome = () => {
    const activo = document.activeElement;
    if (!activo) return false;
    return (barra && barra.contains(activo)) || (menu && menu.contains(activo));
  };
  const esVisible = (elemento) => {
    for (let nodo = elemento; nodo; nodo = nodo.parent) {
      if (nodo.hidden) return false;
    }
    if (elemento.offsetParent === null) return elemento === lienzo || elemento === asa;
    return true;
  };
  const enfocablesVisibles = () => {
    if (!raiz.querySelectorAll) return [];
    const selector = "a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex='-1'])";
    return Array.from(raiz.querySelectorAll(selector)).filter(esVisible);
  };
  const primerControlBarra = () => {
    if (!barra || !barra.querySelectorAll) return null;
    const selector = "a[href], button, input, select, textarea, summary";
    return Array.from(barra.querySelectorAll(selector)).find(esVisible) || null;
  };
  const sincronizarAsa = () => {
    if (!asa) return;
    asa.hidden = !(raiz.dataset.chrome === "oculto" && !finAbierto);
  };
  const ponerChrome = (oculto) => {
    raiz.dataset.chrome = oculto ? "oculto" : "";
    sincronizarAsa();
  };
  const revelarYEnfocarPrimero = () => {
    ponerChrome(false);
    const primero = primerControlBarra();
    if (primero && typeof primero.focus === "function") {
      primero.focus({ preventScroll: true });
    } else if (barra && typeof barra.focus === "function") {
      barra.focus({ preventScroll: true });
    }
    return primero;
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
      ponerChrome(true);
    }, 3000);
  };
  const despertarChrome = () => {
    ponerChrome(false);
    programaOculto();
  };
  const ocultarBarraInmersiva = (enfocar = true) => {
    if (menu && !menu.hidden) {
      menu.hidden = true;
      menuBoton.setAttribute("aria-expanded", "false");
    }
    ponerChrome(true);
    if (temporizadorChrome !== null && typeof clearTimeout === "function") {
      clearTimeout(temporizadorChrome);
    }
    temporizadorChrome = null;
    if (enfocar && lienzo && typeof lienzo.focus === "function") {
      lienzo.focus({ preventScroll: true });
    }
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
    if (raiz.dataset.chrome === "oculto") {
      ponerChrome(false);
      programaOculto();
    } else {
      ponerChrome(true);
      if (temporizadorChrome !== null && typeof clearTimeout === "function") {
        clearTimeout(temporizadorChrome);
      }
      temporizadorChrome = null;
    }
  };
  if (asa) {
    asa.addEventListener("click", () => {
      if (raiz.dataset.chrome !== "oculto" || finAbierto) return;
      revelarYEnfocarPrimero();
    });
  }
  const cambiarModo = (nuevo) => {
    if (nuevo !== "ancho" && nuevo !== "pantalla" && nuevo !== "doble") return;
    modo = nuevo;
    if (modo !== "doble") { desplazamiento = 0; paginaBVisible = false; }
    else decidirPareja();
    try { window.localStorage.setItem("zascarr.lector.modo", modo); } catch (_) { /* igual */ }
    if (modo === "pantalla") ocultarBarraInmersiva();
    else {
      ponerChrome(false);
      programaOculto();
    }
    pinta();
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
  // Cierre propio dentro del panel (#1118): con el panel más alto que la pantalla el botón
  // «Opciones» sale de la vista al desplazarlo, y no debe ser el único modo de cerrar.
  const menuCerrar = document.getElementById("lector-menu-cerrar");
  if (menuCerrar) menuCerrar.addEventListener("click", () => cambiarMenu(false, true));
  for (const boton of document.querySelectorAll(BOTONES_MODO)) {
    boton.addEventListener("click", () => cambiarModo(boton.dataset.modo));
  }
  desplazar.addEventListener("click", () => {
    desplazamiento = desplazamiento === 0 ? 1 : 0;
    pinta();
  });
  botonSentido.addEventListener("click", cambiarSentido);
  if (quedarmeFin) quedarmeFin.addEventListener("click", cerrarFin);
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
  const alCambiarPantalla = () => {
    if (document.fullscreenElement) {
      ocultarBarraInmersiva();
    } else if (finAbierto) {
      // Salir de fullscreen con la página de fin abierta no debe hacer parpadear la barra
      // sobre su título durante los 3 s del auto-ocultado.
      ponerChrome(true);
      if (temporizadorChrome !== null && typeof clearTimeout === "function") {
        clearTimeout(temporizadorChrome);
      }
      temporizadorChrome = null;
    } else {
      ponerChrome(false);
      programaOculto();
    }
    aplicarZoom();
  };
  document.addEventListener("fullscreenchange", alCambiarPantalla);
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
    const relacionado = evento.relatedTarget;
    if (relacionado === document.body) return;  // texto no interactivo: no cierra ni roba foco
    const esEnfocable = relacionado === menuBoton || relacionado === lienzo
      || (typeof relacionado.closest === "function"
          && relacionado.closest("a[href], button, input, select, textarea, summary, [tabindex]"));
    if (!esEnfocable) return;
    const estabaEnOpciones = evento.target === menuBoton || menu.contains(evento.target);
    const sigueEnOpciones = relacionado === menuBoton || menu.contains(relacionado);
    if (estabaEnOpciones && !sigueEnOpciones) cambiarMenu(false);
  });
  if (menu) {
    const noInteractivo = (elemento) => !(elemento && typeof elemento.closest === "function"
      && elemento.closest("a[href], button, input, select, textarea, summary, label, [contenteditable], [role='button']"));
    // Solo puntero/ratón: `touchstart.preventDefault` bloquearía el desplazamiento del panel.
    ["pointerdown", "mousedown"].forEach((tipo) => menu.addEventListener(tipo, (evento) => {
      if (noInteractivo(evento.target) && evento.preventDefault) evento.preventDefault();
    }, { passive: false }));
  }
  if (modo === "pantalla") ocultarBarraInmersiva(false);
  else if (typeof setTimeout === "function") programaOculto();

  document.addEventListener("pointermove", (evento) => {
    // Con la barra oculta, acercarse a la franja superior la muestra; en la página de fin
    // no se muestra para no tapar su título (se sale con «Quedarme»/Esc).
    if (!finAbierto && raiz.dataset.chrome === "oculto" && evento.clientY <= 90) {
      despertarChrome();
    }
  }, { passive: true });
  document.addEventListener("keydown", (evento) => {
    if (evento.defaultPrevented || evento.ctrlKey || evento.altKey || evento.metaKey || evento.isComposing) return;
    const { key, target } = evento;
    if (key === "Tab") {
      const menuAbierto = !!menu && !menu.hidden;
      const activo = document.activeElement;
      if (menuAbierto && menu.contains(activo)) return;  // el focusout/cierre deciden al salir
      const lista = enfocablesVisibles();
      if (!lista.length) return;
      const dentro = raiz.contains ? raiz.contains(activo) : activo === raiz;
      if (!dentro || activo === document.body || activo === lienzo) {
        evento.preventDefault();
        if (raiz.dataset.chrome === "oculto") ponerChrome(false);
        const destino = evento.shiftKey ? lista[lista.length - 1] : lista[0];
        if (destino && typeof destino.focus === "function") destino.focus({ preventScroll: true });
        return;
      }
      const indice = lista.indexOf(activo);
      if (indice === -1) {
        evento.preventDefault();
        const destino = evento.shiftKey ? lista[lista.length - 1] : lista[0];
        if (destino && typeof destino.focus === "function") destino.focus({ preventScroll: true });
      } else if (!evento.shiftKey && indice === lista.length - 1) {
        evento.preventDefault();
        if (lista[0] && typeof lista[0].focus === "function") lista[0].focus({ preventScroll: true });
      } else if (evento.shiftKey && indice === 0) {
        evento.preventDefault();
        const ultimo = lista[lista.length - 1];
        if (ultimo && typeof ultimo.focus === "function") ultimo.focus({ preventScroll: true });
      }
      return;
    }
    const enFinPagina = !!fin && !fin.hidden
      && (target === fin || (typeof fin.contains === "function" && fin.contains(target)));
    if (key === "Escape") {
      if (document.fullscreenElement) return;  // Esc es del navegador (sale de pantalla completa)
      evento.preventDefault();
      if (!menu.hidden) cambiarMenu(false, menu.contains(target));
      else if (finAbierto) cerrarFin();        // en la página de fin, Esc vuelve; no cierra el lector
      else if (raiz.dataset.chrome === "oculto") despertarChrome();
      else window.location.assign(volver);
      return;
    }
    const enLienzo = target === lienzo;
    // WCAG 2.1.4: los atajos de un carácter (+ − 0 f h m) solo actúan con el foco en la zona de
    // lectura; con el foco en el cuerpo o en otro control no hacen nada (#1119).
    if (enLienzo && (key === "+" || key === "=" || key === "NumpadAdd")) {
      evento.preventDefault(); cambiarZoom(zoom + ZOOM_PASO); return;
    }
    if (enLienzo && (key === "-" || key === "NumpadSubtract")) {
      evento.preventDefault(); cambiarZoom(zoom - ZOOM_PASO); return;
    }
    if (enLienzo && (key === "0" || key === "Numpad0")) {
      evento.preventDefault(); restablecerZoom(); return;
    }
    if (enLienzo && (key === "f" || key === "h" || key === "m")) {
      evento.preventDefault();
      if (key === "f") alternarPantalla();
      else if (key === "h") alternarChrome();
      else cambiarModo(modo === "ancho" ? "pantalla" : modo === "pantalla" ? "doble" : "ancho");
      return;
    }
    const enFlecha = target === anterior || target === siguiente;
    if (enFinPagina) {
      // FR-20: dentro de la página de fin, Espacio/Enter sobre un control no se interceptan y se
      // puede salir con Tab. Las teclas de avance, Home y End no hacen nada; las de vuelta, sí.
      const interactivo = target && typeof target.closest === "function"
        && target.closest("a, button, input, select, textarea, [contenteditable], [role='button']");
      if (interactivo) return;
      const volverTecla = sentido === "rtl" ? "ArrowRight" : "ArrowLeft";
      if (key === volverTecla || key === "PageUp" || (key === " " && evento.shiftKey)) {
        evento.preventDefault();
        cerrarFin();
      }
      return;
    }
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
      // Deseados: el recambio se limita a #fin-deseo (no borra la vuelta); si el foco se quedó en
      // el body al desaparecer el botón, vuelve a «Quedarme» y el resultado se anuncia (FR-15).
      if (evento.target && evento.target !== accionesFin && evento.target.id === "fin-deseo") {
        if (document.activeElement === document.body) {
          const destino = quedarmeFin || document.getElementById("fin-titulo");
          if (destino && typeof destino.focus === "function") destino.focus({ preventScroll: true });
        }
        const texto = (evento.target.textContent || "").trim();
        if (texto) anunciar(texto);
        return;
      }
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
                    px: panX, py: panY, movido: false, franja: t.clientY <= 44 };
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
    // UATP-03 D-1: la franja superior (44 px) revela sin cambiar de página; solo un toque sin
    // desplazamiento. Los deslizamientos ya se han resuelto arriba.
    if (origen.franja && raiz.dataset.chrome === "oculto") {
      despertarChrome();
      return;
    }
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

  // FR-21: en la página de fin, el deslizamiento o toque de retroceso vuelve a la última página;
  // el de avance no hace nada y los controles reciben su toque con normalidad. El zoom no impide
  // volver (la página de fin no se amplía).
  if (fin) {
    let toqueFin = null;
    const enControl = (elemento) => elemento && typeof elemento.closest === "function"
      && elemento.closest("a, button, input, select, textarea, [contenteditable], [role='button']");
    fin.addEventListener("touchstart", (evento) => {
      if (enControl(evento.target) || !evento.touches || evento.touches.length !== 1) {
        toqueFin = null; return;
      }
      const t = evento.touches[0];
      toqueFin = { x: t.clientX, y: t.clientY };
    }, { passive: true });
    fin.addEventListener("touchend", (evento) => {
      if (!toqueFin || !evento.changedTouches || !evento.changedTouches.length) {
        toqueFin = null; return;
      }
      if (evento.touches && evento.touches.length) { toqueFin = null; return; }
      const t = evento.changedTouches[0];
      const dx = t.clientX - toqueFin.x;
      const dy = t.clientY - toqueFin.y;
      toqueFin = null;
      if (Math.abs(dx) >= 50 && Math.abs(dx) > 2 * Math.abs(dy)) {
        evento.preventDefault();
        const adelante = (dx < 0) !== (sentido === "rtl");
        if (!adelante) cerrarFin();
        return;
      }
      if (Math.abs(dx) > 12 || Math.abs(dy) > 12) return;
      // Toque corto: solo la zona de retroceso vuelve (en RTL, la derecha).
      const rect = typeof fin.getBoundingClientRect === "function"
        ? fin.getBoundingClientRect() : null;
      if (!rect || !rect.width) return;
      const zona = (t.clientX - rect.left) / rect.width;
      const zonaVuelta = sentido === "rtl" ? zona > 0.7 : zona < 0.3;
      if (zonaVuelta) { evento.preventDefault(); cerrarFin(); }
    }, { passive: false });
    fin.addEventListener("touchcancel", () => { toqueFin = null; });
  }

  if (imagen.complete && imagen.naturalWidth) decidirPareja();
  aplicarZoom();
  pinta();
})();
