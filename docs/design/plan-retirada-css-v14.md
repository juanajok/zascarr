# Plan de retirada del CSS heredado y cierre de la Épica V (V14, #750)

> **Estado: ejecutado el 2026-11-14.** No autoriza código, migración ni despliegue.
> Base medida: `main` `667b508` (2026-11-13), la Pi desplegada con `d2faf13`. Complementa a
> `docs/design/ui-migracion.md` y al sistema de diseño publicado
> (`docs/design/sistema-de-diseno-zascarr.md`).

## 1. Objetivo

Cerrar la migración V0–V13 **sin restos**: retirar las clases de antes de V2 que ya no aportan
(o migrarlas a los componentes), quitar reglas de CSS muertas, dejar una comprobación automática
que impida que vuelvan y registrar el estado final (capturas, documentación, presupuesto de peso).
No cambia ningún flujo, ninguna pantalla ni el modelo de datos.

## 2. Inventario medido hoy

### 2.1 Clases de la lista de compatibilidad (`CLASES_ANTERIORES_A_V2`, 135)

| Situación | Clases | Nota |
|---|---|---|
| Sin ninguna aparición en plantillas | **12** | `ajustes-grid`, `audit-ok`, `estado-bad`, `estado-check-row`, `estado-ok`, `estado-warn`, `filter-bar-secondary`, `filter-search-box`, `htmx-request`, `series-cover`, `topnav`, `visible` |
| Heredadas **en uso** y con sustituto | 5 | `.btn-primary` (8 usos), `.legal-notice-warn` (3), `.issue-chip` (4, con `.issue-missing`/`.issue-present`, 2+2), `.estado-dot` (2) |
| Compatibilidad con significado propio | 2 | `button[type="submit"].neutro` (1 uso, base neutra) y `.visible` (JS de `/estado`) |

**Ojo: no todo lo que «no aparece» está muerto.** El script de la fase 1 debe distinguir:
- `htmx-request`: lo añade htmx en runtime (definido en su config y usado en la hoja).
- `visible`: lo añade el JS de `estado.html` (`classList.add/remove`).
- `estado-ok`/`estado-warn`/`estado-bad`/`estado-neutral`: se construyen por concatenación en
  `estado.html` (`"estado-" + meta.level`), no como literal en una plantilla.
- Las clases citadas en comentarios y en pruebas no cuentan como uso; el script debe analizar
  atributos `class="…"` y las cadenas de JS que construyan clases, con una **lista blanca
  declarada** para lo dinámico y para los ganchos de pruebas/HTMX.

### 2.2 Peso actual (medido en la Pi, `main` `667b508`)

| Recurso | Bytes | gzip |
|---|---:|---:|
| `web.css` (934 reglas) | 130.813 | 29.971 |
| `/ui/biblioteca` (224 series, página 1) | 43.078 | 5.760 |
| `/ui/pendientes` (50 pendientes, página 1) | 83.928 | 7.850 |
| `/ui/auditoria` (informe completo) | 138.322 | 10.710 |

Estas cifras son la **línea base** del criterio 5; el cierre compara con la misma medición y no
admite crecimiento. `web.css` no se sirve comprimido por la app (se cachea con ETag y `no-cache`),
así que el objetivo útil es el tamaño en claro.

### 2.3 Reglas muertas y deuda del sistema de diseño

- `.topnav`: **14 reglas** y ninguna plantilla la usa (el menú es `.app`/`.nav`).
- `.hero-state`: **6 reglas** sin uso (componente de la maqueta que nunca llegó a una pantalla).
- `.toast`: **1 regla** sin uso (V1/V2 lo dejaron listo; el toast actual es un aviso).
- `.audit-ok`: ya no se usa en plantillas (sustituido por `ui.aviso("ok")` en #730), pero se
  conserva por la lista de compatibilidad.
- `.estado-ok/warn/bad` y `.estado-neutral`: las genera `/estado` por JS (no retirar sin migrar
  ese bloque; ver §3).
- Clases muertas sin regla: 0 (la lista de compatibilidad ya pasa el test).

## 3. Sustituciones (qué reemplaza a cada clase viva)

| Vieja | Sustituta | Pantallas | Acción |
|---|---|---|---|
| `.btn-primary` (botón y `<a>`) | `button.primary` / `.btn.primary` (V2) | Auditoría, comprobación de disco, desvinculación, duplicados, aviso legal… | Cambiar la clase y conservar el tipo (`button` o `a.btn`) |
| `.legal-notice-warn` | `ui.aviso("warn", …)` | `_legal_disclaimer.html` (2), `wishlist.html` | Macro: aporta icono, `role="alert"` y borde de tinta |
| `.issue-chip` + `.issue-missing` / `.issue-present` | `ui.chip("neutro"\|"ok"\|"amber", "#N")` y el borde discontinuo del sistema | Ficha de serie, `_politica_serie.html` | Migrar también `.issue-leido`/`.issue-leyendo` al aspecto que corresponda; conservar `data-*` que usen pruebas |
| `.estado-dot` + `estado-*` | Semáforo con **glifo** del chip de su color (✓ ! ?), como decidió #391 | `/estado` (JS de la página) | Reescribir el bloque de JS en línea para pintar el glifo (V9 ya estaba pendiente de retirar el JS en línea; **no** se reescribe la pantalla en V14) |
| `button[type="submit"].neutro` | Base de `button` (un envío es neutro por defecto) | `dashboard.html` | Quitar `.neutro` y comprobar el aspecto |
| `.series-cover` | `ui.portada` (ya migrada la Biblioteca) | Ficha de serie | Solo retirar la clase muerta; la ficha ya usa `.portada.series-cover`? Verificar en F3 |
| `.visible` | Se queda | `/estado` (JS) | Lista blanca, no es deuda |

## 4. Fases (cada una, una PR fusionable y reversible)

| # | Rebanada | Qué entra | Pruebas | Riesgo |
|---|---|---|---|---|
| **F1** | Auditoría de clases | `scripts/auditar_css.py`: extrae clases de plantillas (atributos y cadenas JS), reglas de `web.css`, compara y emite dos listas (clases sin regla / reglas sin clase) con **lista blanca declarada** (`htmx-request`, `visible`, `estado-*` dinámicas, ganchos de tests). Se añade como paso informativo de CI; el objetivo de V14 es que la lista de «sin uso» se vacíe o quede justificada. | Test del script con CSS/HTML sintéticos y **mordida** (una clase nueva sin regla debe aparecer) | Bajo |
| **F2** | Retirar lo muerto | `.topnav` (14 reglas), `.hero-state` (6), `.toast` (1), `.audit-ok` (1), `.ajustes-grid`, `.filter-bar-secondary`, `.filter-search-box`, `.series-cover`, `.estado-check-row`. Solo CSS, sin plantillas. Actualizar `CLASES_ANTERIORES_A_V2` (quitar las retiradas, con nota del motivo, como se hizo con `.wishlist-badge`). | Suite, contraste, `test_web_componentes`; capturas de las pantallas afectadas | Bajo |
| **F3** | Migrar lo vivo | `.btn-primary` → `.primary`; `.legal-notice-warn` → `ui.aviso("warn")`; `.issue-chip/{missing,present,leido,leyendo}` → `ui.chip` + borde discontinuo; `.estado-dot` con glifos; `.neutro` fuera. Una PR por familia o una sola con commits separados por familia. | Tests de cada pantalla (auditoría, wishlist, ficha de serie, estado, duplicados, comprobación de disco); navegador real en claro/oscuro y 1280/375 | **Medio** (JS de `/estado` y estados de lectura) |
| **F4** | Retirar las migradas | Reglas de `.btn-primary`, `.legal-notice-warn`, `.issue-chip` y familia, `.estado-dot`; la lista de compatibilidad **se vacía** (el test pasa a «no queda ninguna clase anterior a V2», con la lista blanca de lo dinámico). | Suite completa; el script de F1 sin avisos no justificados | Medio-bajo |
| **F5** | Trazabilidad y peso | Capturas nuevas en `docs/design/ui-actual/` (claro/oscuro, 1280/375) y README; CHANGELOG y BACKLOG (V14 → Hecho con mecanismo); registrar lo que quedó fuera (§6); medir `web.css` y las tres páginas en la Pi y anotar el antes/después; enlace a ADR 0005 (ya Aceptado). | Medición reproducible; revisión de capturas | Bajo |

**Orden:** F1 → F2 → F3 → F4 → F5. F2 puede ir en paralelo con F3 (archivos disjuntos), pero se
fusiona antes para reducir la hoja mientras se migra.

## 5. Verificación

- **Automática:** suite completa, `ruff`, `test_web_css_contraste`, `test_web_componentes`,
  `test_web_css_tokens`, script de F1 con mordida. CI ligada al SHA de cada PR.
- **Manual (navegador real, Chrome + Firefox, claro/oscuro):** Inicio, Biblioteca, Por revisar,
  Duplicados, Colecciones, Descubrir, ficha de serie, Deseados, Estado, Auditoría, Ajustes, login
  y aviso legal, a 1280 y 375 px. Comprobar: foco visible, objetivos táctiles, sin scroll
  horizontal, un solo botón principal por pantalla, avisos con icono.
- **Peso:** medir `web.css` (bytes y gzip) y `/ui/biblioteca`, `/ui/pendientes`, `/ui/auditoria`
  con la misma receta de §2.2; cualquier crecimiento se justifica o se revierte.
- **Regresión de compatibilidad:** una clase antigua que aún se use no se retira; primero F3.

## 6. Lo que queda fuera de V14 (se registra, no se hace)

1. **Conmutador manual de tema.** El sistema de diseño decide que el tema sigue al sistema
   (`prefers-color-scheme`), sin selector. No hay nada que migrar; se documenta la decisión.
2. **Deshacer tras asignar.** La maqueta lo simulaba; no es de V14 ni está implementado.
3. **Progreso real de V11b** (sondeo de escaneo). Requiere backend nuevo y se estima aparte.
4. **Rediseño de Biblioteca/Descubrir.** V12 hizo *restyle*, no rediseño de flujo; sigue abierto
   como historia propia si el PO lo quiere.
5. **Retirar todo el JS en línea de `/estado` (V9).** V14 solo migra `.estado-dot` a glifos; el
   resto del bloque no se reescribe.

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Clases dinámicas tratadas como muertas | Se rompe `/estado` o un indicador htmx | Lista blanca + mordida + navegador real de `/estado` y de una acción HTMX |
| Tests acoplados a nombres viejos | Falsos positivos al retirar | Actualizar la lista de compatibilidad en la misma PR, con nota del motivo |
| Usuarios con CSS cacheado | Estilo viejo puntual | `/static` va con `no-cache` + ETag; no requiere nada más |
| Pantallas menos visitadas (Descubrir, asistente) | Rotura visual no detectada | Lista manual de §5 incluye todas; capturas antes/después |
| Pérdida de semántica en `.estado-dot` | Se vuelve a depender solo del color | Glifo obligatorio (decisión #391) y prueba del contraste de los tres glifos |

## 8. Estimación y Definition of Ready

- **Talla S** (≈2–3 días): F1 0,5 · F2 0,5 · F3 1 · F4 0,5 · F5 0,5.
- DoR: este plan aprobado; dependencias V0–V13 cerradas; ADR 0005 aceptado; sin migraciones.
- DoD: criterios 1–6 del BACKLOG acreditados; CI en verde por SHA; PASS/FAIL/NOT RUN separados;
  fusión y despliegue aprobados aparte.

## 9. Mapa de criterios de aceptación

| AC (BACKLOG) | Dónde se acredita |
|---|---|
| 1 · Retirar alias y reglas sin uso, con script | F1 (script) + F2/F4 (retirada) + test del script |
| 2 · Plantillas huérfanas | F2 (hoy no hay ninguna: el script de F1 lo verifica) |
| 3 · Capturas, README, CHANGELOG, BACKLOG, Épica U | F5 |
| 4 · Registrar lo que quedó fuera | §6 de este plan + F5 |
| 5 · Presupuesto de peso | §2.2 (línea base) y F5 (medición final) |
| 6 · ADR 0005 «Aceptado» | Ya aceptado (2026-10-02); F5 lo enlaza y registra |

## 10. NOT RUN

Nada del plan está ejecutado: no se ha tocado CSS, plantillas, tests ni la Pi. Las cifras de §2.2
son mediciones reales del estado actual, no resultados del cierre.
