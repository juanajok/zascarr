# Volver de la ficha a la Biblioteca con su estado (UATP-02 / UXA-08)

> **Estado:** implementada en TDD (task-24, 2026-11-21); pendiente la pasada independiente de
> UI/UX, SecOps y QA y el E2E de navegador (T14, **NOT RUN** si no se ejecuta). **No declara
> cumplida** UATP-02: fija el contrato, los criterios y la evidencia que faltan.
>
> **Insumos:** [#1125 · UXA-08](https://github.com/juanajok/zascarr/issues/1125) (ampliada por
> UATP-02), [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141), el informe de
> Benchmarking de UATP-02 (**task-22**, 2026-11-20; solo lectura, no versionado; veredicto
> **NO PASA**) y el contrato vigente de BL-IT03 (`web/retorno.py`) y BL-IT01/BL-IT02
> (Biblioteca). Benchmark de producto de los filtros:
> [`benchmark-biblioteca-filtros.md`](benchmark-biblioteca-filtros.md); retorno a colección:
> [`benchmark-deep-dive-colecciones-2026-11-14.md`](benchmark-deep-dive-colecciones-2026-11-14.md)
> (§5); procedimiento y vocabulario: [`benchmark-referencias.md`](benchmark-referencias.md).
>
> **Único escritor de este documento:** SPEC.writer. No toca código, tests ni otras docs; la
> implementación es una tarea aparte (TDD).
>
> **Referencias de línea:** las de este documento corresponden a `origin/main` =
> `18e883e9` (2026-11-20), la base sobre la que debe implementarse.

## 1. Problema y resultado esperado

**Problema (verificado en `main` por task-22, veredicto NO PASA):**

| # | Hallazgo | Evidencia |
|---|---|---|
| P-1 | La allowlist de retorno tiene **7** parámetros; la ruta `/ui/biblioteca` acepta **22** (además de `puntuacion`). Un solo filtro moderno (`orden`, `author_id`, `leido`, `densidad`, `modo`, `naturaleza`, `formato`, `etiquetas`, `anio_desde`…) hace que se **rechace la URL entera**, incluidos `q`, `vista` y `page` | [`web/retorno.py:16`](../../src/zascarr/web/retorno.py:16) frente a [`web/library.py:840`](../../src/zascarr/web/library.py:840) |
| P-2 | La generación de la URL y el ancla `#serie-<uuid>` son correctas; la tarjeta enfoca/desplaza. La **fila de la vista lista no enfoca** (`id` en un `<tr>` no enfocable) | [`_rejilla_biblioteca.html:115`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:115) y `:140` |
| P-3 | Si la tarjeta **ya no existe** (serie filtrada, otra página, otro orden), no hay foco: el ancla no apunta a nada y el foco se queda en `BODY` con scroll 0 | mismo archivo; [`series_detail.html:21`](../../src/zascarr/web/templates/series_detail.html:21) |
| P-4 | Colecciones conserva el **destino** pero no el **estado**: el enlace a la ficha lleva solo `/ui/colecciones/<uuid>` y la allowlist prohíbe query; se pierden `q`, `tradicion`, `vista` y `pagina` | [`coleccion_detalle.html:58`](../../src/zascarr/web/templates/coleccion_detalle.html:58) y `:81`; [`web/retorno.py:50`](../../src/zascarr/web/retorno.py:50) |
| P-5 | `volver_segura` acepta `///ui/biblioteca` (el navegador lo resuelve como host `ui`), nombres de parámetro **repetidos** y espacios iniciales; no aplica el endurecimiento ya decidido en UATP-01 para `volver_legal` (`//`, `%` en ruta, `%2e%2e`, barra invertida, controles) | [`web/retorno.py:33`](../../src/zascarr/web/retorno.py:33); `uatp01-retorno-legal.md` §3.3 |
| P-6 | La documentación de la Biblioteca está desfasada: el inventario de rutas/parámetros no refleja los 22 reales y el retorno a colección está documentado «sin query» | [`ui-migracion.md:220`](ui-migracion.md:220); [`benchmark-deep-dive-colecciones-2026-11-14.md:93`](benchmark-deep-dive-colecciones-2026-11-14.md:93) |

**Resultado esperado:** desde una ficha abierta en la Biblioteca, «Volver» devuelve a la
**misma** vista: búsqueda, chips, resultados, orden, vista, página, densidad/modo y etiquetas
(estado que vive en la URL), con la **misma tarjeta o fila enfocada** y visible; si esa serie ya
no está en la página que se restaura, el foco cae en la **rejilla de resultados** (posición
predecible), no en `BODY`. Todo **sin JavaScript nuevo**, sin sesión, cookie ni historial
paralelo, y sin que un valor manipulado pueda sacar la navegación del propio servidor. Desde
Colecciones, el retorno conserva el destino **y** su estado (`q`, `tradicion`, `vista`,
`pagina`).

## 2. Alcance / no alcance

**Dentro:**

| Pieza | Cambio |
|---|---|
| `web/library.py` | Allowlist **derivada de la ruta** `index` (una sola fuente) y función pública de validación canónica (basada en `_leer_filtros` + `_qs`). `index` gana `foco` y calcula si el objetivo está en la página. |
| `web/retorno.py` | `url_de_ficha` añade `foco`; `volver_segura` se endurece y valida el estado canónico de Biblioteca y de Colección; conserva fragmento. |
| `web/colecciones.py` | URL de retorno a la colección con su estado, construida en el servidor a partir de `_url_ficha`. |
| `web/templates/_rejilla_biblioteca.html` | `autofocus` en la tarjeta/fila objetivo; `tabindex="-1"` en la fila de lista objetivo. |
| `web/templates/biblioteca.html` | `#rejilla` enfocable cuando el objetivo no está en la página. |
| `web/templates/coleccion_detalle.html` | Usar la URL de retorno construida por el router (tarjetas y lista). |
| `static/web.css` | Anillo de foco visible para tarjeta, fila y `#rejilla` también cuando el foco es programático (`autofocus`). |
| `tests/test_web_retorno.py`, `test_web_library.py`, `test_web_series.py`, `test_web_colecciones.py`, `test_ux_bib_1058.py`, `test_log_acceso.py` | Casos §7; `foco` en el inventario de parámetros de query. |
| Documentación | §9. |

**Fuera:** JavaScript nuevo o cambios de los `biblioteca-*.js` existentes; persistir estado en
sesión/cookie/BD; `Atrás` como mecanismo (el contrato no depende de `history`); scroll exacto en
píxeles; acciones de ficha que vuelven a la ficha (nota, favorito, colecciones, seguimiento,
vista previa…) y que hoy pierden el `volver` al recargar: es una limitación declarada, no parte
de UATP-02; navegación ficha → número → ficha; modo escaparate (§10 D-2); rediseñar la Biblioteca
o sus filtros; tocar el gate legal o `volver_legal` (UATP-01); migración, dependencias o cambios
de BD.

**D-1 de UATP-01 no aplica:** el criterio «conserva consulta o selección» de Deseados no se
reabre. En Biblioteca el estado **ya vive entero en la URL** (`web/library.py:3-10`); no hay
estado de sesión que inventar. La decisión D-4 de UATP-01 (Biblioteca como respaldo del gate
legal) **no se toca**: esta historia no añade páginas a `volver_legal`; si algún día se añade
`/ui/biblioteca` allí, debe usar la allowlist derivada de §3.1, no los 7 nombres de
`PARAMETROS_DE_VUELTA` de 2026-11-20.

## 3. Contrato de retorno

### 3.1 Allowlist derivada de la ruta (una sola fuente)

**No se mantiene una lista manual de 22 nombres.** Al final de `web/library.py`, después de
declarar `index`, se deriva de la propia ruta de FastAPI:

```python
# Al final del módulo, cuando ya existen todas las rutas del router.
_RUTA_INDEX = next(
    r for r in router.routes if r.path == "/ui/biblioteca" and "GET" in r.methods)
PARAMETROS_DE_BIBLIOTECA = frozenset(
    q.alias or q.name for q in _RUTA_INDEX.dependant.query_params)
```

- La lista resultante es la que el framework acepta de verdad (incluye alias y tipos, no solo
  anotaciones). Hoy son 22 (incluye `puntuacion`); con `foco` serán **23**. En este router, `APIRoute.path` ya incluye
  el prefijo (`"/ui/biblioteca"`), comprobado contra `library.router.routes`.
- **`PARAMETROS_DE_VUELTA` (7 nombres) desaparece** o queda como alias interno de la nueva
  constante; nadie más lo importa hoy (`tests/test_web_retorno.py` es el único consumidor).
- `web/retorno.py` **importa esta constante de forma perezosa** (dentro de la función): `library`
  importa `url_de_ficha` de `retorno` en su cabecera, y un import de módulo en sentido contrario
  cerraría el ciclo.
- **Prueba de sincronía** (§7 T1): el conjunto derivado debe ser igual al de los parámetros de
  query de la ruta real y al de las claves que puede emitir el constructor canónico
  (`_qs` con un `Filtros` completo) más `foco`. Añadir o retirar un filtro de `index` sin revisar
  la allowlist **rompe la prueba**; no hay segunda lista que actualizar a mano.
- El constructor de URLs (`_qs`) sigue siendo la fuente de la **forma canónica**; la allowlist
  solo dice **qué nombres** pueden viajar.

### 3.2 Validación de valores: canónico o rechazo

La allowlist no decide valores: **la misma normalización de la ruta** es la que valida. Se añade
en `web/library.py` (pública para `retorno`) una función que, dada la query ya troceada, devuelve
la query canónica equivalente o `None`:

```python
def consulta_canonica_de_biblioteca(query: str) -> str | None:
    """La query canónica equivalente a `query`; None si la ruta la corregiría."""
```

Reglas exigibles:

1. Se trocea con `parse_qsl(..., keep_blank_values=True)`; error de decodificación → `None`.
2. **Sin repetidos**: cada nombre aparece una sola vez; un nombre vacío o repetido → `None`.
3. **Sin nombres fuera de la allowlist** → `None`.
4. Se normaliza con **`_leer_filtros`** (el de la ruta) y se re-emite con **`_qs`**. El valor de
   vuelta solo es válido si la query canónica **coincide carácter a carácter** con la recibida
   (sin reordenar, sin normalizar). Si `_leer_filtros` corregiría algo (página 0 o `01`, tradición
   inexistente, vista `tarjetas` en Biblioteca —la canónica omite el valor por defecto—, orden
   `titulo`, años de 3 dígitos o invertidos, `q` de más de 200, etiquetas fuera de tope, `modo`
   forzado…), la canónica no coincide → `None`. **No se repara ni se recorta: se rechaza.**
5. **Enums y formas**: los valores válidos son los de la ruta, y solo en su forma canónica:
   `tradition` ∈ `ComicTradition`; `vista` solo `lista` (el valor por defecto `tarjetas` no se
   emite); `leido` ∈ {`si`, `no`, `leyendo`}; `orden` ∈ {`titulo`, `titulo_desc`, `anio_desc`,
   `anio_asc`, `reciente`} (solo se emite si no es `titulo`); `coleccion` ∈ `COLECCION_TIPOS`;
   `densidad` ∈ {`grande`, `compacta`} (la intermedia se omite); `modo=escaparate` solo sin
   filtros; `naturaleza` ∈ `_NATURALEZAS_VALIDAS`; `formato` ∈ `_FORMATOS_VALIDOS`; `edicion` ∈
   {`oficial`, `tradumaqueta`, `escaneo_propio`, `otro`}; `favoritos` solo `1`; `idioma` en
   minúsculas y ≤ 10. `publisher_id`, `character_id`, `story_arc_id` y `author_id` se validan con
   `UUID`.
6. **Dígitos ASCII** para `page`, `anio_desde` y `anio_hasta` (`[0-9]+`, nunca `str.isdigit()`):
   `²`, `٣`, `１２` o `٢٠٠٠` se rechazan **sin 500/422** (la ruta acepta hoy años Unicode por
   `str.isdigit()`; la vuelta no los admite como canónicos). `page` debe ser ≥ 1.
7. **Controles** (cualquier `ord < 32`, `127`) en los valores ya decodificados → `None`; el
   espacio (`ord 32`) sí es legítimo dentro de `q` y `etiquetas` (se codifica `+`).
8. Para que no haga falta un segundo mapa nombre-de-URL → argumento, `_leer_filtros` pasa a
   aceptar **los nombres públicos** de la query (`favoritos` en vez de `favorito`; el resto ya
   coincide) y la ruta y el validador lo llaman con esos nombres (actualizar `index`,
   `resultados`, los tres `buscar-*`, `sugerir_etiquetas` y `test_ux_bib_1058.py::_leer`). La
   prueba de sincronía compara también la firma del normalizador con la allowlist.

Consecuencia: una URL generada por la app siempre valida; una URL editada, recortada o de una
versión anterior que no sea canónica no se repara, cae al respaldo (§4) y no pierde nada que la
persona pueda percibir como un error (la ficha pinta «← Biblioteca», sin aviso).

### 3.3 `foco`: parámetro de transporte, no de estado

El fragmento `#serie-<uuid>` no viaja al servidor. Para que el servidor pueda decidir el foco y
su respaldo, `url_de_ficha` añade `foco=<uuid>` **antes** del fragmento:

```
/ui/series/<sid>?volver=%2Fui%2Fbiblioteca%3Fq%3Dthor%26page%3D2%26foco%3D<sid>%23serie-<sid>
```

- `foco` es **opcional** (una URL antigua con ancla pero sin `foco` sigue siendo válida) y, si
  está: aparece **una sola vez** y **como último parámetro** de la query del destino (lo garantiza
  `url_de_ficha`; así la comparación canónica no re-encode nada), es un UUID canónico en
  minúsculas, coincide con el ancla `#serie-<uuid>` y, cuando `volver_segura` recibe
  `series_id`, coincide con esa serie. Cualquier desajuste → se rechaza la URL entera.
- `index` declara `foco: str = ""` y lo valida con `UUID` sin lanzar; calcula `foco` (el UUID
  canónico o `""`) y `foco_ausente` (hay `foco` pero no está en `items`) después de consultar la
  página. El parámetro **no** se añade a `resultados` ni a `_qs`; el parcial usa
  `foco|default("", true)` para que una respuesta HTMX sin `foco` no dependa de él.
- **No es estado de vista**: no lo emite `_qs`, no entra en `url_canonica`, no se conserva al
  cambiar de filtro/página (el `HX-Push-Url` de la Biblioteca emite la canónica sin `foco`) y
  recargar la URL de vuelta vuelve a enfocar (inofensivo) o cae al respaldo si el objetivo ya no
  está. No se guarda en cookie ni sesión.
- Límite de longitud del valor `volver`: **4096** caracteres (antes 2000). Motivo: una búsqueda
  canónica de 200 caracteres no latinos puede superar 2000 al ir percent-encoded dentro de la
  query; 2000 rechazaría URLs legítimas generadas por la app. `> 4096` → rechazo. Hay prueba con
  una URL canónica larga y con otra por encima del tope.

### 3.4 Colecciones: conservar el estado, no el foco

`/ui/colecciones/<uuid>` lee de la URL `q`, `tradicion`, `vista` y `pagina`
([`web/colecciones.py:125`](../../src/zascarr/web/colecciones.py:125)). El retorno a colección
pasa a llevar **el estado normalizado**, construido en el servidor con `_url_ficha(...)` (la
misma función que genera los enlaces de vista) y no con la URL cruda de la petición. La
validación de la vuelta vive junto a esa ruta: `colecciones.py` expone
`consulta_canonica_de_coleccion(coleccion_id, query) -> str | None`, con el mismo criterio de
comparación exacta de §3.2 (normaliza con `_filtros` y re-emite con `_url_ficha`); `retorno.py`
la importa de forma perezosa, igual que la de Biblioteca.

- `colecciones.py` expone `url_ficha` (o el nombre que use el router) para las tarjetas y filas
  de la colección: `/ui/series/<sid>?volver=<quote(_url_ficha(cid, q, tradicion, [], pagina,
  vista))>`. `serie_ids` se omite: es selección transitoria, no lugar.
- En la vuelta se acepta: (a) la URL **canónica con estado**, validada por el mismo criterio de
  §3.2 (`_filtros` + `_url_ficha`, comparación exacta, `pagina` en dígitos ASCII ≥ 1); y (b) la
  URL **sin query** (`/ui/colecciones/<uuid>`), que hoy generan enlaces existentes y debe seguir
  funcionando. No se acepta fragmento. Se rechazan `serie_ids`, `cambio_vista`, `limpiar`,
  `abrir` y `guardado`: son banderas de un solo uso o selección, no estado del lugar.
- **Limitación declarada:** las listas de una colección no tienen `id` estable por serie ni
  rejilla enfocable; no se promete restaurar **foco ni posición** al volver a una colección, solo
  el estado. Añadirlo sería otra historia (implica marcar las filas y decidir el respaldo).

### 3.5 Foco sin JavaScript

El servidor decide el foco al pintar la página de vuelta (`index`, 200 normal, sin redirección):

| Caso | Marcado | Resultado |
|---|---|---|
| El objetivo está en la página, vista tarjetas | `<a class="library-card" id="serie-<uuid>" … autofocus>` | El navegador enfoca y desplaza a la tarjeta; `scroll-margin-block-start` ya existe (`.library-card`, `web.css:884`). |
| El objetivo está en la página, vista lista | `<tr id="serie-<uuid>" tabindex="-1" autofocus>` | La fila es enfocable por programa (`tabindex="-1"`, no entra en el orden de Tab) y recibe el foco; antes un `<tr>` no podía. |
| El objetivo **no está** en `items` (filtrado, otra página, otro orden, error) o `foco` no es un UUID | `#rejilla` con `tabindex="-1" autofocus role="region" aria-labelledby="rejilla-titulo"` (título `.sr` estable) | Foco y desplazamiento predecibles al inicio de los resultados; sin tarjeta enfocada. No se corrige la página ni se redirige. |
| `modo=escaparate` | Sin `#rejilla`; se ignora `foco` | El escaparate no genera enlaces con `foco` (§10 D-2). |

Exigencias:

- **Un solo `autofocus` por documento** (el de la tarjeta, la fila o `#rejilla`; nunca junto al
  buscador, que en la página completa no lo lleva).
- `foco` se valida en `index` sin lanzar (UUID inválido → se ignora, 200); no hay 422/500 por un
  `foco` manipulado.
- El anillo de foco debe verse también con foco **programático**: además del `:focus-visible`
  general, una regla `:focus` para `.library-card`, `.library-lista tr` y `#rejilla` con el anillo
  existente (`3px var(--cyan-t)`); sin tokens ni colores nuevos. La fila va con `outline-offset:
  -3px` porque la tabla recorta con `overflow: hidden`. Verificación visual en navegador: §8 (si
  no se ejecuta, **NOT RUN**).
- No se promete la posición exacta en píxeles ni que el navegador restaure el scroll al volver
  con `Atrás`; el contrato es foco + desplazamiento al elemento (o a la rejilla).

## 4. Endurecimiento de `volver_segura`

`volver_segura(valor, series_id=None)` sigue siendo la única puerta de entrada del `volver` de la
ficha ([`web/series.py:759`](../../src/zascarr/web/series.py:759)) y de cualquier parcial que lo
relea. Se alinea con el criterio de **UATP-01 §3.3** (`volver_legal`): no se repara, se rechaza
(ver `docs/design/uatp01-retorno-legal.md` §3.3). Antes de mirar el destino:

1. Vacío, `> 4096`, no empieza por `/`, o empieza por `//` (esto cubre `///ui/...`: el navegador
   lo resolvería como host `ui`) → `None`.
2. Cualquier espacio o `isspace()`, control (`ord < 32` o `127`) o **barra invertida** en el valor
   crudo → `None`. (Los espacios legítimos de `q` van percent-encoded, no literales.)
3. `%` en la **ruta**, segmento `.`/`..`, o ruta que no sea exactamente una de las dos de §3
   → `None` (esto cubre `%2e%2e`, `%2f`, `%00`, `//` interno y mayúsculas de la ruta).
4. La query se trocea una vez; nombres repetidos, vacíos o fuera de la allowlist del destino
   (Biblioteca o Colección) → `None`; los valores decodificados no pueden llevar controles.
5. Destino **Biblioteca**: si hay `#`, el fragmento debe ser `serie-<uuid>` canónico en
   minúsculas y, si se pasa `series_id`, el de esa ficha; un `#` vacío o un segundo `#` → rechazo;
   `foco` según §3.3. La query (sin `foco`) debe ser canónica según §3.2; la Biblioteca **sin
   query** (`/ui/biblioteca`, sin `?`) se acepta como forma por defecto (equivale a `?page=1` y
   no inventa estado); un `?` con la query vacía no es canónico → rechazo.
6. Destino **Colección**: ruta `/ui/colecciones/<uuid>` exacta; **sin fragmento**; sin query
   (forma antigua, sin `?`) o query canónica de §3.4; nada de banderas de un solo uso ni
   `serie_ids`.
7. Cualquier otra ruta (incluidos `/ui/biblioteca/resultados` y `/api/**`) → `None`.

| Valor hostil | Resultado |
|---|---|
| `///ui/biblioteca`, `//ui/biblioteca`, `//evil.example/ui/biblioteca` | rechazo (host) |
| `https://…`, `javascript:…`, `/\ui/biblioteca`, `/ui/biblioteca\` | rechazo |
| ` /ui/biblioteca`, `\t/ui/biblioteca`, `/ui/biblioteca?q=x%0a` | rechazo (espacio/control) |
| `/ui/biblioteca/%2e%2e`, `/ui/%2e%2e/ui/biblioteca`, `/ui/biblioteca%2f` | rechazo (`%` en ruta) |
| `/ui/biblioteca?page=1&page=2`, `?q=x&q=y`, `?page=1&x=1` | rechazo (repetido/desconocido) |
| `/ui/biblioteca?page=²`, `?page=٣`, `?anio_desde=٢٠٠٠`, `?page=0` | rechazo sin 500/422 |
| `/ui/biblioteca?q=x#serie-<otra>` con `series_id` | rechazo (ancla ajena) |
| `/ui/biblioteca?…&foco=<no-uuid>` o `foco` que no coincide con ancla/serie | rechazo |
| `/ui/colecciones/<uuid>#x`; `/ui/colecciones/<uuid>?serie_ids=…` | rechazo |
| `/ui/biblioteca?q=` + 4097 caracteres | rechazo |

El rechazo **no muestra un error**: la ficha pinta el enlace de respaldo
`← Biblioteca` (destino `/ui/biblioteca`), como hoy cuando no hay `volver`. Ningún `Location`
sale del propio servidor; `volver_segura` no redirige, solo devuelve `str | None`.

## 5. Comportamiento HTTP y de URL

- `GET /ui/biblioteca` con `foco` válido: **200** normal (no 303), `Cache-Control: no-store` como
  hoy; sin cookies ni escritura en BD.
- La URL canónica de la Biblioteca **no incluye `foco`**; los enlaces de filtros, paginación,
  chips, quitar y limpiar lo pierden solos al usar `_qs`. `HX-Push-Url` sigue apuntando a la
  página completa canónica.
- La ficha sigue validando con `volver_segura` en el render; una re-renderización por HTMX de un
  parcial que no recibe `volver` no cambia el enlace (está fuera del parcial).
- `url_de_ficha` conserva el formato actual (quote del destino completo) y solo añade
  `foco`/fragmento; no genera URLs externas ni absolutas.

## 6. Criterios de aceptación (UATP-02)

Trazabilidad: #1125 CA (volver a la misma búsqueda/chips/resultados/orden/vista/página y
posición) → AC-01…AC-06; benchmark task-22 P-1/P-2/P-3 → AC-01/04/05/06; P-4 → AC-08; P-5 →
AC-07; P-6 → AC-11.

- **AC-01 · Allowlist completa y derivada.** Un `volver` canónico con **los 22** parámetros de
  `index` (o cualquier subconjunto: `q`, `tradition`, `publisher_id`, `character_id`,
  `story_arc_id`, `author_id`, `favoritos`, `idioma`, `edicion`, `anio_desde`, `anio_hasta`,
  `etiquetas`, `leido`, `orden`, `coleccion`, `page`, `vista`, `densidad`, `modo`,
  `naturaleza`, `formato`, `puntuacion`) más `foco` se acepta **entero** y la ficha devuelve el
  enlace de vuelta con el mismo valor (y el ancla). `PARAMETROS_DE_BIBLIOTECA` se deriva de la ruta; la
  prueba de sincronía pasa (T1).
- **AC-02 · Sincronía sin lista paralela.** `set(query_params de index) ==
  PARAMETROS_DE_BIBLIOTECA`; las claves de `_qs(_leer_filtros(...), page=…)` con un `Filtros`
  completo están en el conjunto, y el conjunto no tiene nombres que la ruta no declare. Añadir
  o quitar un filtro de la ruta sin tocar la allowlist hace fallar la prueba.
- **AC-03 · Validación estricta sin 500/422.** Las URLs no canónicas de §4 se rechazan
  (`volver_segura` → `None`) y la ficha cae al enlace de respaldo; ninguna produce 500 ni 422.
  Incluye `page`/años con dígitos Unicode, repetidos y valores de enum inválidos.
- **AC-04 · Foco en tarjeta.** Con `foco` presente y esa serie en `items`, la página tiene la
  tarjeta `id="serie-<uuid>"` con `autofocus`, **exactamente un** `autofocus`, y el `href` de la
  tarjeta conserva `volver`/`foco`; el ancla `#serie-<uuid>` sigue en la URL de vuelta.
- **AC-05 · Foco en vista lista.** Con `vista=lista`, la fila objetivo
  `<tr id="serie-<uuid>" tabindex="-1" autofocus>` recibe el foco (un solo `autofocus`, sin
  tarjetas en el documento).
- **AC-06 · Respaldo de foco.** Si `foco` no está en los resultados de la página restaurada (o
  no es UUID), `#rejilla` es enfocable y recibe el foco; 200, sin redirección y sin
  `autofocus` en tarjetas. No se corrige la página ni se recorta la URL.
- **AC-07 · `volver_segura` endurecida.** La tabla de §4 da `None` en todos los casos, y la
  ficha pinta `/ui/biblioteca` como respaldo; se conservan fragmento y Colecciones válidos.
  `volver_legal` no se toca.
- **AC-08 · Colecciones con estado.** Enlace de tarjeta y de fila de una colección →
  ficha → «Volver a la colección» devuelve a
  `/ui/colecciones/<uuid>?q=…&tradicion=…&pagina=…&vista=…` con los valores normalizados; la URL
  antigua sin query sigue funcionando; estado inválido o banderas de un solo uso se rechazan.
- **AC-09 · Sin JS, sesión ni cookie.** No se añade ningún `.js`; `foco` no se persiste; una
  respuesta con foco no escribe BD ni cabeceras de sesión. El estado restaurado es el de la URL.
- **AC-10 · Longitud y Unicode.** Una URL canónica larga (q de 200 caracteres no latinos) valida
  y vuelve entera; `> 4096` se rechaza sin 500.
- **AC-11 · Documentación y evidencia.** §9 actualizado por la implementación; §8 con
  PASS/FAIL/NOT RUN por AC. El E2E de navegador (Chrome/Firefox) se marca **NOT RUN** si no se
  ejecuta; no se deduce del HTML.

## 7. Casos de prueba

Nombres orientativos; lo exigible es el caso. Todo con `FakeSession`/TestClient salvo el E2E.

| # | Caso | Dónde | Espera |
|---|---|---|---|
| T1 | Sincronía: parámetros de `index` == `PARAMETROS_DE_BIBLIOTECA` == claves de `_qs` completas ∪ `{foco}`; firma del normalizador == allowlist | `test_web_retorno.py` / `test_log_acceso.py` | AC-02 |
| T2 | Cada filtro por separado y todos juntos en una URL canónica: `url_de_ficha` → `volver_segura` lo acepta; la ficha pinta el enlace con el valor íntegro. Actualizar `test_la_url_de_la_ficha_lleva_la_biblioteca_y_el_ancla` (compara la query exacta) para incluir `foco` | `test_web_retorno.py`, `test_web_series.py` | AC-01 |
| T3 | Sin canónico: `page=0`, `page=01`, `page=²`, `page=٣`, años de 3 dígitos, `anio_desde > anio_hasta`, `vista=tarjetas` en Biblioteca, `orden=titulo`, `q` de 201, etiquetas con 13 tokens, enum inválido, `page`/`q` repetidos, nombre desconocido → `None`, sin excepción | `test_web_retorno.py` | AC-03 |
| T4 | `///ui/biblioteca`, `//x`, `/\ui/...`, espacio inicial, `%2e%2e`, `%2f`, `%00`, `\`, control literal, `foco` ajeno o mal formado, `>4096` → `None` | `test_web_retorno.py` | AC-07/AC-10 |
| T5 | Ficha GET con el `volver` de una tarjeta → enlace de vuelta con el mismo valor y ancla; sin `volver` → «← Biblioteca» | `test_web_series.py::TestVolverALaBiblioteca` | AC-01/AC-04 |
| T6 | Biblioteca con `foco` de un item, vista tarjetas: un solo `autofocus` en la tarjeta; `id` y `href` intactos | `test_web_library.py` | AC-04 |
| T7 | Biblioteca con `foco` y `vista=lista`: un solo `autofocus` en la fila; `tabindex="-1"`; no hay `library-card` | `test_web_library.py` | AC-05 |
| T8 | Biblioteca con `foco` de un UUID que no está en `items` (filtro que lo excluye o página sin él): `#rejilla` con `tabindex="-1" autofocus`; sin `autofocus` en tarjetas; 200 y sin `Location` | `test_web_library.py` | AC-06 |
| T9 | `foco` inválido directo (`?foco=x`): 200, sin 500/422; sin `autofocus` en tarjetas y `#rejilla` recibe el foco (AC-06) | `test_web_library.py` | AC-06 |
| T10 | Colección: tarjeta y fila llevan `volver` con estado; ficha devuelve ese mismo valor; URL sin query sigue aceptada; `serie_ids`/`cambio_vista` rechazados | `test_web_colecciones.py`, `test_web_series.py`, `test_web_retorno.py` | AC-08 |
| T11 | URL canónica larga con `q` no latino de 200 caracteres: válida y vuelta entera; 4097 caracteres: rechazo | `test_web_retorno.py` | AC-10 |
| T12 | `foco` en `PARAMETROS_DE_QUERY` (`test_log_acceso.py:350`) y los valores de la query no se registran | `test_log_acceso.py` | AC-01/AC-09 |
| T13 | `no-store` en la página de vuelta; sin `Set-Cookie`; no se escribe nada en la BD (espía de sesión) | `test_web_library.py` | AC-09 |
| T14 | E2E manual: Firefox y Chrome, tarjetas y lista, objetivo con y sin coincidencia; «Volver» restaura chips/página/orden/vista; foco visible; Colecciones con vista y página | navegador real + `docs/TESTING_E2E.md` si aplica | AC-04/05/06/08; **NOT RUN** si no se ejecuta |

Comandos mínimos:

```bash
pytest -q tests/test_web_retorno.py tests/test_web_library.py tests/test_web_series.py \
  tests/test_web_colecciones.py tests/test_ux_bib_1058.py tests/test_log_acceso.py
ruff check src/ tests/
```

Si el cambio toca `_leer_filtros` (firma o llamadas), añadir las suites de Biblioteca y barrido
completo de la suite no-PG. La suite completa se ejecuta con el directorio temporal en el mismo
dispositivo que `/` (CLAUDE.md §8). No hace falta Postgres para T1–T13.

## 8. Evidencia

- **Código:** SHA completo del commit, rama y fecha; diff del rango; enlace al PR. No vale un SHA
  anterior a la última corrección.
- **Pruebas:** salida de §7 con PASS/FAIL y `ruff` limpio; cada AC con su fila PASS/FAIL/NOT RUN.
- **Contrato:** para AC-01/AC-02, imprimir el conjunto derivado y la prueba de sincronía; para
  AC-07, la tabla de §4 con el valor observado de `volver_segura` (`None`) y el `href` de respaldo
  exacto; para AC-10, longitudes y resultado.
- **HTML observado:** para AC-04/05/06, fragmentos exactos con `autofocus` (uno solo) y el
  `tabindex` de la fila o `#rejilla`, más el `href` de la tarjeta/volver.
- **Navegador real:** T14 Chrome/Firefox (y 320 px si se toca CSS). Si no se ejecuta, **NOT RUN**
  explícito; no se afirma «enfoca en el navegador» solo por el HTML.
- **No-regresión:** inventario de logs actualizado (`foco`) y suites de Biblioteca, ficha y
  colecciones en verde.

## 9. Documentación a actualizar (parte de la implementación)

| Doc | Cambio |
|---|---|
| [`ui-migracion.md:220`](ui-migracion.md:220) | Inventario de `/ui/biblioteca` y `/ui/biblioteca/resultados`: los 21 parámetros de estado reales y `foco` (22 en la ruta de la página). |
| [`benchmark-deep-dive-colecciones-2026-11-14.md:93`](benchmark-deep-dive-colecciones-2026-11-14.md:93) | §5: el retorno a colección conserva estado (`q`, `tradicion`, `vista`, `pagina`) además del destino; sin foco. |
| `docs/design/uatp01-retorno-legal.md` §8 D-4 | Referencia a los «7 parámetros de `PARAMETROS_DE_VUELTA`»: se actualiza a la allowlist derivada de §3.1 si el PO retoma la entrada de Biblioteca en el gate legal. No cambia el gate. |
| Este documento | Estado y evidencia al cerrar; D-1…D-3 resueltas por el PO. |
| `docs/BACKLOG.md` | Solo al cerrar la historia P1, con la nota del mecanismo (allowlist derivada + `foco` + canonical/round-trip). |

## 10. Decisiones pendientes del PO

### D-1 · Foco y posición al volver a una Colección

La historia pide estado en Colecciones; el **foco/posición** exigiría ids estables en sus listas
y el mismo respaldo que la Biblioteca. **Recomendación:** aceptar la limitación de §3.4 en
UATP-02 y abrir una historia aparte si el PO lo pide; el estado (lo que hoy se pierde) sí se
restaura.

### D-2 · Modo escaparate

Las sugerencias del escaparate enlazan a la ficha **sin `volver`**
([`_escaparate.html:10`](../../src/zascarr/web/templates/_escaparate.html:10)), así que «Volver»
cae a la Biblioteca sin filtros. **Recomendación:** dejarlo fuera (el escaparate no tiene
búsqueda/chips que restaurar; su URL es `modo=escaparate` y volver a ella no es la tarea de
UATP-02) y anotarlo como limitación. Si el PO quiere conservarlo, es una entrada más en el
contrato y una prueba.

### D-3 · Aviso cuando el `volver` se rechaza

Hoy el rechazo es silencioso: la ficha pinta «← Biblioteca» sin decir por qué. **Recomendación:
no añadir aviso** (no ha fallado ninguna acción de la persona; el coste de un aviso es ruido y
copy nuevo). Si se quiere, debe ser distinto de los avisos de acción y no bloquear la ficha.

## 11. Dependencias y orden

- Implementación (TDD) de §3–§5 y pruebas §7; después SecOps (open redirect, valores hostiles,
  longitud, `foco`/canonical), UI/UX (foco visible y copy del respaldo) y QA (matriz §6/§7).
- Sin migración, sin dependencias nuevas, sin JavaScript nuevo y sin tocar `LEGAL.md`.
- Orden sugerido: (1) allowlist derivada + validador canónico (T1–T3); (2) `foco` + foco
  servidor (T4–T9); (3) Colecciones (T10); (4) docs §9 y evidencia.
