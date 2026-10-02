# V3 — shell nueva: menú agrupado, barra inferior y contadores

Historia **V3** de la Épica V. Primer uso real de los componentes de V2 en una pieza compartida: `base.html`
pasa de la barra superior a un menú lateral (escritorio) y una barra inferior (móvil), con el **mismo
marcado**. Datos del menú en `src/zascarr/web/menu.py` (una sola fuente: escritorio, barra inferior y
«Más» salen de la misma lista); presentación en `static/web.css` §3b; macro `ui.menu` en
`templates/_componentes.html`; fragmento de contadores en `web/navegacion.py`.

## Qué cambia para el coleccionista
- Menú agrupado: **Mi colección** (Inicio, Por revisar, Biblioteca, Duplicados), **Añadir** (Descubrir,
  Deseados), **Sistema** (Estado, Ajustes). **Las URL no cambian** (`/estado` sigue en `/estado`).
- Nombres (U7): *Pendientes* → **Por revisar**, *Lista de deseos* → **Deseados**, *Mi biblioteca* →
  **Duplicados**, *Dashboard* → **Inicio**, *Tu biblioteca* → **Biblioteca**. `<title>` y `<h1>` coinciden con
  el menú, y la ficha de serie ya tiene título.
- Contadores en el menú (**6** por revisar, **5** deseados) y un punto en **Estado** si el servicio está
  abierto sin contraseña (A11). Antes «Biblioteca» enlazaba al panel y la rejilla real no estaba en el menú.
- En móvil, una barra inferior con **Inicio, Revisar, Deseados, Estado y Más**; «Más» abre el resto
  (Biblioteca, Duplicados, Descubrir, Ajustes).

## Decisiones de diseño (y por qué)
- **Cuatro entradas + «Más» (no las cinco de la maqueta).** Con el texto mínimo de 14 px (V1), seis columnas no
  caben a 320 px. «Más» es un `<details>` nativo: sin JavaScript, operable con Enter y Espacio.
- **Las entradas de «Más» salen dos veces en el DOM** (barra y panel) y CSS muestra solo una por tamaño; la
  oculta no existe para el lector de pantalla. Por eso el HTML tiene **dos** `aria-current` en esas páginas y el
  navegador **uno visible** (comprobado, ver abajo). Solo las entradas principales llevan contador, así que ningún
  `id` se repite.
- **Los enlaces nunca dependen del fragmento.** El menú lleva sus ocho enlaces en el HTML; los contadores son
  marcadores `hidden`. El sondeo es `hx-get` + `hx-trigger="load, every 30s"` + **`hx-swap="none"`** y el fragmento
  responde solo con intercambios **fuera de banda** sobre `#cnt-*`: no contiene ningún enlace ni puede reemplazar uno.
- **`204 No Content` ante cualquier fallo** (htmx 4 intercambia todo salvo 204/304): BD caída con la app en marcha
  (que en `/ui/*` es un `500` de texto plano), arranque degradado (E6) y sesión caducada.
- **El fragmento NO es ruta de diagnóstico.** Esas se sirven sin comprobar la sesión. Sin sesión el middleware
  responde `204` vacío (no redirige: htmx seguiría la redirección e intercambiaría la página de acceso) y la BD ni
  se consulta. El resto de `/ui/*` sigue dando `303 → /login` (A6) y `503` de E6 (E6).
- **El punto de Estado es solo la señal de seguridad de A11** (`seguridad.atencion`): es la única señal de
  atención barata y exacta sin llamar a servicios externos. V9 la amplía a «el peor de los parciales».

## Verificación
- **Pruebas** (sin navegador): `tests/test_web_navegacion.py` (122 casos: datos del menú, HTML de la macro,
  enlaces fuera de cualquier elemento htmx, las 8 pantallas —título, `<h1>`, `aria-current`, salto, un solo `nav`—,
  fragmento con datos/cero/>999/cualquier fallo, sesión, arranque degradado, filtro de los recuentos compartido con
  las listas, CSS). Suite completa verde.
- **Navegador real** (Chrome 154, entorno aislado de V0 con la imagen de esta rama; `verificar.py` + `ensayo.sh`;
  resultados en `verificar-*.json`):

| Caso | Resultado |
|---|---|
| Menú, 8 pantallas × escritorio / 390 / 320 px | 8 enlaces siempre; **un `aria-current` visible** en cada una; **sin desborde horizontal** |
| Acceso móvil a las 4 secciones de «Más» (390 y 320 px) | **8/8 alcanzadas**, «Más» marcado como activo |
| Teclado | 1.º foco = enlace de salto → lleva el foco a `<main>`; luego marca y 8 entradas en orden; foco visible (contorno 3 px); «Más» se abre/cierra con Enter y Espacio y Tab entra en su panel |
| Sondeo | 1 petición al cargar, **2 a los ~35 s** |
| Red: fragmento bloqueado | menú **íntegro** (8 enlaces), contadores ocultos |
| **BD caída con la página ya cargada** | siguiente sondeo **`204`**; **contadores y 8 enlaces conservados**; la página no cambia |
| **Arranque sin BD** (E6) | `/estado` **200** con menú completo; fragmento **`204`** vacío; `/ui/` sigue en `503` |
| **Sesión caducada** (cookies borradas en mitad del uso) | sondeo **`204`**, sin redirigir, página y enlaces sin cambios; navegar sí lleva a `/login` |
| Login / logout | página de acceso sin menú (no cambia); botón *Cerrar sesión* solo con la autenticación activa; sale a `/login` |
| Sin cookie (curl) | fragmento `204`, 0 bytes, sin `Location`; `/ui/pendientes` `303 → /login` |

- **Coste del sondeo** (riesgo que pedía medir la ficha): dos `COUNT`. Con **50.000 ficheros** (≈33× una biblioteca
  de 1.500) el fragmento tarda **46 ms de mediana, 52 ms p90** en un equipo de desarrollo, y 14 ms con la BD de
  ensayo; `EXPLAIN ANALYZE` del recuento de pendientes: 26 ms. **No medido en la Pi.**
- **Antes / después**: `antes--*.png` (código de `main`) y `despues--*.png`, mismo estado de datos. Las páginas
  móviles son ~100 px más cortas (la barra superior que se partía en varias líneas ocupa ya una sola); Ajustes de
  escritorio es más alta (2.183 → 2.775 px) porque sus tarjetas pasan de 4 a 3 columnas al restar la barra lateral.

## Lo que la verificación encontró y se corrigió (no estaba en la ficha)
- **El contenido se encogía** en la rejilla (`margin: 0 auto` en un hijo de CSS Grid impide que se estire): el Inicio
  quedaba en 736 px y el resto en 1.036 a 1.280 de ancho. Corregido (`.app > .content { width: 100% }`) y con prueba.
- **Contador sobre el icono** en la barra inferior y **«Deseados» (66 px) en una celda de 64** a 320 px: columnas
  `minmax(max-content, 1fr)` y desplazamiento del contador.
- **Herramienta de captura:** `scrollIntoView` es asíncrono con `scroll-behavior: smooth` y el caso 409 hacía clic en
  una posición vieja; ahora el desplazamiento es instantáneo. Mi teclado sintético tampoco abría `<summary>`
  (faltaba el carácter de la pulsación): era de la herramienta, no del producto.

## Límites
- Un navegador (Chrome 154) y un equipo; **sin probar en la Pi ni en Firefox/Safari**. `display: contents` en
  `.nav-grupo` (barra inferior) y `<details>` se apoyan en navegadores recientes.
- El punto de Estado solo refleja seguridad (V9 lo amplía).
- `/ui/*` con la BD caída en marcha sigue dando el `500` de texto plano (defecto operativo aparte, ver BACKLOG):
  solo el fragmento está blindado.
- Las páginas con desborde preexistente (ficha de serie 413 px, aviso legal en texto 409 px) no cambian: V13.
- Las glifos del menú (`⌂ ✎ ▤ ⚖ ⌕ ★ ♥ ⚙`) dependen de las fuentes del sistema; son decorativos (`aria-hidden`).
