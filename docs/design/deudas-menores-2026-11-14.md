# Pasada de deudas menores — 2026-11-14

Registro de la pasada de deudas declaradas en los informes de SecOps/QA de la épica SCR.
Criterio: cerrar lo barato y de valor (seguridad, legal, cobertura); **diferir con motivo** lo
que exige rediseño o decisión de producto, en vez de acumular parches.

## Cerradas en esta pasada (PR #805)

| Deuda | Origen | Qué se hizo |
|---|---|---|
| **m-1** atribución legal/UI | SecOps SCR2 | El aviso genérico de metadatos incluye DC/Marvel Database (Fandom); la atribución CC-BY-SA de la ficha de serie se ve **sin desplegar** el `<details>` |
| **m-2** listado de sagas sin atribución | SecOps SCR2 | `ArcoResumen.origen` + `PaginaArcos.hay_fandom`; aviso CC-BY-SA 3.0 + `/legal` bajo `/ui/arcos` cuando hay arcos Fandom (`rel="noopener noreferrer"`), sin tocar orden/paginación |
| **m-3** dedupe de arcos por título | SecOps SCR2 | `enricher._upsert_arc` identifica por `metadata_->>'fandom_dc'`; un arco manual o de otra fuente homónimo **no se adopta ni se sobrescribe**: se crea el arco de Fandom aparte. Idempotente |
| **M-5** 304 anotado «4xx» | SecOps SCR1 | `peticiones.py` registra `304` como «304» («Sin cambios»); 400/404 siguen «4xx» |
| **Categorías sin cota** | QA/SecOps SCR5 | Máx. 10 categorías, ≤100 caracteres, controles fuera |
| **O2** sin prueba `_pg` de reconciliación | QA SCR3 | `tests/test_reconciliacion_lecturas_pg.py` (skip sin `TEST_DATABASE_URL`): arco + `reading_order`, idempotencia y biblioteca/ficheros intactos. **Fix posterior**: usar `async with bd_efimera(URL)` (el helper `_sync` llamaba a `asyncio.run` dentro del bucle) |

Verificación: QA **apto** (6.987 passed ×2, `_pg` 1 passed con Postgres real y 1 skipped sin URL);
SecOps **favorable**, §5.8 no aplica (no toca `ajustes`/`seguridad`/`models`/migraciones).

## Ya cerradas antes (verificadas)

- **m-4** código de error de MediaWiki sin sanear (SCR2): cerrado; `FandomPayloadError` usa
  `_codigo_seguro` (re.sub + tope) desde el fix de #749. Se verificó en esta pasada.

## Aceptadas con justificación (no se tocan)

- **m-6** `imageinfo` guarda una URL sin validar (SCR2): la política H1 se aplica en el **punto de
  descarga** (`url_portada.py`: allowlist, DNS público, IP validada, tope, gate de fuente), no al
  guardar. Es el patrón de todas las fuentes; tocarlo ahora duplicaría validación y podría romper
  descargas legítimas. Se mantiene como defensa en profundidad documentada.
- **M-6** caché/robots heredan la confianza de la URL del llamador (SCR1): solo las usan clientes
  con URLs de fuentes gobernadas; documentado en `cache_http.py`/`robots.py`.

## Diferidas (merecen su propia tarea)

| Deuda | Por qué no ahora | Recomendación |
|---|---|---|
- **RES-3 — cerrada (2026-11-14, PR [#819](https://github.com/juanajok/zascarr/pull/819)):** `peticiones.py` lee con `cliente.stream()` y corta al superar `max_cuerpo_transfer_bytes` (4 MiB, 1–16), con `CuerpoDemasiadoGrande` sin reintento ni caché negativa; redirecciones 3xx sin leer cuerpo, `Response` compatible y suite 7.011×2. Deuda restante declarada (Corte 2): consumidores que no capturan `ErrorDePeticion` (Comic Vine/GCD/Discovery) pueden repetir el intento en el siguiente ciclo.
- **M-4 — cerrada (2026-11-14, PR [#832](https://github.com/juanajok/zascarr/pull/832)):** `crawl_delay_max_s=60` (5–300, `.env`) recorta el `Crawl-delay` del servidor sin bajar del mínimo local; `GestorRobots.olvidar(origen)` con generación (singleflight intacto) y `origenes_de_fuente`; Ajustes olvida solo los orígenes de fuentes que cambian. QA apto (sonda 11/11) y SecOps favorable con **§5.8** sobre el SHA final `82203f81`. Menor declarado: valores como `inf # comentario`/`1e999` no activan el recorte (sin impacto de seguridad; ampliar regex en el futuro). Límite: el reset no invalida la fila de `http_cache` del robots.txt.
- **Herald: carga perezosa — cerrada (2026-11-15, PR [#856](https://github.com/juanajok/zascarr/pull/856)):** `/ui/arcos` ya no hace red; la sección se hidrata con `hx-get`/`revealed once` desde `/ui/arcos/novedades-herald` (200 vacío si apagada/fallo, `no-store`, esqueleto sin layout shift). El tope de transferencia ya lo acota RES-3 (4 MiB) y el de parseo de Herald sigue en 1 MiB. Menor declarado: el error htmx de Importar no actualiza `aria-invalid`/`aria-describedby` (m-1/O1).
| **Lectura real de temas del foro** (SCR4) | Necesita URLs de hilos del usuario para validar con credenciales; hoy está cubierto con fixtures | Validar cuando haya URLs y añadir fixture/caso si el HTML real difiere |
- **Pantalla de importación de guías — cerrada (2026-11-15, PR [#846](https://github.com/juanajok/zascarr/pull/846)):** «Importar una guía» en Sagas en orden (fuente + URL, allowlist de los extractores, aviso de fuente apagada, cortesía y resultado con enlazados/omitidos); los errores y esperas se explican sin pantallas de error. Menores declarados: validación de URL antes que fuente apagada (O1), mensaje genérico (O2), commit fuera del `try` (m-1) y trazas potenciales en logs (m-2), sin impacto de seguridad.
| **Precisión del match por volumen** (SCR3) | Requiere datos reales y ajuste fino con falsos positivos | Medir con N guías reconciliadas antes de tocarlo |

## Cerradas en el lote 2 (2026-11-15, PR [#850](https://github.com/juanajok/zascarr/pull/850))

- **SCR7 O1** (inanición del lote de huecos): `_enrich_huecos_por_id` rota por `enrichment_attempted_at` (actualizado al procesar) y el `limit` solo lo consumen series cubribles; las fuentes cortadas no cuentan y las series sin huecos cubribles se marcan 30 d. Menores restantes declarados: prefetch `max(limit*50, 500)` y corte transitorio que puede hacer rotar una serie sin petición.
- **SCR7 O2**: GCD/Metron/Open Library tratan payload vacío como `None` (igual que 404), sin borrados.
- **SCR7 O3**: la atribución de relleno se muestra aunque la URL de ficha no valide (texto sin `href` vacío ni esquemas peligrosos).
- **Guía UI m-1/m-2**: el `commit` y la lectura van dentro del `try` (200 con aviso, `rollback`, sin 500) y el log genérico ya no vuelca trazas ni URL.

Riesgo residual aceptado: O4 (la marca de 30 d también se pone tras un relleno exitoso) es lo que pide la spec de SCR7. Pendientes de la fase UI/UX: carga perezosa de «Novedades» de Herald y validación real de la lectura de temas del foro.

## Pendientes de producto

- **ADR 0018** (caché HTTP y fuentes externas) sigue «Propuesto»: implementado desde SCR1; falta la
  aceptación del PO.
- **SCR7** (GCD/Metron/Open Library rellenando huecos) en backlog (#736).
