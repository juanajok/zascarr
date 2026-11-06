# Medición BL-PORT1 (3/3): censo de portadas por debajo del objetivo (#411)

> **Estado:** entrega del **script** y de las pruebas del clasificador (AC-15/AC-16). La
> **ejecución real en la Pi** queda **NOT RUN** hasta lanzar el comando de §4 sobre la
> instalación con PR-1 desplegado (la caché `covers/v2` tiene que existir); este documento no
> inventa cifras. La decisión sobre BL-PORT2 se toma con la tabla que produzca esa ejecución.
> **Base:** `main` al 2026-11-06. Sin dependencias nuevas, migración ni cambios de esquema.

## 1. Qué mide

Una pasada **de solo lectura** sobre la base y los ficheros reales. Para cada `Series` lee la
cabecera del JPEG cacheado (preferir `covers/v2/<id>.jpg`; la legada no cuenta como objetivo) y,
si no está a 600, mira el **primer `File` no ausente** con el mismo camino que
`web/series.py::portada`: `puede_tener_portada` y la lectura acotada de la primera página
(`core/formato_contenedor`), leyendo **solo la cabecera** de la imagen, sin decodificar.

Cada serie cae en **una** de las seis clases de FR-14:

| Clase | Qué significa |
|---|---|
| `ya_en_objetivo` | `covers/v2/<id>.jpg` existe y mide ≥ 600. |
| `regenerable_al_pedir` | No hay v2, el primer `File` se extrae y su primera página mide ≥ 600: la próxima visita la regenera. |
| `extraible_mas_adelante` | El primer `File` no se extrae, pero otro posterior sí; la cascada solo mira el primero. |
| `original_pequeno` | Se extrae, pero la primera página mide < 600 (no se amplía). |
| `sin_extractor` | Ningún `File` extraíble (CBR/PDF/EPUB reales) o solo `cover_url`: no hay página local. |
| `sin_fuente` | No hay ningún `File` no ausente ni `cover_url`. |

**Cifra para decidir BL-PORT2:** `original_pequeno + extraible_mas_adelante + sin_extractor +
sin_fuente` (§9.5 de la spec). `regenerable_al_pedir` **no** cuenta como problema: se arregla
solo al visitar la serie. La decisión final es del PO con esa cifra.

## 2. Garantías de solo lectura

- No escribe en la base (solo un `SELECT`), ni en la caché, ni en los ficheros de la biblioteca.
- La única escritura es el informe: `--json` y, opcionalmente, `--csv` (ids y clases, **sin
  rutas ni nombres**).
- No descarga nada: no hay red en el script (solo abre PostgreSQL en la red interna de Compose).
- El I/O de disco va en un bucle síncrono acotado dentro de `asyncio.to_thread`; no se ejecuta
  dentro del servidor.

## 3. Pruebas (PASS)

`tests/test_medicion_portadas.py` (además del banco de AC-12):

- **PASS** — clasificador puro con probe inyectado: las seis clases, incluido «el primero no
  extraíble y el segundo sí», y «un segundo grande no arregla un primero pequeño».
- **PASS** — probe real con CBZ mínimos: cabecera 1600×2400, 400×600, `.cbr` real (sin
  extractor), `.cbz` falso y fichero ausente.
- **PASS** — clasificación de principio a fin con caché temporal (seis clases en una pasada) y
  `covers/v2` de 400 que no cuenta como objetivo.
- **PASS** — la cifra de BL-PORT2 excluye `regenerable_al_pedir`; JSON/CSV sin rutas.
- **PASS** — sin escritura en la caché ni en los ficheros de entrada durante la clasificación.

## 4. NOT RUN: ejecución real en la Pi

Requisito: PR-1 desplegado (la v2 existe) y una pasada de uso normal para que la regeneración
perezosa haya actuado. Desde el directorio del repo en la Pi (con `.env` cargado por Compose):

```bash
mkdir -p /tmp/censo-portadas

docker compose run --rm --no-deps \
  -v "$PWD/scripts/medicion/censo_portadas.py:/app/scripts/medicion/censo_portadas.py:ro" \
  -v /tmp/censo-portadas:/informe \
  zascarr python scripts/medicion/censo_portadas.py \
    --covers /config/covers \
    --json /informe/censo-portadas.json

cat /tmp/censo-portadas/censo-portadas.json
```

- `docker compose run --rm --no-deps` crea un **contenedor de un solo uso** con el entorno,
  la red interna, la biblioteca y la caché del servicio `zascarr`; no reinicia ni redespliega
  nada. El script se monta desde el repo para no depender de que la imagen lo incluya.
- La base se lee con `DATABASE_URL` del Compose (solo `SELECT`).
- El JSON queda en `/tmp/censo-portadas/censo-portadas.json` del host (única escritura).
- El script imprime la tabla por clase y total; el JSON añade `serie_id` y `clase` por serie,
  `cifra_bl_port2` y `estado` (`lectura`/`clasificacion`/`decision_BL_PORT2`).

Con la salida real, actualizar este documento con la tabla, el `PASS/FAIL/NOT RUN` de la
ejecución y la decisión sobre BL-PORT2. Sin esa ejecución, AC-15 queda **NOT RUN** y no se
convierte en PASS.
