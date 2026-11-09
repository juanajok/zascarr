# Medición BL-CNV0 — coste y convertibilidad de CBR en la Pi

> **Tarjeta:** #477 / BL-CNV0. **Fecha:** 2026-11-09. **Entorno:** Raspberry Pi 4 (aarch64, Debian 13, 4 núcleos, 4 GiB RAM), biblioteca en el disco externo de la Pi (ext4, 3,6 TB, 70 % usado). **Sin escritura en la biblioteca:** solo se leyeron cabeceras y se copiaron ficheros a `~/eval-cnv/muestras`. Contenedor desechable `--network none --read-only --memory=512m --memory-swap=512m`, imagen de evaluación histórica `zascarr-eval-rar:local` (**unar/lsar 1.10.1**, ID `8792cab5…`, 2026-10-23) y **pasada nueva con la imagen de producción `zascarr-zascarr:latest` (unar/lsar 1.10.8, ID `06a32079…`, 2026-11-09)**; misma muestra y umbrales. La extracción temporal va a un directorio de disco en `~/eval-cnv/trabajo`, **fuera** de la biblioteca.
>
> **No es una conversión real de la biblioteca.** Las copias de la muestra se hicieron con `cp` y hash SHA-256 comprobado; el original no se abrió para escribir. Los scripts están en `scripts/medicion/evaluacion_cnv/`.
>
> Autorización PO/P5 registrada en #477: consultas de solo lectura a Transmission/aMule y Kavita; si una consulta no era posible, se marca **NOT RUN**. La biblioteca no se montó en ningún contenedor de conversión.

## 1. Censo de los CBR registrados

Fuente: tabla `files` de la instalación (PostgreSQL), solo `file_path LIKE '%.cbr'`; **4.545 CBR registrados** (frente a 4.548 `.cbr` en el disco: 3 no registrados). El censo de cabeceras leyó los primeros 4 KiB de cada uno, sin descomprimir:

| Clase | Recuento | Método |
|---|---:|---|
| CBR registrados | **4.545** | `files` de la BD real, solo lectura |
| Legibles para el censo de cabeceras | **4.531** (99,69 %) | cabecera de 4 KiB |
| Ilegibles / no accesibles | **14** (0,31 %) | `ENOENT/EACCES`; no se pudieron clasificar ni copiar |
| RAR4 | **3.951** | firma + cabecera RAR4 |
| — RAR4 sólido | **125** | bandera de cabecera |
| — RAR4 no sólido | **3.826** | bandera de cabecera |
| RAR5 | **223** | firma + cabecera RAR5 |
| — RAR5 sólido | **2** | bandera de cabecera |
| — RAR5 no sólido | **221** | bandera de cabecera |
| **Sólidos totales** (RAR4+RAR5) | **127** (2,80 % de los legibles) | cabecera |
| Cifrados | **0** | cabecera; el 0 es un resultado de esta biblioteca, no una promesa general |
| `.cbr` que en realidad son **ZIP** | **357** (7,88 %) | firma ZIP; D5: se renombrarían, no se recomprimen |
| Otros formatos | **0** | ninguna firma RAR/ZIP/7z en los legibles |

El listado `lsar` se ejecutó sobre las **26 copias** de la muestra (26/26 listables, 0 entradas anidadas) y sirvió para el manifiesto de la conversión. **El barrido `lsar` de los 4.545 CBR no se completó** (el listado por fichero en la Pi es lento y se detuvo al agotar el tiempo de la tanda): los recuentos de dañados/anidados/multivolumen de *toda* la biblioteca quedan **NOT RUN**; los de formato, sólido, cifrado y ZIP son de cabecera. **No se descomprimió ningún original.**

### Distribución de tamaño (BD, CBR registrados)

| Cuantil | Tamaño |
|---|---:|
| mínimo | 45.998 B |
| p25 | 10,4 MB |
| mediana | 15,8 MB |
| p75 | 25,7 MB |
| máximo | 1.995,8 MB (dos ficheros ~2 GB) |
| > 300 MB | 126 ficheros |

## 2. Muestra reproducible

Regla fija implementada en `scripts/medicion/evaluacion_cnv/seleccionar_muestra.py`, sin elección manual:

- 4 sólidos: el mayor ≤ 300 MB y tres cuantiles de tamaño;
- 4 RAR5: el mayor ≤ 300 MB y tres cuantiles;
- 2 `.cbr` que son ZIP (ZIP disfrazado);
- 16 típicos RAR4/RAR5 de 1–150 MB, ordenados por `sha256(ruta)` (reproducible);
- hasta 2 `lsar` no listables/filename anidado/multivolumen si el censo los encuentra.

**Resultado:** **26 copias** (24 RAR + 2 ZIP), **989.320.853 B** (943,5 MiB). Cada copia tiene su SHA-256 comprobado contra el original y quedó en solo lectura (`m01`…`m26`). La muestra incluye **4 sólidos** (el mayor, 215,8 MiB) y **4 RAR5**, además de 2 ZIP disfrazados y 16 típicos. No hay cifrados en la biblioteca; **cifrado = NOT RUN** (no hay muestra).

Archivo de correspondencia interno: `~/eval-cnv/salida/muestras.tsv` (no se publican rutas ni nombres en este informe).

## 3. Umbrales P10 fijados antes de medir

Se fijan **antes** de la pasada de conversión y se aplican a la **muestra convertida con éxito**. «P10» = percentil 10 de la muestra (el 10 % más favorable); se añaden P90 y máximo para la cola contraria. Los presupuestos duros:

| Métrica | P10 | P90 | Máximo | Nota |
|---|---:|---:|---:|---|
| Tiempo total por CBR (unar + zip) | ≤ **10 s** | ≤ **30 s** | ≤ **120 s** | presupuesto de una conversión en la Pi; muestra hasta 311 MB |
| RSS del proceso `unar`/Python | ≤ **128 MiB** | ≤ **256 MiB** | ≤ **384 MiB** | RSS del proceso; el pico de cgroup se informa aparte |
| Pico de cgroup en la conversión | ≤ **384 MiB** | ≤ **384 MiB** | ≤ **384 MiB** | límite del contenedor 512 MiB; se exige margen |
| Espacio temporal / CBR | ≤ **1,25×** | ≤ **1,50×** | ≤ **2,00×** | extracción completa antes de comprimir |
| Tamaño CBZ / CBR (`ZIP_STORED`) | ≤ **1,05×** | ≤ **1,15×** | ≤ **1,25×** | sin recomprimir; puede crecer por cabeceras ZIP |
| Verificación | **100 %** nombres, tamaños, CRC y `testzip` | — | — | fallo de una sola entrada = FAIL de esa copia |

PASS si **P10, P90 y máximo** de las copias válidas cumplen; una extracción fallida se cuenta como **FAIL de convertibilidad** de esa copia, aunque la media sea buena. La memoria **no se mide en tmpfs**: el temporal va a disco (si no, la propia extracción consumiría el presupuesto y se confundiría con un problema de la herramienta).

## 4. Métricas de conversión — pasada histórica 1.10.1

Contenedor por copia, sin red, root read-only, 512 MiB sin swap; una copia por contenedor para que el pico de memoria sea por fichero. `unar` extrae a un directorio temporal en disco, `zipfile` escribe `ZIP_STORED`, `testzip` y comparación de manifiesto contra `lsar`.

**Resultado global:** **23 de 26 copias convertidas y verificadas**; **3 fallos de extracción con `unar`**. Las 23 verificadas tienen nombres, tamaños y CRC iguales y `testzip = None`; no se detectó una copia publicada con contenido distinto.

| Métrica (23 válidas) | P10 | P50 | P90 | Máximo |
|---|---:|---:|---:|---:|
| Tiempo total (s) | **0,124** | 0,357 | **3,110** | **11,360** |
| `unar` (s) | 0,143 | 0,302 | 1,614 | 4,991 |
| `zipfile` (s) | 0,011 | 0,024 | 0,103 | 1,422 |
| RSS (MiB) | **12,1** | 12,7 | **15,1** | **114,6** |
| Pico cgroup (MiB) | **33,8** | 54,9 | **202,2** | **512,0** |
| Espacio temporal / CBR | 1,000 | 1,015 | 1,072 | **1,113** |
| CBZ / CBR | 1,000 | 1,015 | 1,072 | **1,113** |

Las 23 válidas son 21 RAR + 2 ZIP renombrados. Los ZIP disfrazados se copiaron y verificaron como CBZ sin recomprimir (ratio 1,000; tiempo 0,084–0,105 s).

### Casos de la muestra

| Caso | Tipo | Resultado | Lectura |
|---|---|---|---|
| `m01` | Sólido RAR4, 215,8 MiB | **Convierte y verifica**; 11,36 s; pico cgroup **512 MiB** | Usa todo el límite de memoria; no queda margen. |
| `m05` | RAR5, 296,6 MiB | **Convierte y verifica**; 4,26 s; pico cgroup **512 MiB** | Usa todo el límite de memoria; no queda margen. |
| `m07` | RAR5 típico | **`unar` falla** (`Attempted to read more data...`) | `lsar -t`: 26 OK, **1 fallo**; `unrar t`: OK. No se publica CBZ; la copia original queda intacta. |
| `m14` | RAR5 típico | **`unar` falla** | `lsar -t`: 123 OK, **11 fallos**; `unrar t`: OK. |
| `m16` | RAR4 típico | **`unar` falla** | `lsar -t`: 49 OK, **2 fallos**; `unrar t`: OK. |

Por tanto, el coste de las copias **pequeñas/medianas** es bajo (P90 3,11 s, pico cgroup P90 202 MiB), pero **los dos casos grandes consumen exactamente los 512 MiB del contenedor** (sin margen; el presupuesto de 384 MiB de pico cgroup no se cumple) y **`unar` 1.10.1 no extrae 3/24 RAR de la muestra**, aunque `unrar` los considere íntegros. Esos fallos son de la herramienta/versión, no del contenedor.

### 4bis. Repetición con la imagen de producción `unar` 1.10.8

Misma muestra de 26 copias (hashes original=copia comprobados de nuevo), mismos umbrales, mismo contenedor (`--network none --read-only --memory=512m --memory-swap=512m`), una copia por contenedor y temporal en disco. Imagen `zascarr-zascarr:latest` ID `06a32079…`; `unar -v` y `lsar -v` = **1.10.8**.

| Métrica (23 válidas) | P10 | P50 | P90 | Máximo |
|---|---:|---:|---:|---:|
| Tiempo total (s) | **0,133** | 0,390 | **3,261** | **13,659** |
| `unar` (s) | 0,163 | 0,308 | 1,553 | 7,336 |
| `zipfile` (s) | 0,012 | 0,024 | 0,103 | 1,883 |
| RSS (MiB) | **17,4** | 17,6 | **19,6** | **117,3** |
| Pico cgroup (MiB) | **38,3** | 58,7 | **207,2** | **512,0** |
| Espacio temporal / CBR | 1,000 | 1,015 | 1,072 | **1,113** |
| CBZ / CBR | 1,000 | 1,015 | 1,072 | **1,113** |

**Resultado:** **23/26 válidas y verificadas** (nombres, tamaños, CRC y `testzip`); **los mismos 3 fallos de `unar`** (`m07`, `m14`, `m16`) que con 1.10.1; los dos grandes `m01`/`m05` convierten y verifican, pero vuelven a alcanzar **exactamente 512 MiB** de pico cgroup. No cambian el tamaño CBZ/CBR ni el espacio temporal: el formato de salida es el mismo `ZIP_STORED`.

### Comparación 1.10.1 vs 1.10.8

| Versión | Válidas/26 | Fallos `unar` | Tiempo P50/P90/máx (s) | RSS P90/máx (MiB) | Cgroup P90/máx (MiB) | Ratio CBZ/CBR máx |
|---|---:|---:|---:|---:|---:|---:|
| 1.10.1 (evaluación) | 23 | 3/24 RAR | 0,357 / 3,110 / 11,360 | 15,1 / 114,6 | 202,2 / 512,0 | 1,113 |
| **1.10.8 (producción)** | **23** | **3/24 RAR** | **0,390 / 3,261 / 13,659** | **19,6 / 117,3** | **207,2 / 512,0** | **1,113** |

**Lectura:** 1.10.8 **no arregla** los 3 fallos de extracción de la muestra; el tiempo y el RSS de base suben ligeramente (P10 RSS de 12,1 a 17,4 MiB; P90 de tiempo de 3,11 a 3,26 s), el pico cgroup grande sigue en 512 MiB y el resultado de tamaño/espacio no cambia. La producción no empeora la corrección, pero tampoco elimina los FAIL de memoria/extracción; la conclusión de BL-CNV0 se mantiene y ahora está confirmada con la versión desplegada.

## 5. Archivos compartidos (D3)

Consultas de solo lectura a los clientes locales de la Pi:

| Cliente | Recuento | Evidencia |
|---|---:|---|
| Transmission | **0 CBR/CBZ registrados** en torrents | 9 torrents, 120 entradas de fichero; 0 extensiones `.cbr/.cbz` y 0 rutas de la biblioteca. Todos son música/vídeo/otros. |
| aMule | **0 CBR/CBZ registrados** en compartidos | `shareddir.dat` = 0 bytes; `IncomingDir` = 0 CBR/CBZ; la biblioteca no está entre las carpetas compartidas. |
| **Total compartición de la biblioteca** | **0 / 4.545 CBR y 0 / 515 CBZ** | No se encontró ningún archivo de la biblioteca compartido por los clientes consultados. |

`amuleweb` responde en `127.0.0.1:4711` pero exige contraseña (devuelve la pantalla de login); **la vista de compartidos de `amuleweb` es NOT RUN** porque no se dispone de la contraseña de administración y no se modificó la configuración de producción para obtenerla. El recuento anterior se apoya en `shareddir.dat`/`IncomingDir`, no en la vista web.

## 6. Kavita

Kavita está instalado y responde `/api/health` **200**; su base tiene **1.109 series**. **La prueba de cambio `.cbr → .cbz` (progreso de lectura y duplicados) es NOT RUN**: no hay una instancia de prueba aislada y cambiar la extensión de un fichero de la biblioteca real está prohibido por esta tarjeta. No se tocó Kavita ni su BD.

## 7. Vulnerabilidades de `unar`

La pasada histórica usa **unar 1.10.1** (`v1.10.1`; paquete Debian `1.10.1-2`) y la actual **1.10.8** (`v1.10.8`; imagen de producción). Consulta de solo lectura al tracker de Debian ([source package unar](https://security-tracker.debian.org/tracker/source-package/unar)): no figura ninguna fila CVE para el paquete en el momento de la consulta. El [changelog de Debian](https://metadata.ftp-master.debian.org/changelogs//main/u/unar/unar_1.10.1-2_changelog) incluye parches de *crash* de 2017. **No es una auditoría de seguridad**: es una consulta al tracker; los fallos de extracción de §4 son un riesgo de robustez independiente de CVE. **Revisión de vulnerabilidades completa: NOT RUN**.

## 8. PASS / FAIL / NOT RUN

### PASS

- **Censo de formatos y sólidos por cabecera**: 4.531/4.545 legibles; 3.951 RAR4 (125 sólidos), 223 RAR5 (2 sólidos), 357 ZIP disfrazados; 0 cifrados; 14 ilegibles contados. Muestra `lsar`: 26/26 listables, 0 anidados.
- **Muestra reproducible**: 26 copias, 943,5 MiB, hash original=copia, 4 sólidos y 4 RAR5; ZIP disfrazados incluidos.
- **Tiempo/espacio/tamaño de las copias válidas (ambas versiones)**: P10/P90/máx de tiempo, RSS, espacio temporal y ratio CBZ/CBR dentro de los umbrales; con 1.10.1 P90 3,110 s y con 1.10.8 P90 3,261 s; pico cgroup P90 202,2/207,2 MiB; ratio y espacio temporal máx 1,113×.
- **Verificación**: 23/23 conversiones válidas con nombres, tamaños, CRC y `testzip` correctos; originales intactos.
- **D3**: 0 CBR/CBZ de la biblioteca en Transmission/aMule; 0/4.545 y 0/515.

### FAIL

- **Memoria de los casos grandes sin margen (persiste con 1.10.8)**: `m01` (215,8 MiB, sólido RAR4) y `m05` (296,6 MiB, RAR5) convierten y verifican, pero su **pico de cgroup es exactamente 512 MiB**, el límite del contenedor; el presupuesto pre-registrado de pico ≤ 384 MiB **no se cumple**. En el límite no hay margen para variaciones ni para el siguiente tamaño.
- **`unar` falla en 3 de 24 RAR de la muestra** (`m07`, `m14`, `m16`) **también con 1.10.8**, pese a que `lsar -t` y `unrar t` dan resultados distintos; no se publica salida. La conversión con `unar` no cubre toda la biblioteca real sin una estrategia de fallback/validación.

### NOT RUN

- **Barrido `lsar` completo de los 4.545 CBR**: no terminó en la ventana de medición; la muestra sí se listó (26/26) y los formatos/sólidos/cifrados se censaron por cabecera.
- **Dañados/anidados/multivolumen globales**: no hay recuento completo; el listado `lsar` de la muestra no encontró entradas anidadas; no se pudo seleccionar un multivolumen porque no apareció ninguno por nombre en la regla de muestra.
- **Cifrado**: 0 CBR cifrados en el censo de cabeceras; no hay caso que medir.
- **Kavita**: cambio de extensión, progreso y duplicados; no hay instancia aislada y la biblioteca real no se toca.
- **`amuleweb`**: vista de compartidos; solo se obtuvo la pantalla de login (sin contraseña de administración).
- **Vulnerabilidades completas de `unar`**: solo consulta al tracker de Debian; no auditoría.
- **Navegador real / interfaz**: esta medición no abre la UI.
- **Conversión de los 4.545 CBR**: solo muestra de 26; el censo de cabeceras y `lsar` no convierte el resto.

## 9. Reproducción y límites

- Scripts: `scripts/medicion/evaluacion_cnv/{censo_lsar.py,seleccionar_muestra.py,convertir_uno.py,medir_muestras.sh}`.
- `censo_lsar.py` y `convertir_uno.py` se ejecutan dentro de contenedores desechables; `seleccionar_muestra.py` copia y verifica hash antes de medir. El temporal de conversión va a un directorio de disco fuera de la biblioteca (`~/eval-cnv/trabajo`).
- La muestra está sesgada por la regla (sólidos, RAR5, típicos) y por la biblioteca de una sola instalación; no extrapola a toda la colección. Los ZIP disfrazados no se recomprimen. El barrido `lsar` completo no se completó (NOT RUN); el censo de formatos/sólidos/cifrados sí es completo por cabecera.
- No se midió caché fría (los ficheros copiados estaban en el disco del sistema), ni concurrencia con Transmission/aMule/Kavita, ni la interfaz de usuario.
- **Ninguna escritura en la biblioteca**: el censo solo leyó cabeceras; la muestra se copió a `~/eval-cnv`; los contenedores de conversión solo montaron `~/eval-cnv/muestras` en lectura y el temporal en un directorio de disco aparte.
