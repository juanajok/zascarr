# ADR 0005: Migración incremental de la UI a la maqueta

## Estado

**Aceptado** — 2026-10-02 (propuesto el 2026-10-01 en la PR #60, fusionada en `a81aae1`).
Se cierra con la historia V0 de la Épica V (`docs/BACKLOG.md`); el inventario en que se apoya
está en `docs/design/ui-migracion.md`.

## Contexto

Existe una **maqueta navegable** de una UI propuesta (`docs/design/maqueta-ui.html`, derivada de
la revisión de UX de la Épica U): menú lateral agrupado, Inicio guiado, «Por revisar» agrupado con
selección múltiple, Deseados con estados honestos, Estado en lenguaje llano, Ajustes por objetivos
y Duplicados con resumen. La UI actual es Jinja2 + HTMX + `web.css` (ADR-0001), con 28 plantillas
(13 páginas y 15 parciales) y 11 routers.

El inventario (V0) encontró que **la maqueta no es un producto**: simula con JavaScript cosas que
aquí no existen (deshacer tras asignar, progreso de la revisión), usa datos inventados y omite
casos reales (número de issue por archivo, alias, tope de 50 pendientes). También que **dos
supuestos de la épica no se sostenían** (la ruta de Estado y la «página estática `/`») y que
**una pantalla de la maqueta contradice una decisión ya tomada** (el selector de exposición de red
en Ajustes frente a A11 / ADR 0004). Ver §2 del inventario.

El proyecto es de **un solo operador** (el coleccionista), corre en una Raspberry Pi compartida y
mantiene una definición de hecho exigente (pruebas, navegador real contra Postgres real,
reversibilidad). Una migración de UI mal planteada es el tipo de cambio que más fácilmente rompe
contratos HTMX sin que ninguna prueba lo vea.

## Decisión

1. **Migración incremental por capas, sin interruptor de «UI vieja / UI nueva».** Primero los
   cimientos (tokens → componentes → menú), después pantalla a pantalla. Cada historia es **una
   PR** que deja `main` desplegable y se deshace con `git revert` de esa PR. Dos UIs en paralelo
   duplicarían plantillas y pruebas en una app de un solo operador.
2. **Las URL no cambian.** Cambian las **etiquetas** y qué etiqueta cuelga de qué ruta, no las rutas.
   En concreto: `/estado` **se queda en `/estado`** (es una ruta de diagnóstico que debe servirse
   con la base de datos caída, E6), y `/` sigue siendo una redirección a `/ui/`. Cualquier ruta nueva
   (p. ej. el fragmento de contadores del menú) debe declarar cómo se comporta con la BD caída.
3. **No se añade JavaScript propio nuevo.** Lo que la maqueta resuelve con JS se traduce a HTMX o
   CSS, o se **retira o se difiere** (tabla de traducción de la épica). El JS propio que **ya existe**
   (el sondeo de `estado.html`, el `onerror` de la portada de Pendientes) **se retira cuando su
   pantalla se migra**, no antes. *(Redacción corregida respecto a la épica, que decía «cero JS
   propio» como si ya fuera el estado actual.)*
4. **Cero lógica de negocio nueva en las plantillas.** Agrupar, mapear estados o derivar pasos vive
   en funciones **puras** de `services/` con pruebas. Si una pantalla hoy lleva lógica en su
   router (el panel `/ui/`), se **extrae primero**.
5. **Sin migración de base de datos dentro de las historias de UI.** Si una historia necesita
   persistir algo trivial, usa los indicadores de `runtime_settings` (`get_flag`/`set_flag`). **Si una
   garantía de integridad exige esquema** (p. ej. que la auditoría de V6a concluya que hay que
   registrar los movimientos para reconciliarlos tras un fallo), **esa dependencia se separa** en su
   propia historia y PR previa, con migración y ficha, y la historia de UI espera. **No se rebaja
   la garantía para que la historia quepa sin migración**, ni se mete esquema en una PR de interfaz.
   Consecuencia ya aplicada: «Unir duplicadas» (los items manuales de Deseados no tienen unicidad a propósito, D8) queda **fuera de la
   migración**; V8 solo agrupa visualmente.
6. **Puerta de validación (G1).** U10 —probar con 3–5 coleccionistas— se hace **antes** de fusionar
   los dos rediseños de mayor riesgo (V5 y V6b): se puede acertar el problema y no la solución.
7. **La UI informa de lo que no puede cambiar (A11).** Ajustes **muestra** la exposición efectiva
   (`seguridad.exposicion`, `contrasena`, `atencion`) y explica cómo cambiarla (**volver a ejecutar el
   instalador**); **no ofrece** un selector de quién puede entrar, porque el puerto publicado es de
   Docker en el host y la aplicación no puede abrir ni cerrar el suyo (ADR 0004). El campo `base_url`
   de Ajustes se conserva.
8. **Las operaciones destructivas o irreversibles no se maquillan.** Asignar mueve un fichero
   (`safe_move`) y **no hay operación inversa**: la salvaguarda es la confirmación previa, no un
   «Deshacer» que prometa lo que no existe. Ignorar sí es reversible (`review_dismissed`) y se
   ofrece recuperarlo. La asignación en lote exige **auditar antes el patrón mover + sesión viva**
   (`CLAUDE.md` §3.1.2), por lo que V6 se divide en servicio (V6a) y UI (V6b).
9. **Lo que no se ha verificado, no se da por hecho.** El comportamiento de htmx 4.0.0 ante un `4xx`
   **se verificó en la línea base de V0** (Chrome 154, datos sintéticos): intercambia el cuerpo del
   error y deja el JSON en crudo donde estaba la tarjeta (`docs/design/ui-baseline/README.md`).
   Consecuencia de diseño: ninguna ruta `hx-*` nueva devuelve un error como cuerpo JSON; los
   fragmentos de estado devuelven `204`/vacío ante **cualquier** fallo.

## Alternativas descartadas

- **SPA o paso de build de Node** — ya descartado en ADR-0001 y sigue descartado: más RAM y
  superficie en una Pi, y el problema no es de interactividad.
- **Reescritura completa («big bang») o interruptor de UI antigua/nueva** — duplica trabajo y
  pruebas, y la vuelta atrás deja de ser un `git revert`.
- **Copiar la maqueta tal cual como plantillas** — arrastraría sus simulaciones (deshacer tras
  asignar), datos fijos y el selector de exposición contrario al ADR 0004.
- **Un buscador único que fusione la búsqueda local y la externa** — decisión de producto
  cerrada: el Inicio lleva a Descubrir con una entrada principal; Deseados conserva su búsqueda
  local, etiquetada. No se unifican todavía.
- **Cambiar las URL para que coincidan con las etiquetas nuevas** — rompe marcadores, pruebas y los
  enlaces del README, a cambio de nada que el coleccionista vea.

## Consecuencias

- Las historias V1–V14 se pueden fusionar de una en una y revertir de una en una; el orden de
  fusión de la épica cambia solo en que **V6 se divide**: V6a (servicio y auditoría, sin cambio visible)
  puede ir antes de la puerta G1 y V6b (interfaz) después.
- **Asignar sin número no existe**: V6b deja los archivos sin número (o con rango) **pendientes y
  explica por qué**; nunca rellena `1` ni convierte un rango en un número.
- V3 **rompe a propósito** dos pruebas que fijan el menú actual (`<nav class="topnav">` y el enlace
  `/estado`); su ficha debe decir que se actualizan.
- Aparece trabajo que la épica no listaba: extraer las consultas del panel a un servicio (V4), un
  `contar_pendientes()` y un agrupado puro por patrón (V5), recuperar ignorados (V7), un fragmento de
  estado que no dependa de la BD (V9).
- Los tokens de la maqueta **no se copian sin comprobar**: un par de color de la propia maqueta
  (insignia `.badge.hot` en modo oscuro) da 3,38:1 y no pasa la prueba de contraste de V1.

## Referencias

- `docs/design/ui-migracion.md` — inventario, contratos HTMX, maqueta frente a la realidad,
  estimaciones revisadas.
- `docs/design/maqueta-ui.html` — la maqueta (propuesta; **simula** deshacer-tras-asignar, el
  progreso de la revisión y el conmutador de tema).
- `docs/adr/0001-ui-stack.md`, `docs/adr/0004-exposicion-de-red.md`.
- Épica V y Épica U en `docs/BACKLOG.md`.
