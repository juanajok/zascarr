# ADR 0001: Stack de la UI web (Fase 6 / Épicas C y D)

## Estado

Aceptado — 2026-09-21.

## Contexto

El backend (matcher, triage, importer, enricher con tres fuentes, orquestador)
está construido y probado, pero todo lo que existe hoy se opera vía `curl` o
se lee en los logs — salvo el dashboard de estado (E1), que es una única
página HTML autocontenida sin plantillas ni navegación. El propio backlog
(`docs/BACKLOG.md`) concluye que el hueco de producto más grande no es
ningún bug, es la ausencia de una interfaz para "el coleccionista": alguien
que quiere ver su biblioteca, revisar pendientes de clasificar y marcar
series como deseadas sin saber qué es una API REST.

Restricciones del proyecto que condicionan esta decisión:
- Equipo de una persona, sin equipo de frontend dedicado.
- Despliegue en una Raspberry Pi (recursos limitados: CPU, RAM, disco).
- Ya existe una API REST completa (`/api/series`, `/api/wishlist`,
  `/api/health`) que cualquier UI puede consumir.
- El patrón de interacción de las pantallas P0 del backlog (bandeja de
  pendientes de B2, huecos por serie de C2, cola de wishlist de D1) es
  "leer → pulsar → el servidor reacciona → la pantalla se actualiza", no
  edición rica de estado en cliente ni navegación que deba sobrevivir sin
  contacto con el servidor.
- No existían ADRs en el repo antes de este documento: las decisiones de
  arquitectura previas (PostgreSQL sobre SQLite, enrutado del enricher por
  `Series.tradition`) se tomaron pero no se registraron formalmente. Este
  es el primero; recuperar los anteriores queda fuera de este documento.

## Decisión

**Jinja2 servido por el propio FastAPI + HTMX, con Alpine.js para
interactividad puramente de cliente (toggles, modales). Sin build step de
Node ni framework SPA.**

- Un router nuevo bajo el prefijo `/ui` (`src/zascarr/web/`), separado
  del router `/api` existente, que devuelve `HTMLResponse` vía
  `Jinja2Templates`.
- Las plantillas llaman a la misma capa de servicios que ya usa la API
  (`Importer`, `EnrichmentService`, etc.), no una segunda copia de la
  lógica de negocio.
- HTMX vendorizado en `src/zascarr/static/vendor/htmx.min.js` (v4.0.0,
  descargado de la release oficial en GitHub y verificado en un navegador
  real antes de vendorizarlo — ver "Verificación" más abajo), no cargado
  desde un CDN.
- Sin dependencias nuevas de peso: solo `jinja2` (Python puro) se añade a
  `pyproject.toml`. HTMX/Alpine son ficheros estáticos, no paquetes npm.

## Alternativas consideradas

| Opción | Por qué no |
|---|---|
| SPA (React/Vite, como Sonarr o Pulsarr) | Segundo lenguaje y toolchain (Node, build, `node_modules`) que mantener en solitario; CORS y autenticación entre capas API/UI; nada en el backlog P0 necesita que el estado sobreviva a un cambio de ruta sin ida y vuelta al servidor, que es el único caso que justifica una SPA de verdad. |
| SPA Angular (como Kavita) | Mismo argumento que React, agravado: el toolchain de Angular es el más pesado de los tres para un equipo de uno. |
| HTMX vía CDN en vez de vendorizado | La pantalla que más tiene que funcionar cuando algo va mal es precisamente el semáforo de estado (E1); si su JS depende de un CDN externo, se cae justo en el escenario que se supone que diagnostica (red caída, DNS raro). Vendorizar son 36 KB servidos por el propio FastAPI, sin esa dependencia. |
| FastUI / NiceGUI / Reflex (Python puro genera la UI) | Menos control sobre el HTML/CSS final que plantillas Jinja2 explícitas; encajan mejor en herramientas internas que en una interfaz pensada para un usuario final no técnico. |

## Qué se copia de Sonarr (la UX, no el stack)

La estructura de pantallas de Sonarr mapea razonablemente bien sobre el
backlog y sirve de referencia de diseño, no de arquitectura:

- Series Index (tabla/pósters) → Épicas C1/B4.
- Series Details con estado por número → C2 + D1 en una sola pantalla.
- Wanted/Activity → wishlist (`WishlistStatus` ya modelado).
- System/Health → ya construido en E1.
- Calendar → requiere fechas de publicación futuras que el enricher no
  aporta todavía; aparcado como P2.

## Consecuencias

- Toda pantalla nueva del backlog (B2, C1-C4, D1-D4) se construye como
  ruta bajo `/ui/*` con su plantilla y, cuando haga falta interacción
  parcial, un endpoint que devuelve solo el fragmento HTML a intercambiar
  (`hx-get`/`hx-target`/`hx-swap`).
- El dashboard de E1 (`src/zascarr/static/dashboard.html`, servido en
  `/`) se queda como está por ahora: es una página autocontenida que
  funciona. Se migra al layout de `web/` cuando exista una segunda
  pantalla real con la que compartir cabecera/navegación — no antes, para
  no reescribir algo que ya funciona sin necesidad.
- Vendorizar HTMX implica actualizarlo a mano cuando convenga (no hay
  gestor de paquetes JS de por medio); el fichero indica su versión y
  origen en `src/zascarr/static/vendor/README.md`.
- Vía de escape documentada: si alguna pantalla necesita de verdad
  interacción rica en cliente (arrastrar y soltar, edición masiva en
  línea) que HTMX no cubre razonablemente, se monta React *sobre la misma
  API REST* sin tirar nada del backend — la ventaja de haber construido
  la API primero.

## Verificación

HTMX v4.0.0 se descargó desde
`https://raw.githubusercontent.com/bigskysoftware/htmx/v4.0.0/dist/htmx.min.js`
(el tag de release oficial más reciente en GitHub en la fecha de esta
decisión) y se cargó en un navegador real contra un servidor HTTP local
antes de darlo por bueno — comprobando `typeof htmx === "object"` y
`htmx.version === "4.0.0"` sin errores de consola — en vez de confiar
ciegamente en la descarga.
