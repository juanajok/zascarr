# Medición AC-12 — BL-PORT1 (#300): coste de la portada en la Pi

> **Evidencia del criterio 4 del issue #300** (NFR-02…NFR-06 de
> `docs/design/especificacion-BL-PORT1.md`). **Fecha:** 2026-11-05.
> **Código medido:** rama `feat/300-portadas-v2` @ `e0d6ea50163b249b5a941e8a3fde70b55818a7f5`
> (commit `e0d6ea5`, «medicion: el banco usa el tamaño real del original y no publica rutas»).
> **Banco:** `scripts/medicion/banco_portadas.py` (solo lectura: no escribe en la caché, ni en la
> base de datos, ni abre ningún archivo en modo escritura).
> **Regla de evidencia:** esta ficha **solo lleva cifras y recuentos**. No incluye rutas de disco ni
> nombres de archivo reales; el JSON del banco tampoco publica rutas (a lo sumo, nombre de fichero y
> recuentos por motivo), y esta ficha no reproduce nombres.
> **Decide el PO.** La ficha de benchmark y esta medición son insumo; la ratificación de Q-4 es del
> PO (§6).

---

## 1. Entorno

| Aspecto | Valor |
|---|---|
| Equipo | Raspberry Pi del PO (modelo y versión de SO **no registrados** en el informe; no se infieren) |
| Contenedor | uno de un solo uso (efímero) de la app, con la biblioteca montada; no queda en marcha al terminar |
| Imagen | local de Compose para el servicio `zascarr` (nombre por defecto `zascarr-zascarr`), sin tag publicado; construida desde el `Dockerfile` del repo con el código de la rama |
| Código | `feat/300-portadas-v2` @ `e0d6ea5` (commit completo `e0d6ea50163b249b5a941e8a3fde70b55818a7f5`) |
| Presupuesto de RAM | contenedor de 512 MB (`docker-compose.yml`); pico medido del proceso: 144,6 MB |
| Fecha de la medida | 2026-11-05 |

**Nota de honestidad:** la medida se hizo en el contenedor de la app, con la biblioteca del PO como
material; no es una réplica del entorno de desarrollo ni un banco sintético. El resultado vale para
orden de magnitud y para PASS/FAIL de los umbrales, no para inferir la distribución de toda la
biblioteca (§8).

---

## 2. Comando ejecutado

Dentro del contenedor de un solo uso, desde la raíz del repo:

```bash
python scripts/medicion/banco_portadas.py \
    --carpeta <biblioteca montada> \
    --muestra 30 --repeticiones 5 --rss \
    --json <informe>.json
```

- `<biblioteca montada>` y `<informe>.json` se omiten por la regla de evidencia sin rutas.
- `--rss` anota el delta de RSS del proceso (`ru_maxrss`).
- El banco recorre `.cbz`/`.zip`, no escribe nada y no toca la base de datos.
- La muestra es **determinista**: los 30 primeros archivos por ruta ordenada (no aleatoria).

---

## 3. Muestra y método

| Aspecto | Valor |
|---|---|
| Candidatos de la muestra | **30** (los 30 primeros `.cbz`/`.zip` por ruta ordenada) |
| Medidos | **29** |
| No medibles | **1** archivo ilegible (excluido de los percentiles; no se publica su nombre) |
| Repeticiones | **5** por archivo y ancho |
| Anchos medidos | **240** («Por revisar») y **600** (Biblioteca, Inicio y ficha) |
| Extracciones totales | 29 × 2 anchos × 5 repeticiones = **290** |
| Percentiles | p50 y p95 por rango más cercano, sobre los tiempos agrupados de todos los archivos |
| Exención de p95 | 600 ms si el **original** supera 12 Mpx (se lee el tamaño real de la primera página, no el de la salida ya reducida) |
| Salida adicional | ancho/alto de salida y píxeles del original, para comprobar que no se amplía |

---

## 4. Resultados

| Ancho | p50 | p95 | límite aplicado | bytes medios |
|---:|---:|---:|---:|---:|
| 240 | 47,5 ms | 72,1 ms | 400 ms | 20,9 KB |
| 600 | 79,7 ms | **156,2 ms** | 400 ms | **93,7 KB** |

Otros datos medidos:

- **No se amplió ningún original.** Las 29 salidas a 600 midieron 600 px de ancho; 0 archivos por
  debajo de 600 (ningún original pequeño en la muestra). La exención de 600 ms para originales
  > 12 Mpx no fue necesaria para el PASS.
- **ΔRSS del proceso: 65,5 MB** (pico 79,1 MB → 144,6 MB). Cabe dentro del contenedor de 512 MB.
- **Sobrecoste de 600 frente a 240:** p95 ×2,2 (72,1 → 156,2 ms) y bytes ×4,5 (20,9 → 93,7 KB).
  El ancho de revisión («Por revisar») no cambia: sigue a 240 con su p95 de 72,1 ms.

---

## 5. Veredicto por umbral (PASS / FAIL / NOT RUN separados)

| Umbral | Valor | Medido | Veredicto |
|---|---|---|---|
| p95 de extracción a **240** | ≤ 400 ms | 72,1 ms | **PASS** (5,5× de margen) |
| p95 de extracción a **600** | ≤ 400 ms (≤ 600 ms si original > 12 Mpx) | **156,2 ms** | **PASS** (2,6× de margen) |
| Media de bytes por portada a 600 | ≤ 60 KB (propuesto) | **93,7 KB** | **FAIL del umbral propuesto** → **PASS** con el ratificado de 100 KB (§6) |
| ΔRSS del proceso | ≤ 40 MB (propuesto) | **65,5 MB** | **FAIL del umbral propuesto** → **PASS** con el ratificado de 80 MB (§6) |
| Sin ampliar originales | 0 ampliados | 0 de 29 | **PASS** |
| 30 portadas en frío con 6 concurrentes | ≤ 6 s | — | **NOT RUN** |
| Lectura caliente (304) | ≤ 30 ms | — | **NOT RUN** |
| `docker stats --no-stream` / cgroup | — | — | **NOT RUN** |
| `du` real de la caché / extrapolación a 1000 series | — | — | **NOT RUN** |

**Lectura.** El criterio de tiempo se cumple con holgura (2,6× en 600). Los dos umbrales que
fallan son **propuestas** de la ficha §10.1, no medidas; con el dato delante el PO los revisa y
ratifica (§6). **Ningún FAIL se convierte en PASS por conveniencia: el FAIL queda escrito.**

---

## 6. Decisión del PO — ratificación de Q-4 (2026-11-05)

Con la medida delante, el PO **mantiene 600 px** y ratifica Q-4 con dos umbrales nuevos:

| Umbral | Antes (propuesta) | **Ratificado** | Base |
|---|---|---|---|
| Media de bytes por portada (600) | ≤ 60 KB | **≤ 100 KB** | medido 93,7 KB; ≈ 100 MB/1000 series, ~1 % de una biblioteca de 8 GB |
| ΔRSS del proceso | ≤ 40 MB | **≤ 80 MB** | medido 65,5 MB; pico total 144,6 MB dentro del contenedor de 512 MB |

**Por qué no se baja a 480:** en el móvil de una columna (290 CSS) 480 da 1,66×, no 2×; el objetivo
de la historia es nitidez a 2× (la medida de presentación de §9.2 de la spec descartó 480 con
1,66×/1,47×). Bajar el ancho no es una salida válida para ahorrar bytes.

**Consecuencias:**

- La spec pasa a **v0.3**: NFR-05 (ΔRSS ≤ 80 MB) y NFR-06 (≤ 100 KB/portada y ≤ 100 MB/1000
  series) con los valores ratificados; AC-12 pasa a **PASS en tiempo** y **FAIL en los dos
  umbrales propuestos**, que con la ratificación son **PASS**.
- Las constantes del banco se alinearon con lo ratificado en el mismo PR (`UMBRAL_MEDIA_BYTES = 100 KB`,
  `UMBRAL_RSS_MB = 80 MB`). La medida que imprimió `RESULTADO: FAIL` se hizo **antes** de ese cambio,
  con las constantes propuestas (60 KB / 40 MB); con las ratificadas, la misma medida da PASS en los
  tres criterios. El veredicto válido es el de esta tabla, no el código de salida histórico.

---

## 7. Qué queda NOT RUN

El banco no mide la página ni el disco (ficha §10.2); queda pendiente y **no se sustituye por un
PASS supuesto**:

1. **30 portadas en frío con 6 peticiones concurrentes** (≤ 6 s) — coste real de abrir una rejilla,
   no solo de extraer una portada.
2. **Lectura caliente (304) ≤ 30 ms** — coste de revalidar con `If-None-Match`.
3. **`docker stats --no-stream` y cgroup** (`memory.current`, `cpu.stat`) durante la página.
4. **`du` real del directorio de caché** y extrapolación a 100/1000 series con la media real (el
   §4.º de esta ficha solo da la media por portada del banco, no el tamaño del directorio).

También queda fuera de esta ficha la verificación en navegador real (AC-21 de la spec).

---

## 8. Límites de la evidencia

- **Muestra determinista, no aleatoria:** los 30 primeros por ruta ordenada. Sirve para orden de
  magnitud y para PASS/FAIL; no describe la distribución de toda la biblioteca.
- **29 de 30 medidos:** 1 archivo ilegible. El porcentaje de ilegibles no es una medida de la
  biblioteca (n = 30), solo una incidencia de la muestra.
- **Ruido de la Pi:** la medida se tomó en la Pi del PO, compartida con otros servicios del
  contenedor; **no consta** que se fijara afinidad de CPU en esta ejecución ni se registró la carga del
  host. El p95 queda con 2,6× de margen, así que el ruido no cambia el PASS de tiempo.
- **Modelo de Pi y SO no registrados:** no se infieren; si una decisión futura depende del modelo,
  hay que medirlo.
- **No hay telemetría** (CLAUDE.md §5.3): esta ficha es una medida puntual, no un panel.

---

## 9. Referencias

- Issue #300 (`BL-PORT1`) y su criterio 4.
- `docs/design/especificacion-BL-PORT1.md` (v0.3): AC-12, NFR-02…NFR-06, Q-4 y §9.3.
- `docs/design/benchmark-BL-PORT1.md` (2026-11-04): umbrales propuestos en §10.1 y plan de medida en
  §10.2.
- `scripts/medicion/banco_portadas.py` y `tests/test_medicion_portadas.py` (rama `e0d6ea5`).
