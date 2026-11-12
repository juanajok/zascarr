# BL-D6 — Colecciones de series y política de auto-búsqueda

**Historia:** #155. **Decisiones del PO:** 2026-11-12. **Base:** `origin/main` `5cfc9ee`.
**Alcance:** agrupación manual de series y política tri-estado de auto-búsqueda. Fuentes y
calidad de descarga **no** entran en esta historia.

## Contrato

- Una serie pertenece como máximo a **una** colección (`series.collection_id`, FK nullable
  `ON DELETE SET NULL`). Borrar una colección no borra series ni archivos: las deja sin colección.
- `collections`: `id` UUID, `name` único (case-insensitive, máx. 120, recortado), `description`
  opcional (máx. 500), `auto_search` (`collection_auto_search`), timestamps.
- `auto_search`:
  - `heredar` (por defecto; también sin colección): se usa la `wishlist_policy` guardada de la
    serie. Es el comportamiento actual de D8.
  - `incluir`: la política efectiva es `faltantes`; se generan faltantes aunque la serie diga
    `ninguno`.
  - `excluir`: la política efectiva es `ninguno`; se veta la auto-búsqueda y se retiran los
    items de origen `politica` pendientes (`WANTED`/`FAILED`). Los items manuales no se tocan.
- La ficha de serie sigue mostrando la política **guardada**; si una colección cambia la efectiva,
  lo explica junto al selector.
- La búsqueda manual («Buscar ahora») no se bloquea por colección.
- UUID de colección/serie se valida en el servicio y en las rutas.

## Orquestador

`sync_policy_items` calcula `politica_efectiva(db, series)` y pasa esa política a
`querer_de_serie`. `_series_para_sincronizar` incluye:
- series sin colección o con `heredar` cuya `wishlist_policy` es `faltantes`/`todos`;
- series de colección `incluir`, aunque su política guardada sea `ninguno`;
- series con items de política pendientes, para retirarlos (también las de `excluir`).

La generación y la retirada siguen usando el mismo predicado de D8; no se duplica la lógica.

## Límites

- Sin migración de datos: las series existentes quedan sin colección y conservan su política.
- No se tocan fuentes, Prowlarr, calidad, archivos ni B6.
- `futuros`/`todos` mantienen su estado reservado de D8; una colección `incluir` usa `faltantes`.
- La colección no reescribe `Series.wishlist_policy`: es una capa de decisión, reversible.

## Pruebas

- `tests/test_colecciones_pg.py`: política efectiva, CRUD, nombre único case-insensitive,
  asignación única, FK al borrar y orquestador `incluir`/`excluir`/manual.
- `tests/test_web_colecciones.py`: listado, detalle, errores, redirecciones CRUD/asignación.
- Regresión D8: sin colección o `heredar` se conserva la política guardada.
