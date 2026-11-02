# BL-SER1 (#303) — Retirar una serie de la biblioteca sin borrar sus archivos

Estado: **implementado, pendiente de revisión y despliegue**. Fecha: 2026-11-02.
Rama: `claude/303-retirar-serie`, fusionada con `origin/main` (`9d7fedf`). No hay migración ni
tabla nueva.

## 1. Qué problema resuelve

Hasta ahora, una serie solo se podía quitar de ZascArr con `DELETE /api/series/{id}`, que se niega
(`409`) si la serie tiene archivos vinculados, números o deseados. La persona que quería dejar de
seguir una serie tenía que desvincular archivo a archivo y borrar números a mano, o dejar la serie
en la biblioteca para siempre. BL-SER1 añade el recorrido explícito **«Retirar de mi biblioteca»**:
quita la serie de ZascArr, devuelve sus archivos a «Por revisar» y **no borra, mueve ni renombra
nada del disco**.

El patrón es *Unmatch* (BL-R0, Kapowarr `c191dda`): los archivos vuelven a la bandeja de revisión
con el mismo historial que una desvinculación normal (BL-R1a, #253) y se pueden volver a vincular
a otra serie o a la misma si se da de alta de nuevo.

### Fuera de alcance (decidido y aceptado)

- No se borra, mueve ni renombra ningún archivo del disco. La prueba de aceptación comprueba el
  hash SHA-256 de todos los archivos antes y después.
- No se crea tabla ni migración nuevas. El comprobante reutiliza `vinculacion_operaciones` con
  `resultado.tipo = "retirada_serie"`.
- No se cambia `DELETE /api/series/{id}` ni su contrato (`409` con dependientes).
- No se añade una exclusión permanente: la serie puede volver a darse de alta o descubrirse.
- No se despliega en la Pi ni se toca la biblioteca real dentro de este trabajo.

## 2. Contrato HTTP

### Vista previa (sin escrituras)

```
POST /api/series/{series_id}/retirada/previsualizar
```

Sin cuerpo. Respuesta `200` (`Cache-Control: no-store`) con:

```json
{
  "series_id": "…",
  "serie": {"id": "…", "titulo": "Flash", "anio": 1987, "total": 3, "politica": "ninguno"},
  "puede_retirar": true,
  "bloqueos": [],
  "numeros": [{"id": "…", "numero": "1", "volumen": 1, "formato": "single_issue",
               "archivos": 1, "lecturas": 0, "deseados": 0, "sagas": 0}],
  "archivos": [{"id": "…", "nombre": "Flash 01 (1987).cbz", "ruta": "/media/…",
                "numero": "1", "formato": "cbz", "falta_en_disco": false,
                "procedencia": "registrada"}],
  "deseados": [{"id": "…", "numero": 2, "estado": "wanted", "origen": "manual", "por_numero": false}],
  "alias": 0,
  "sagas": 0,
  "aviso_disco": "Los archivos del disco no se borrarán, moverán ni renombrarán.",
  "aviso_despues": "Los archivos vinculados vuelven a «Por revisar»…",
  "token": "…"
}
```

- Si hay bloqueos, `puede_retirar` es `false`, `token` es `null` y `bloqueos` explica el motivo.
- `404` si la serie no existe. `503` si el servidor no tiene clave de firma.
- La vista previa **solo lee**: no escribe en la base ni toca el disco (probado con instantánea de
  la BD y hash del disco).

### Confirmación

```
POST /api/series/{series_id}/retirada
{"token": "…"}
```

`200` con un resultado estable e idempotente:

| `resultado` | Cuándo | Efecto |
|---|---|---|
| `retirada` | se aplicó ahora | serie, números, deseados y alias fuera; archivos a «Por revisar» |
| `ya_retirada` | el token ya se aplicó (mismo `operacion_id`) | ninguno; devuelve el mismo informe |
| `omitido` + `motivo` | no se pudo aplicar | ninguno |

Motivos de `omitido`: `serie_inexistente`, `cambio_desde_la_vista_previa`, `en_curso`.

Errores: `422` token inválido o de otra serie; `410` token caducado; `503` conflicto de bloqueo o
resultado incierto (con `Retry-After: 1`); `500` error inesperado. Todos con `Cache-Control:
no-store` y sin códigos internos en la superficie HTML.

### UI

- Entrada: `/ui/series/{id}` → enlace **«Retirar de mi biblioteca»**, con el aviso de que no toca
  el disco.
- Vista previa y resultado: `/ui/series/{id}/retirar` (`GET` y `POST` de formulario).
- La misma ruta responde al panel solo cuando la petición es htmx (`HX-Request`), con
  `hx-target="#retirada"` y `hx-swap="outerHTML"`.
- Sin JavaScript funciona igual: formulario `method="post"` normal.
- Teclado: el enlace y el botón son enfocables y se activan con `Enter`. Probado en Chrome real.
- Móvil: probado con emulación de toque real a 390×844.

## 3. Token

Propósito propio `retirar_serie`, contexto = `series_id`. Un token de otra serie no vale en esta
URL (se comprueba en el servicio y en la capa web/API). Campos firmados: `version`, `serie_id`,
`huella` (SHA-256 del estado canónico) y `operacion` (UUID de la operación). TTL 15 minutos.
Tamaño fijo y acotado por `MAX_TOKEN_RETIRADA` (peor caso emitible), validado en API y formulario.

La `huella` firma el estado canónico completo, no una lista de nombres: se calcula con
`json.dumps(..., sort_keys=True)` sobre la serie, sus alias, números, archivos, deseados,
asignaciones vivas, participaciones en sagas y progreso de lectura. La confirmación vuelve a leer y recalcula con las filas ya
bloqueadas; si cambió, no se aplica nada. El progreso de lectura se incluye porque se borra en
cascada con los números: si alguien empieza o termina una lectura entre la vista previa y la
confirmación, la vista previa ya no vale y no se pierde en silencio.

## 4. Bloqueos

Solo bloquean:

- una asignación de archivos **viva** (`preparada` o `confirmada`) de la serie o de uno de sus
  archivos vinculados;
- un deseo de la serie o de sus números en estado `searching` o `downloading`.

Otros estados de deseo (`wanted`, `downloaded`, `failed`, `retirado`, …) no bloquean. El bloqueo
se muestra con su causa y un detalle en llano («el nº 2 se está buscando»). No hay exclusión
permanente.

## 5. Transacción, orden de bloqueo y carreras

1. Candado consultivo por `operacion_id` (idempotencia y serialización de reintentos).
2. Si ya existe informe para esa operación: se devuelve (`ya_retirada`) sin volver a aplicar.
3. Serie `FOR UPDATE`; si no existe → `omitido/serie_inexistente`.
4. Archivos vinculados `FOR UPDATE`, números `FOR UPDATE`, deseados `FOR UPDATE`, en ese orden.
5. Relectura completa del estado y comparación de huella.
6. Efectos: desvincular cada archivo con `aplicar_desvinculacion(...)` (misma semántica e
   historial que BL-R1a), borrar deseados, borrar la serie (cascada de números, alias y
   participaciones en sagas), escribir el comprobante y purgar informes viejos.
7. `COMMIT`. Si el commit se pierde, el reintento con el mismo token devuelve el informe ya
   guardado.

Los bloqueos de fila impiden que una asignación nueva se cuele mientras se aplica. Como red de
seguridad, la restricción `ck_asignacion_viva_con_referencias` impide dejar una asignación viva sin
serie; si la carrera ocurriera, la transacción se revierte y se responde `omitido/en_curso`.

## 6. Comprobante (sin tabla nueva)

Se reutiliza `vinculacion_operaciones`, que ya es inmutable (trigger que rechaza `UPDATE`) y se
purga a las 24 h con el token caducado. El informe lleva `resultado.tipo = "retirada_serie"`,
`version`, `operacion_id`, `fecha`, la serie y sus números, los archivos (id, `issue_id`, número,
formato, procedencia), los deseados, las sagas y los totales. **No** lleva rutas, nombres de
archivo, hashes, tokens ni sesión.

`leer_resultado` ignora los informes con `tipo` (no son vinculaciones) y `resumen_operaciones`
filtra `resultado.tipo IS NULL`, así que el comprobante de retirada no se cuenta como vinculación
ni infla el panel de operaciones.

## 7. Pruebas

### Postgres real y ficheros reales

`tests/test_retirada_serie_pg.py` (24 pruebas):

- vista previa sin escrituras, sin cambios en disco y con contenido/token correctos;
- bloqueo por asignación viva y por deseo `searching`/`downloading`; deseo `wanted` no bloquea;
- confirmación: serie, números y deseados fuera; archivos con `issue_id = NULL`,
  `review_dismissed = false` y una entrada en `vinculo_historial`; disco intacto;
- idempotencia (`ya_retirada`) y dos confirmaciones simultáneas del mismo token
  (`retirada` + `ya_retirada`, un solo comprobante);
- token de otra serie → `422`; cambio tras la vista previa (incluido vincular un archivo nuevo) →
  `omitido` sin cambios; cambio de progreso de lectura → `omitido` sin perder la lectura;
- serie borrada entre la vista previa y la confirmación → `omitido/serie_inexistente`;
- asignación viva que aparece en la carrera (red de seguridad `ck_asignacion_viva_con_referencias`) →
  `omitido/en_curso`, con la serie y los vínculos intactos;
- `DELETE /api/series/{id}` sigue devolviendo `409`;
- comprobante presente, sin rutas/nombres/hash/token y sin contarse como vinculación;
- errores de la API: `410` con y sin `puede_haberse_aplicado`, `404`, `503` sin clave, `503` de
  conflicto/resultado incierto con `Retry-After: 1`, `500` sin fugas; todos con `Cache-Control: no-store`;
- sagas: se borra la participación (`story_arc_issues`), no la saga.

`tests/test_retirada_serie_ui_pg.py` (28 pruebas):

- enlace en la ficha con aviso de disco y sin escrituras al entrar;
- vista previa: aviso destacado, conteos, alias/sagas/deseados, sin escrituras, `no-store`,
  contrato htmx y panel solo con `HX-Request`;
- bloqueos sin formulario y con causa; `wanted` no bloquea; sin códigos internos;
- confirmación sin JS y con htmx; resultado, «Por revisar», repetición sin escrituras, token de
  otra serie, token inválido, caducado con y sin «pudo aplicarse», cambio posterior, resultado
  incierto con «Comprobar el resultado», ficha ya inexistente, y `503` sin clave como HTML/panel
  (no como JSON colado).

`tests/test_tokens_retirada.py` (9 pruebas): ida y vuelta, caducidad, propósito, contexto,
esquema estricto, tamaño máximo.

Resultado local (Postgres 15 en Docker, `zascarr_test`):

```
tests/test_retirada_serie_pg.py       24 passed
tests/test_retirada_serie_ui_pg.py    28 passed
tests/test_tokens_retirada.py          9 passed
```

Suite PG completa, mismo conjunto que el job de CI (`grep -l TEST_DATABASE_URL tests/*.py`):

```
1811 passed, 2 skipped
```

Los 2 saltos son `test_restore_pg.py` y `test_zz_preparar_fixture_123a_pg.py`, que necesitan los
clientes `psql`/`pg_dump` de PostgreSQL 15 en el PATH; en esta máquina no están instalados. El job
`postgres` de CI los instala y exige **cero** saltos, así que allí se ejecutan. **No se han dado
por pasados en local.**

Suite no-PG completa (`pytest -q -rs`):

```
4855 passed, 1837 skipped, 1 failed
```

El único fallo es
`test_ensayo_f1bis_arnes.py::TestPresupuestoDeDescarga::test_se_corta_mientras_se_descarga_y_mata_el_grupo_entero`:
una prueba de tiempos (4 s) que tardó 4,5 s en este host, también con `--basetemp` en el disco
raíz. La prueba **aislada pasa**; es el fichero completo el que falla por interacción/tiempos. El
fichero es idéntico a `origin/main` y no toca código de la retirada; la `Suite unitaria` de CI
pasa. Se deja como **FAIL local conocido**, no se cuenta como PASS ni se oculta.

### Navegador real

Chrome headless por CDP, aplicación real contra Postgres real y una biblioteca temporal con
archivos reales. La captura se repitió **después** de fusionar `origin/main` (`9d7fedf`), para que
la evidencia corresponda al código final de la rama. Evidencia en
`/tmp/opencode/303-browser/capturas/` (fuera del repo):

| Captura | Qué demuestra |
|---|---|
| `01-ficha-escritorio.png` | enlace «Retirar de mi biblioteca» y aviso de disco |
| `02-ficha-enlace-enfocado.png` | enlace alcanzado solo con `Tab` |
| `03-vista-previa-escritorio.png` | vista previa con aviso destacado y recuentos |
| `04-previa-boton-enfocado.png` | botón alcanzado solo con `Tab` |
| `05-resultado-escritorio.png` | resultado tras pulsar `Enter` |
| `06-bloqueo-deseado-escritorio.png` | bloqueo por deseo en curso, sin formulario |
| `07-ficha-movil.png` | ficha a 390×844 |
| `08-vista-previa-movil.png` | vista previa tras toque real en el enlace |
| `09-previa-movil-boton.png` | botón visible en móvil |
| `10-resultado-movil.png` | resultado tras toque real en el botón |
| `11-por-revisar.png` | archivos devueltos a «Por revisar» |

`datos.json` registra: `resultado_dato = "retirada"` en escritorio y móvil,
`bloqueo_tiene_formulario = false`, `disco_intacto = true` (hash SHA-256 de todos los archivos
antes y después). La base quedó con las series retiradas en `404`, los archivos con
`issue_id NULL` y `review_dismissed false`, y dos comprobantes
`resultado.tipo = "retirada_serie"`.

### No ejecutado (NOT RUN) y por qué

- **Despliegue en la Pi y medición en el host real**: no autorizado; la Pi sigue fuera de este
  trabajo.
- **Biblioteca real**: no se toca. La prueba de disco usa una biblioteca temporal.
- **Clientes de PostgreSQL 15 en local**: no instalados; los 2 saltos de arriba los cubre el job
  de CI.
- **Revisión de Seguridad/QA/Pixel independiente**: se hizo una revisión QA/SecOps de la rama; no
  encontró bloqueantes y sus hallazgos importantes (caducado ambiguo, `no-store` en errores,
  `MissingGreenlet` en la carrera y pruebas que faltaban) están corregidos y cubiertos por las
  pruebas de arriba. La revisión Pixel formal como sesión independiente no se pudo lanzar en esta
  sesión (límite de la plataforma); se revisaron visualmente las 11 capturas y la plantilla. La
  revisión Pixel formal y la aceptación final quedan pendientes en el PR y requieren aceptación
  explícita del PO.

## 8. Rollback

La funcionalidad es aditiva: dos rutas nuevas, un servicio nuevo y una plantilla nueva. No hay
migración. Revertir el commit elimina las rutas y deja la tabla y el `DELETE` como estaban. Los
comprobantes ya escritos se purgan solos a las 24 h; no bloquean nada.

## 9. Riesgos y decisiones abiertas

- **Carrera con un deseo que empieza justo después de la relectura**: no se cuela. Un `INSERT`
  en `wishlist` que apunta a la serie (o a uno de sus números) necesita la clave foránea y toma
  `FOR KEY SHARE` sobre la fila de `series`, que esta transacción mantiene `FOR UPDATE`: espera
  al `COMMIT` y, cuando entra, la serie ya no está. No hace falta una restricción adicional ni
  una migración.
- **Asignación viva que aparece en la carrera**: además de los bloqueos, la restricción
  `ck_asignacion_viva_con_referencias` revierte la transacción y se traduce a
  `omitido/en_curso`; hay una prueba determinista con el gancho de pruebas.
- **Sagas**: borrar la serie borra sus participaciones, no las sagas. Es la cascada existente.
- **Deseados**: se borran los de la serie y los de sus números, incluidos los de política; no hay
  búsqueda ni descarga en curso porque eso bloquea.
