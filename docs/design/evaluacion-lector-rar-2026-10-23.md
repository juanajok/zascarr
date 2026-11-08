# Evaluación de un lector de RAR/CBR en la Pi (spike #308)

> **Estado: FICHA PARA REVISIÓN. Recomendación: SEGUIR INVESTIGANDO** (dos criterios clave de §7 quedan **NOT RUN**: seguridad y coste de dependencia). **No se ha implementado nada, no se ha tocado la imagen de ZascArr ni ninguna biblioteca**; las muestras eran copias con hash verificado, la biblioteca no se montó en ningún contenedor. Protocolo: `protocolo-evaluacion-lector-rar.md` (#312). Datos celda a celda: `evaluacion-lector-rar-2026-10-23-datos.md`.

## 1. Veredicto en pocas líneas
- **`unar` (y `unrar`, de pago aparte) leyeron las 10 muestras RAR** —RAR4, RAR5 y un sólido— con **≤ 25,3 MiB de pico** (umbral 256) y **≤ 0,2 s la primera página** (umbral 5 s), sin ninguna muerte por memoria. Medido **en la Pi**, con la caché de disco caliente (§6).
- **`bsdtar` (libarchive 3.6.2 de Debian) no abre los RAR sólidos** («RAR solid archive support unavailable»). `rarfile` con `bsdtar` como motor falla en 15 de 18 lecturas de página, también en RAR no sólidos.
- Un `.cbr` de la muestra **es un ZIP**: `unrar` y `rarfile` dicen «no es RAR»; `unar` y `bsdtar` lo leen. Hay que decidir por **contenido**, no por extensión (enlaza con #307).
- **Lo que no está medido** y impide recomendar «adoptar»: ficheros corruptos/cifrados y topes (seguridad), lectura en frío, tamaño de la imagen, `ComicInfo.xml` (ninguna muestra lo trae), y una sola muestra sólida.

## 2. Entorno (medido en la Pi, no en un PC)
| Dato | Valor |
|---|---|
| Equipo | Raspberry Pi 5, `aarch64` (Linux 6.18.50+rpt-rpi-2712), 4 CPU, 4049 MiB de RAM (1104 MiB disponibles al empezar) |
| Docker | 29.9.1 (arm64) |
| Carga al empezar | `load average` 0,28 / 0,30 / 0,43; sin descargas ni importaciones |
| Fecha | 2026-10-23, 00:15 (CEST) |
| Contenedor de medición | imagen desechable `zascarr-eval-rar:local` (sobre la imagen de ZascArr, `python:3.11-slim-bookworm`); `--network none --read-only --memory=512m --memory-swap=512m --cpus=2 --pids-limit 128 --cap-drop ALL`, `tmpfs` de trabajo de 128 MiB, muestras `:ro` |
| Método | cada operación en un **proceso nuevo**; 3 repeticiones; se informa la primera, la mediana y el máximo; pico = memoria residente máxima de los procesos hijo (`RUSAGE_CHILDREN`); muertes por memoria vigiladas en el cgroup; tope de 60 s por operación |
| Pasos con red | solo la construcción de la imagen desechable (autorizada por el PO en el chat el 2026-10-22); la medición, sin red |

## 3. Muestras (copias con `cp`, `sha256` igual al original en las 11)
| Id | Extensión en disco | Formato real (firma) | Sólido | Tamaño | Nota |
|---|---|---|---|---|---|
| m01 | ninguna | RAR 2.0/4 | no | 35 MB | novela gráfica |
| m02 | ninguna | RAR 4 | no | 20 MB | novela gráfica |
| m03 | `.rar` | RAR 4 | no | 56 MB | volumen de manga |
| m04 | `.rar` | RAR 4 | no | 189 MB | **paquete**: dentro hay ficheros con extensión de contenedor (§5.4) |
| m05 | ninguna | RAR 4 | no | 173 MB | el mayor |
| m06 | ninguna | **RAR 5** | no | 67 MB | |
| m07 | `.rar` | **RAR 5** | no | 57 MB | nombres con corchetes dentro |
| m08 | `.cbr` | RAR 4 | **sí** | 57 MB | **única muestra sólida** |
| m09 | `.cbr` | RAR 4 | no | 33 MB | |
| m10 | `.cbr` | RAR 4 | no | 43 MB | |
| m11 | `.cbr` | **ZIP** | no | 111 MB | un «CBR» que no es RAR |

## 4. Herramientas
| Candidata | Versión (arm64) | Origen / licencia | Resultado |
|---|---|---|---|
| `unar`/`lsar` | 1.10.7+ds1+really1.10.1-2+b2 | Debian bookworm **main**, LGPL-2.1+ | lee las 10 RAR (incl. RAR5 y sólido) y el ZIP |
| `bsdtar` (`libarchive-tools`) | 3.6.2-1+deb12u5 | Debian **main**, BSD | lee RAR4/RAR5 no sólidos y el ZIP; **no el sólido** |
| `unrar` | 1:6.2.6-1+deb12u1 | Debian **non-free** (licencia de RARLAB); solo comparación | lee las 10 RAR; no el ZIP |
| `rarfile` (Python) | 4.5 | PyPI, ISC (no está en la imagen de producción) | depende del motor: con `unar` y `unrar`, igual que ellos; con `bsdtar`, falla |

Para `rarfile` se evaluó **cada motor por separado** y el banco lo forzó explícitamente (`rarfile.tool_setup(force=True, …)`).

## 5. Resultados (resumen; todas las celdas en el fichero de datos)
RAR = m01…m10. Cada celda: celdas que pasan / celdas ejecutadas.

| Motor | listar | primera página | última página | Pico máx. (MiB) | Primera página, máx. (s) | Última página del sólido (s) |
|---|---|---|---|---|---|---|
| `unar` | 10/10 | 9/9 | 9/9 | 25,3 | 0,05 | 1,02 |
| `bsdtar` | 9/10 (falla el sólido) | 9/9 ¹ | 9/9 ¹ | 14,8 | 0,02 | — (no abre el sólido) |
| `unrar` | 10/10 | 9/9 | 9/9 | 14,8 | 0,01 | 0,69 |
| `rarfile` + `unar` | 10/10 | 9/9 | 9/9 | 25,3 | 0,19 | 1,14 |
| `rarfile` + `unrar` | 10/10 | 9/9 | 9/9 | 23,9 | 0,13 | 0,81 |
| `rarfile` + `bsdtar` | 10/10 | **0/9** | **3/9** | 23,3 | — | FAIL |

¹ Incluye `m04`, donde `bsdtar` enumera otras entradas (§5.4); los fallos son 9 de «primera» y 6 de «última». Para los demás motores `m04` es un paquete y «primera/última» es NOT RUN («sin entrada aplicable»), no PASS. De las 18 lecturas de página con `rarfile`+`bsdtar` fallan 15.

1. **Memoria.** Ningún pico supera 25,3 MiB (el 10 % del umbral de 256) y no hubo ninguna muerte por memoria en las 264 celdas. El RAR **sólido** (57 MB) también cabe: 25,3 MiB con `unar`.
2. **Tiempo.** Primera página ≤ 0,2 s en todas las muestras, también en la de 173 MB. La **última** página de un RAR sólido cuesta ~1 s (hay que descomprimir hasta ella; en los no sólidos, ≤ 0,05 s con las herramientas directas y ≤ 0,2 s con `rarfile`). Para portadas (la primera) no importa; sí para cualquier idea de «leer una página cualquiera».
3. **Escrituras.** `unar` no escribe a la salida estándar: extrae al `tmpfs` (de 0,06 a 1,1 MB por página en los RAR, 2 MB en el ZIP; el tamaño de la página). Los demás motores, 0 bytes. Quien integre `unar` necesita un directorio temporal acotado.
4. **`m04` es un paquete.** `lsar` lista 11 ficheros `.cbr` (un tomo con sus capítulos) más su carpeta: 12 entradas, que es lo que ven `unar`, `unrar` y `rarfile` con los tres motores; la regla «paquete» (idea adaptada de Kapowarr) lo marca, y por eso «primera/última» es NOT RUN. **`bsdtar` lista otra cosa**: 27 nombres de páginas (`00.png` … `36.jpg`) que no son ninguna de esas 12 entradas. **Anomalía sin causa determinada**: no se sabe si es un defecto de `bsdtar` con este fichero, de su lector RAR o de cómo se leyó la muestra, y **no se afirma** que `bsdtar` no pueda leer paquetes en general. Traza para reproducirla: muestra `m04` (copia con `sha256` igual al original), `bsdtar -tf /m/m04` con `bsdtar` 3.6.2-1+deb12u5 (arm64) en la imagen desechable `zascarr-eval-rar:local`, `--network none --read-only`, muestra montada `:ro`; el banco lo repite en `resultados.jsonl` (`bsdtar`, `listar`, «27 entradas»). Con la evidencia actual basta para **no recomendarlo**, junto con el RAR sólido, no para más.
5. **RAR5.** Las dos muestras (m06, m07) pasan con `unar`, `bsdtar` y `unrar`.
6. **Sólido.** `bsdtar` falla al listar (`RAR solid archive support unavailable`, estado FAIL con causa en la herramienta, no en el fichero). `unar` y `unrar` lo leen.
7. **`m11` (ZIP con extensión `.cbr`).** `unrar`, `rarfile`+(`unar`|`bsdtar`|`unrar`): FAIL («no es RAR»); `unar` y `bsdtar`: PASS. Este FAIL es esperable para herramientas solo-RAR; lo relevante es que **la extensión no sirve para elegir lector**.
8. **`rarfile` + `bsdtar`.** Falla con `BadRarFile: Failed the read enough data … got=51` (recibe 51 bytes en vez de la página; probablemente un mensaje de error de `bsdtar`, no comprobado). Texto confirmado en el `resultados.jsonl` de la ejecución final; no investigado más porque `bsdtar` ya falla por sí mismo en el sólido y no es candidato.
9. **`rarfile` frente a la herramienta directa.** Añade ~0,1–0,15 s por operación (primera página: 0,05 → 0,19 s) y una dependencia de PyPI, sin ampliar lo que se puede leer; la memoria es del mismo orden (19–25 MiB).

## 6. Límites de lo medido (leer antes de concluir nada)
- **«Pillow la decodifica» se comprobó con `Image.verify()`**, que valida la cabecera/estructura, **no** decodifica todos los píxeles. Un PASS de «página» significa «salieron bytes que Pillow reconoce como imagen», no «imagen íntegra». No se comparó el tamaño ni el CRC con el listado.
- **Lectura en caliente.** No se vació la caché de disco (`DROP_CACHES` no se usó) y las copias vivían en el disco de la Pi, no en el disco USB de la biblioteca. El «disco en frío» que pide el protocolo es **NOT RUN**.
- **Una sola muestra sólida** (57 MB). No permite estimar cuántos RAR sólidos hay ni cómo escala la memoria con uno de varios cientos de MB. El 7z sólido de #305 sí escaló mal (197 MiB con 100 MB); para RAR sólido no hay más dato que este.
- **Sin `ComicInfo.xml`:** ninguna de las 11 muestras lo trae → la operación «leer ComicInfo» es **NOT RUN** en las 66 celdas.
- **Sin RAR corrupto ni cifrado** (no hay con qué crearlos; el protocolo lo preveía): «fallo controlado» **NOT RUN**.
- **Sin topes probados** (entradas, tamaño descomprimido): `unar`/`lsar` no se ejercitaron con una bomba; la regla de ZascArr (`MAX_ZIP_ENTRIES`, `MAX_ZIP_UNCOMPRESSED`) es solo para ZIP.
- **Tamaño de la imagen:** medido solo **en conjunto**: `zascarr-zascarr:latest` 593 MB → imagen de evaluación 636 MB (**+43 MB**, un 7 %), con `unar`, `libarchive-tools`, `unrar` y `rarfile` juntos. **No es el coste de adoptar `unar` ni acredita por sí solo el criterio de dependencia.** El desglose por herramienta (lo que costaría solo `unar` con sus dependencias) **no está medido**.
- **Trazabilidad:** una ejecución anterior (00:01) se **descartó**: el banco pasaba mal los nombres con corchetes de `m07` a `unar` y `bsdtar` (fallo del banco, no de las herramientas). Se corrigió y se repitió entera; esta ficha usa solo la segunda.
- El kit de medición (banco, Dockerfile, pasos) está ahora en `scripts/medicion/evaluacion_rar/` (se añadió con la 2ª tanda); `muestras.ejemplo.txt` sustituye a la lista real de muestras, que lleva nombres de ficheros del PO.

## 7. Criterios de §7 del protocolo
| Criterio | `unar` | `bsdtar` | `unrar` | Nota |
|---|---|---|---|---|
| Compatibilidad (RAR4 y RAR5) | **PASS** | **FAIL** (sólido) | **PASS** | con la salvedad de `verify()`; `m04` solo «listar» |
| Memoria ≤ 256 MiB, sin muertes por memoria | **PASS** (25,3) | **PASS** (14,8) | **PASS** (14,8) | sólido: una muestra de 57 MB |
| Tiempo, primera página ≤ 5 s (~200 MB) | **PASS** en caliente (≤ 0,2 s) | **PASS** | **PASS** | en frío: **NOT RUN** |
| Seguridad (solo `tmpfs`; topes; corrupto/cifrado) | **NOT RUN** | **NOT RUN** | **NOT RUN** | solo se midió lo que escribe cada motor |
| Licencia (Debian `main` o aceptación del PO) | **PASS** (main, LGPL-2.1+) | **PASS** (main) | **requiere aceptación** (non-free) | `rarfile` es de PyPI: también requiere aceptación |
| Dependencia (coste en imagen y superficie) | **NOT RUN** | **NOT RUN** | **NOT RUN** | +43 MB en conjunto (593 → 636 MB); desglose sin medir; decisión del PO |

Regla de §7: hay NOT RUN en criterios clave → **seguir investigando**.

## 8. Recomendación
**Seguir investigando; no adoptar todavía.** La evidencia técnica es favorable a **`unar` invocado directamente** (sin `rarfile` y sin `unrar`): es el único de los tres que cubre RAR4, RAR5, sólido y ZIP con licencia de Debian `main`. `bsdtar` queda descartado como lector único (sólido). `unrar` no aporta nada que `unar` no dé en estas muestras y arrastra una licencia que el PO tendría que aceptar.

Para poder pasar a «adoptar» (o a «descartar») faltan, en este orden:
1. **Seguridad:** comportamiento ante un RAR truncado/alterado (se puede fabricar con una copia) y un cifrado (si el PO tiene uno), y qué topes de entradas/tamaño se pueden aplicar con el **listado** de `lsar` antes de extraer.
2. **Dependencia:** tamaño de la imagen con **solo** `unar` (hoy sabemos +43 MB con las cuatro piezas), a decidir por el PO (CLAUDE.md §2).
3. **Medición en frío** (`DROP_CACHES=1`) y desde el disco de la biblioteca, no desde el disco del sistema.
4. **Comprobar la página de verdad** (`Image.load()` y tamaño/CRC contra el listado) y una muestra con `ComicInfo.xml`.
5. **Más muestras sólidas** de otro tamaño y, si se quiere, más paquetes como `m04` (la discrepancia de `bsdtar` está descrita, no explicada).

Esta ficha **no decide** la implementación ni autoriza renombrar, convertir, mover o adoptar ningún fichero de la biblioteca. Los 1234 `.cbr` siguen sin abrirse hoy; lo que cambiaría una implementación futura (portada y metadatos para esos ficheros) **no está medido** y depende de que cada fichero contenga imágenes legibles.

## 9. Actualización 2026-11-09 — #528: base trixie, `unar` 1.10.8 y flag de sólidos

> **No reescribe la medición de arriba.** Las tablas de §2–§7 se midieron con `unar`/`lsar` **1.10.1** de bookworm (`1.10.7+ds1+really1.10.1-2+b2`) sobre las 11 muestras del #308; siguen siendo la referencia histórica. Esta nota registra lo que cambia con la implementación de **#528 (opción 1 del PO)**.

| Dato | Antes (medición / bookworm) | Ahora (#528) |
|---|---|---|
| Imagen base | `python:3.11-slim-bookworm` | **`python:3.11-slim-trixie`** (builder y runtime), Python 3.11.18 |
| `unar`/`lsar` | 1.10.7+ds1+really**1.10.1**-2+b2 | **1.10.8+ds1-9** (`v1.10.8`; lo comprueba la CI dentro de la imagen) |
| GNUstep Base | 1.28.1+really1.28.0-5 | **1.31.1-3** (`libgnustep-base1.31`) |
| Listado | `lsar -j` | **`lsar -j -json-skip-solid-information`** |

**Por qué el flag.** En un RAR sólido, `lsar -j` repite en **cada** entrada el objeto interno del sólido (`XADSolidObject`, ≈29 KB). Con ~140 páginas el JSON supera `RAR_MAX_SALIDA_LISTADO` (4 MiB) y el lector devuelve `demasiado_grande`: el caso real de #528, con 216–246 páginas (≈12,9 MiB de salida). `-json-skip-solid-information` (`-jss`) omite ese objeto; el resto del contrato (índice, nombre, tamaño, CRC, cifrado, directorio) no cambia.

**Lo que NO se relaja.** Los topes de `utils/lector_rar.py` siguen igual: 1000 entradas, 500 MiB declarados, 4 MiB de salida de listado, 128 MiB de RSS, timeout y un solo lector. El flag no añade permisos ni rutas; solo reduce el JSON. La extracción por índice y la verificación por tamaño/CRC no dependen del flag.

**Compatibilidad con 1.10.1.** Si el binario no conoce el flag (bookworm), `listar` lo reintenta **una sola vez** sin él y sigue leyendo; en ese runtime el sólido grande vuelve a quedar limitado por el tope de 4 MiB (comportamiento anterior, no una regresión nueva). El soporte del flag se **decide una vez por proceso** (cacheado), el aviso `cover.lsar_sin_flag` sale una sola vez y sin rutas, y el reintento solo se dispara con la **firma exacta** del 1.10.1 («Unknown option -json-skip-solid-information»), no con cualquier mensaje que diga «unknown». Hay prueba con el `lsar` falso que imita ese mensaje y otra de que un error real no reintenta.

**Base mutable y cadena de suministro (#530 C6).** El `Dockerfile` usa el tag `python:3.11-slim-trixie` (mutable). Observado el 2026-11-09 en amd64: `python@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`; no se fija el digest, y la revisión periódica de ADR 0015 (cada actualización de base/paquete) sigue siendo la obligación. **arm64 no se ha verificado en esta historia**: la construcción y las pruebas de imagen son x86-64; la Pi queda **NOT RUN**.

**Herramientas y tamaño (#530 C2).** Trixie arrastra por `gnustep-base-runtime` y sus dependencias herramientas que el runtime no necesita: `dpkg-dev` (salvo `dpkg-architecture`), `gnutls-bin`, `make`, `patch`, `binutils`/`binutils-x86-64-linux-gnu`, `graphviz` y las utilidades de `perl`. Se borran sus ejecutables/scripts y se conservan las bibliotecas. **Dos excepciones obligatorias, medidas:** `dpkg-architecture` (GNUstep lo invoca en runtime para `DEB_HOST_MULTIARCH`; sin él `lsar`/`unar` abortan) y `perl-base` + `libdpkg-perl` + `perl-modules-5.40` (es un script Perl). Tamaño medido en local (x86-64): **722 MB** antes de C2 → **691,7 MiB** tras C2 → **687,8 MiB** con `.dockerignore`; la CI tiene un **presupuesto de 750 MiB** que falla por encima. Los fixtures, los hostiles y `lsar`/`unar` se verifican después de la limpieza en `scripts/comprobar_imagen_rar.py`.

**Contexto de build (#530 C1).** `.dockerignore` excluye `.git`, `.env`, `.env.*` (salvo `.env.example`), `.worktrees`, `.squad`, scratch, venv, `node_modules`, `__pycache__`, cachés (`pytest`/`ruff`/`mypy`) y artefactos. Con un `.env` centinela: **presente** en `/app` antes y **ausente** después. En local el contexto baja ≈4 MiB (2,8 MiB de `__pycache__` + cachés); en la CI, además, deja fuera `.git` (≈51 MB medidos en el checkout principal). La imagen no contiene `.env` ni cachés de pruebas.

**Cobertura.** Pruebas unitarias (`tests/test_lector_rar.py`, `tests/_rar_falso.py`): el flag queda fijado en `llamadas.log`; sólido sintético de **220** entradas con salida compacta con flag y >4 MiB sin flag; extracción con CRC; caché del soporte y aviso único; y el reintento único para el binario viejo, limitado a la firma exacta. Imagen y CI: el job `docker-build` comprueba `unar -v`/`lsar -v` = 1.10.8, que `lsar --help` incluye el flag, lo usa sobre el fixture sólido real, exige el presupuesto de tamaño y `scripts/comprobar_imagen_rar.py` valida GNUstep limpio, sin setuid nuevos, los fixtures/hostiles y la excepción de `dpkg-architecture`. El job de suite exige también 1.10.8 + flag en el runner (`scripts/ci_rar_real.py`), de modo que el fallback no pueda tapar un runner antiguo.

**NOT RUN / pendiente (no se toca la Pi).** Medir en la Pi el pico de memoria de la aplicación al interpretar una salida de listado grande con el flag (el tope de 4 MiB acota lo que se guarda y parsea, pero no hay medida en hardware real); extraer una portada de un RAR sólido real de ≥220 páginas (ese caso no está en `tests/fixtures/rar/`: la prueba de las 220 entradas es sintética); lectura en frío desde el USB de la biblioteca; **arm64** (la imagen y las pruebas se hicieron en x86-64). La limitación conocida de extraer un **RAR 5 sólido** sigue igual y es de `unar` 1.10.8 (ver `test_lector_rar_real.py::test_rar_real_un_rar5_solido_no_se_lee_limitacion_conocida_de_unar`); #528 solo arregla el **listado** del sólido, no la extracción de ese caso de RAR 5, y el issue sigue **abierto** hasta la medición real (C5).

