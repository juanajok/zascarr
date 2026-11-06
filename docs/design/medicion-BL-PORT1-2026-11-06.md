# Medición BL-PORT1 (3/3): censo de portadas por debajo del objetivo (#411)

> **Estado:** **ejecutado en la Pi el 2026-11-06** (20 series; PR-1 desplegado). Resultado:
> **9 de 20 ya a 600** y **11 CBR sin extractor, todas con `cover_url`**; cifra real para
> BL-PORT2 = **0**. El desglose de `sin_extractor` por `cover_url` corrige la cifra engañosa de
> la primera versión (que contaba 11). **Base:** `main` al 2026-11-06. Sin dependencias nuevas,
> migración ni cambios de esquema.

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

`sin_extractor` se **desglosa** en el informe con el `cover_url` ya leído: `con_portada_externa`
(la cascada la descarga a 600 al abrir la ficha; se resolverá sola) y `sin_portada_externa` (no
hay ninguna vía local ni externa; esto sí es problema de BL-PORT2). El JSON publica los dos
contadores; las seis clases no cambian (FR-14).

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
- **PASS** — la cifra de BL-PORT2 excluye `regenerable_al_pedir` y, dentro de `sin_extractor`,
  excluye los que tienen `cover_url`; solo cuenta `sin_extractor_sin_portada_externa`.
- **PASS** — CBR con `cover_url` sigue `sin_extractor` pero no cuenta; CBR sin `cover_url` sí
  cuenta; mezcla de ambos cuenta solo el segundo.
- **PASS** — JSON/CSV sin rutas y sin escritura en la caché ni en los ficheros de entrada.

## 4. Ejecución real en la Pi (2026-11-06) — PASS

Pasada sobre la instalación real con PR-1 desplegado, **20 series**:

| Clase | Series |
|---|---:|
| `ya_en_objetivo` | 9 |
| `regenerable_al_pedir` | 0 |
| `extraible_mas_adelante` | 0 |
| `original_pequeno` | 0 |
| `sin_extractor` | 11 |
| `sin_fuente` | 0 |
| **TOTAL** | **20** |

Desglose de `sin_extractor` (consulta adicional sobre las mismas series):

- **11 con `cover_url`** → se resuelven al abrir la ficha: la cascada descarga la portada
  externa y la cachea a 600; la próxima pasada del censo las contará como `ya_en_objetivo`.
- **0 sin ninguna portada** (ni local ni externa).

Por tanto:

- **9 de 20 ya están a 600** (PR-1 funciona; el 45 % de la biblioteca medida).
- **Cifra BL-PORT2: 0** — no hay ninguna serie que se quede por debajo sin una vía para
  resolverla. La primera versión del censo daba 11 porque metía en el mismo saco los CBR con
  `cover_url`; ese número era engañoso.
- **Decisión: NO hace falta BL-PORT2 con los datos actuales.** Se reevalúa si en una pasada
  futura aparece alguna serie `sin_extractor_sin_portada_externa` (o si las `cover_url`
  existentes resultan muertas o son la imagen de relleno de #311; ver NOT RUN).

### Comando usado

Desde el directorio del repo en la Pi, con `.env` cargado por Compose y PR-1 desplegado:

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

- `docker compose run --rm --no-deps`: contenedor de un solo uso con el entorno, la red
  interna, la biblioteca y la caché del servicio `zascarr`; no reinicia ni redespliega.
- La base se lee con `DATABASE_URL` del Compose (solo `SELECT`). La única escritura es el
  JSON del informe en `/tmp/censo-portadas/` del host.

### PASS / FAIL / NOT RUN de esta evidencia

- **PASS** — lectura de la base y clasificación de las 20 series (solo lectura; ni BD ni caché
  ni biblioteca modificadas).
- **PASS** — desglose de `sin_extractor` por `cover_url` (11 con, 0 sin) y cifra BL-PORT2 = 0.
- **NOT RUN** — **ninguna serie sin fuente** en esta instalación (la clase existe, pero no hay
  caso real que la ejercite aquí).
- **NOT RUN** — **red real de las `cover_url`**: no se ha comprobado que las 11 portadas
  externas respondan, ni que no sean la imagen de relleno de #311. Si alguna estuviera muerta,
  la serie no llegaría a 600 al abrir la ficha y el censo la seguiría contando como
  `sin_extractor_sin_portada_externa` en la próxima pasada; entonces sí tocaría reevaluar
  BL-PORT2. No se convierte en PASS.
