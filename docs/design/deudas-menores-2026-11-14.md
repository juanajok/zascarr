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
| **M-4** tope de `Crawl-delay` y reinicio del estado de robots al apagar/encender fuente (SCR1) — [tarea #813](https://github.com/juanajok/zascarr/issues/813) (P2, S, «Lista para desarrollar») | Toca `robots.py` y el guardado de Ajustes (§5.8); la política actual ya solo **sube** el intervalo y el proceso es único | Tarea corta con tope (p. ej. 60 s) y reset en el toggle |
| **Herald: carga perezosa de la sección** (O2 QA) y **tope 1 MiB tras descargar** (o-1 SecOps) | La sección pide el feed en el GET de `/ui/arcos` (primera carga ≤3,5 s por cortesía); el tope real depende de RES-3 | Carga asíncrona/htmx con caché caliente y, junto a RES-3, tope antes de bufferizar |
| **Lectura real de temas del foro** (SCR4) | Necesita URLs de hilos del usuario para validar con credenciales; hoy está cubierto con fixtures | Validar cuando haya URLs y añadir fixture/caso si el HTML real difiere |
| **Pantalla de importación de guías** (SCR3) | Es una feature de UI, no una deuda menor | Historia propia: formulario URL + fuente + vista previa de reconciliación |
| **Precisión del match por volumen** (SCR3) | Requiere datos reales y ajuste fino con falsos positivos | Medir con N guías reconciliadas antes de tocarlo |

## Pendientes de producto

- **ADR 0018** (caché HTTP y fuentes externas) sigue «Propuesto»: implementado desde SCR1; falta la
  aceptación del PO.
- **SCR7** (GCD/Metron/Open Library rellenando huecos) en backlog (#736).
