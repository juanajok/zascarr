# Evaluación del lector RAR/CBR en la Pi — 2.ª tanda (spike #308)

> **Estado: FICHA PARA REVISIÓN. No se ha implementado nada**, no se ha tocado la imagen de ZascArr ni ninguna biblioteca (las muestras eran copias con hash verificado; la biblioteca no se montó en ningún contenedor). Cierra los NOT RUN de `evaluacion-lector-rar-2026-10-23.md` (#315). Datos celda a celda: `evaluacion-lector-rar-tanda2-2026-10-23-datos.md`. Kit: `scripts/medicion/evaluacion_rar/` (#317, #319).

## 1. Veredicto en pocas líneas
- **`unar` leyó íntegra la página en las 35 muestras RAR evaluadas (34 distintas)** (RAR4, 6 RAR5 distintos, 4 sólidos hasta 215 MB): tamaño y **CRC32 del listado** coinciden y `Image.load()` decodifica (140 de 140 con `unar` y `unrar`). Pico de memoria **≤ 25,8 MiB**; primera página **≤ 0,09 s** en caliente y **≤ ~0,33 s en frío** (listar + primera, copias en el disco del sistema).
- **Con los daños ensayados, ninguna herramienta devolvió datos erróneos en silencio, ni se colgó, ni cayó, ni se pasó de memoria** (3 bases × 6–8 daños fabricados). Es un resultado favorable **para esos daños y esas muestras, no una validación completa de seguridad**. El daño en los datos de una página se detectó con código de salida ≠ 0.
- **Dos trampas que una integración debe cubrir:** `lsar` lista un fichero **truncado con código 0** y menos entradas; `unar` devuelve **0 sin escribir nada** si el índice pedido no existe. Hay que comprobar siempre existencia, tamaño y CRC contra el listado.
- **Coste de dependencia medido:** `unar` solo añade **+22,5 MiB (+4 %)** a la imagen y **12 paquetes** (incluido el runtime de GNUstep). La decisión de aceptarlo es del PO.
- **Lo que sigue sin medir:** una bomba de descompresión real y un RAR cifrado (no hay con qué crearlos; **la biblioteca no tiene ningún RAR cifrado**), y la lectura en frío desde el disco USB de la biblioteca.

## 2. Entorno (medido en la Pi, no en un PC)
Raspberry Pi 5 `aarch64` (Linux 6.18.50+rpt-rpi-2712), 4 GB, Docker 29.9.1. Mismo contenedor desechable que la 1.ª tanda (`--network none --read-only --memory=512m --memory-swap=512m --cpus=2`, `tmpfs` de 128 MiB, muestras `:ro`). Herramientas: `unar`/`lsar` 1.10.7+ds1+really1.10.1-2+b2, `unrar` 1:6.2.6-1+deb12u1 (comparación), `libarchive-tools` 3.6.2-1+deb12u5, `rarfile` 4.5. Paso 6: 2026-10-23 10:31 (carga 0,00, sin descargas); paso 7: 10:42.

## 3. Muestras y censo de cabeceras de la biblioteca
**Censo (solo lectura de 4 KiB por fichero; 1267 ficheros `.cbr`, `.rar` o sin extensión):**

| Formato | No sólidos | Sólidos |
|---|---|---|
| RAR4 o anterior | 964 | **86** |
| RAR5 | **156** | 2 |
| ZIP con extensión `.cbr` | 58 | — |
| 7z | 1 | — |

- **Los sólidos son ~7 %** (88 de 1208 RAR) y **RAR5 un 13 %** (158): ninguno es un caso marginal. **No hay ningún RAR cifrado** (0 de 1208).
- **58 `.cbr` son en realidad ZIP**: legibles con la biblioteca estándar, sin dependencias nuevas (#307).
- El intérprete de cabeceras es propio y sus pruebas usan cabeceras sintéticas; **se contrastó con la realidad**: marcó como sólida solo `m08` entre las 10 muestras RAR de la 1.ª tanda (el único sólido que se conocía), `unar` rotuló como «RAR 5» las marcadas RAR5, y la última página tarda segundos en los sólidos grandes.

**Unidades (para no mezclar recuentos):** hay **36 muestras RAR** (`m01`–`m10` y `s01`–`s26`; `m11` es el ZIP). De ellas, **35 «casos RAR»** tienen páginas evaluadas (`m04` es un paquete y solo se lista), y como `s14` y `s15` son el mismo fichero, son **34 archivos RAR distintos con páginas evaluadas** (35 archivos distintos en total contando `m04`). La comprobación de `ComicInfo.xml` se hizo sobre las 36 muestras RAR.

**Muestras:** las 11 de la 1.ª tanda (`m01`–`m11`) más 26 elegidas **por regla fija** (`s01`–`s26`: el sólido mayor ≤ 300 MB, uno mediano, y 24 `.cbr` típicos 1 de cada 30 en orden alfabético). 36 son RAR (`m04` es un paquete: solo se lista); `m11` es el ZIP. `s14` y `s15` son **el mismo fichero** (mismo hash). Sólidos: `m08` (57 MB), `s01` (215 MB), `s02` (48 MB), `s09`.

## 4. Resultados
### 4.1 Integridad de la página (tamaño + CRC32 + `Image.load()`)
**140 de 140 PASS** (35 muestras × `unar`/`unrar` × primera/última). El listado real de `lsar -j` trae `RARCRC32`, `XADFileSize`, `XADIndex` y `XADIsDirectory` (esquema constatado en la Pi). `m04` (paquete: 11 `.cbr` + carpeta) NOT RUN para páginas.

| Magnitud (`unar`) | Valor |
|---|---|
| Pico de memoria (sobre todas las operaciones) | **25,8 MiB** (el sólido de 215 MB; umbral 256) |
| Primera página, caliente | 0,03–0,09 s (≤ 0,09) |
| Última página, no sólido | ≤ 0,06 s |
| **Última página, sólido** | 0,13 s (`s09`), 0,93 s (48 MB), 1,06 s (57 MB), **3,97 s (215 MB)**; `unrar` algo menos (2,8 s en el de 215 MB) |

### 4.2 Lectura en frío (`drop_caches` antes de cada muestra; 37 muestras, disco del sistema)
- `lsar` (listar) pasa de ~0,04 s en caliente a **0,20–0,26 s**: es el coste de arrancar `unar` y el runtime de GNUstep desde disco la primera vez. La primera página siguiente cuesta **0,04–0,07 s**. Una lectura fría de portada es **≈ 0,25–0,33 s**.
- La última página de un sólido en frío es igual que en caliente (3,92 s en el de 215 MB): el coste es de descompresión, no de disco.
- **No medido:** desde el disco USB de la biblioteca (no se copiaron muestras a ese disco ni se montó en contenedores).

### 4.3 Ficheros dañados (copias en el tmpfs; originales intactos)
Bases: un RAR4 (35 MB), un RAR5 (67 MB) y un sólido (57 MB). Se **vuelve a listar** la copia dañada y se pide la página que diga el listado (como haría ZascArr), comparándola con la página original.

| Daño | `unar` | `unrar` |
|---|---|---|
| Datos de una página alterados (1 byte, o 4 KiB a cero), RAR4 y RAR5 | detecta la página mala (`Failed! (Wrong checksum)`, ≠ 0); entrega las otras **4 de 5** | detecta (`checksum error`, ≠ 0); entrega las otras 4 de 5 |
| Truncado al 50 % | las páginas que aún estaban enteras salen bien; la cortada falla (`Attempted to read more data than was available`) | falla con `Unexpected end of archive`, **incluso en una página íntegra** (más estricto) |
| Cabecera cortada a 64 bytes / un byte cambiado en cabecera | sin página que pedir, o tolerante (RAR5: lista 132 de 132 y las páginas salen bien por CRC) | `Corrupt header is found`… (RAR5), o sin página que pedir |
| Sólido, ceros a mitad | última página falla con error claro | igual |
| Un byte o 4 KiB a cero a mitad del fichero (lejos de las páginas pedidas) | las páginas pedidas salen bien | igual |
| Último byte del fichero (RAR4) | la última página falla (`Wrong checksum`) | igual (`checksum error`) |

**Ningún `SILENCIOSO`, `CRASH`, `TIMEOUT`, `OOM` ni `SIN_SALIDA_CON_RC_0` en 8 daños × 3 bases.** Con un caveat: el daño dentro de los datos de una página no se probó en el RAR sólido (no se puede localizar sin sacar los desplazamientos), solo «ceros a mitad».

**Hallazgos que obligan a verificar:**
1. **`lsar` lista un fichero truncado con código 0** y menos entradas (22 de 53, 66 de 132, 116 de 221): el código de salida no avisa.
2. **`unar` devuelve 0 sin escribir nada** si el índice pedido no existe (visto en la prueba corta, antes de volver a listar la copia).
3. `lsar -j` sobre una cabecera cortada a 64 bytes sale con código ≠ 0 y 0 entradas: controlado (las 3 «FAIL» del `resumen2.md` fueron un mensaje que el banco no capturaba; ver §7).

### 4.4 Topes
- **El listado da lo necesario para fijar topes antes de extraer:** nº de entradas y tamaño declarado por entrada. En 36 muestras: hasta **324 entradas**, **221 MiB** declarados en total, la mayor entrada **22 MiB** (en `m04`, un `.cbr` anidado; en los tebeos normales ≤ 6,5 MiB). (El tope de ZIP de ZascArr es 1000 entradas / 500 MiB.)
- **`lsar -j` en un RAR sólido es lento**: 2,5 s (57 MB), 4,7 s (215 MB), frente a 0,2 s en uno de 324 entradas no sólido. El listado sin `-j` (solo nombres) es casi instantáneo, pero sin tamaños ni CRC.
- **Topes desde fuera** (`unar` no tiene opciones): **tamaño máximo de fichero** (`RLIMIT_FSIZE`) funciona (SIGXFSZ tras escribir exactamente el tope); **tiempo** (matar el grupo de procesos) funciona y no deja huérfanos. **`RLIMIT_AS` no sirve: `unar` muere con SIGSEGV con 96 MiB de memoria virtual**; el tope de memoria debe ser el del contenedor/cgroup (los picos residentes de 25 MiB caben de sobra).
- **NOT RUN:** una bomba de descompresión real (no hay forma de crear un RAR así aquí).

### 4.5 Cifrado y ComicInfo
- **Cifrado: NOT RUN**, no por el banco sino porque el censo no encontró ningún RAR cifrado (0 de 1208): no hay nada que probar en esta biblioteca.
- **`ComicInfo.xml`: 0 de 36 muestras RAR lo traen.** Sobre las 24 tomadas por regla fija (1 de cada 30), la prevalencia queda **por debajo de ~12 %** (regla de tres); las otras 12 las elegí yo y no cuentan para esa cota. **Esto no demuestra que el resto de la biblioteca carezca de `ComicInfo.xml`.** Conclusión respaldada: *en las muestras examinadas no se acreditó ganancia de metadatos mediante `ComicInfo.xml`; sí se acreditó la extracción de páginas.*

### 4.6 Coste de dependencia
| Imagen | Tamaño (bytes) | Diferencia |
|---|---|---|
| ZascArr actual | 594 261 630 | — |
| + solo `unar` | 617 825 475 | **+23 563 845 (+22,5 MiB, +4 %)** |
| + `unar`, `libarchive-tools`, `unrar`, `rarfile` (imagen de evaluación) | 637 071 712 | +42,8 MB |

`unar` arrastra **12 paquetes, 18 499 KiB instalados**: `libgnustep-base1.28` (7077), `unar` (6118), `gnustep-base-runtime` (1842), `libavahi-common-data` (738), `gnustep-base-common` (695), `libgc1`, `libdbus-1-3` (516 cada uno), `libobjc4`, `gnustep-common`, `libwavpack1`, `libavahi-common3`, `libavahi-client3`. **No se ha revisado el historial de vulnerabilidades de `unar`/GNUstep.**

## 5. Criterios de §7 del protocolo (`unar`)
| Criterio | Resultado |
|---|---|
| Compatibilidad (RAR4, RAR5, sólido) | **PASS** — 35/35 por CRC; `m04` solo se lista |
| Memoria ≤ 256 MiB, sin muertes | **PASS** — 25,8 MiB; 0 OOM |
| Primera página ≤ 5 s | **PASS** — ≤ 0,09 s caliente, ≤ ~0,33 s frío (disco del sistema); USB **NOT RUN** |
| Seguridad | **PASS parcial** — para los daños ensayados, sin datos erróneos ni caídas (no es una validación completa); topes de tamaño de fichero y tiempo operativos; memoria virtual descartada como tope. **NOT RUN:** bomba real; cifrado (no hay muestras) |
| Licencia (Debian `main` o aceptación del PO) | **PASS** — `main`, LGPL-2.1+ |
| Dependencia | **medida, decisión del PO** — +22,5 MiB / 12 paquetes (GNUstep, avahi-client, dbus); historial de vulnerabilidades sin revisar |

## 6. Recomendación
La evidencia técnica pasa de «seguir investigando» a **«candidato a adopción condicionada»**: `unar` invocado directamente (sin `rarfile` ni `unrar`) cubre todo lo que la biblioteca tiene. Formalmente el protocolo conserva dos NOT RUN de seguridad (bomba real y cifrado) que no se pueden ejecutar aquí; se proponen cubrir con topes **antes** de extraer, no con una prueba.

**La decisión es del PO** y no se ha tomado: aceptar +22,5 MiB y 12 paquetes (con GNUstep) frente a la posibilidad de extraer páginas (portada) de ~1208 RAR; en las muestras examinadas no se acreditó ganancia de metadatos por `ComicInfo.xml`, además de decidir si los 58 ZIP con extensión `.cbr` (#307, sin dependencias) van antes.

### Condiciones de diseño que se deducen (no implementadas)
1. Decidir el lector por **firma**, no por extensión (58 ZIP `.cbr`, 12 ficheros sin extensión).
2. **Listar antes** (`lsar -j`); aplicar topes: nº de entradas, tamaño declarado total y por entrada; clasificar «paquete» si hay extensiones de contenedor.
3. Extraer **una sola página** a un directorio temporal acotado, con `RLIMIT_FSIZE`, tiempo máximo con **muerte del grupo de procesos** y el límite de memoria del contenedor.
4. Tras extraer, **verificar siempre**: que el fichero existe, su tamaño y su CRC32 contra el listado, y `Image.load()`. `rc 0` y un listado con menos entradas **no** son prueba de nada.
5. Leer los mensajes de `unar` de la **salida estándar** además de la de errores.
6. Los RAR sólidos cuestan segundos de listado (`lsar -j`): cachear el resultado y no repetirlo.
7. Sin renombrar, mover ni convertir ningún original.

## 7. Límites y trazabilidad
- **Defectos de medida corregidos durante la tanda** (el banco, no las herramientas): la 1.ª prueba corta pedía las páginas por el índice del original y ocultaba los mensajes (`-q`, `-inul`); se rehízo (#319). En la tanda completa quedaron tres defectos más, corregidos en #319 después de ejecutarla: el mensaje de `lsar -j` ante un fichero cortado no se capturaba (3 «FAIL» espurios de `lsar` sobre un fichero cortado a 64 bytes), las filas `primera` de los daños heredaban tiempo y detalle de `ultima`, y `RLIMIT_AS` figuraba como PASS. **La clasificación de resultados no cambia.** La tanda se ejecutó con el banco de `0525f30`.
- El daño dentro de los datos de una página **no se aplica al RAR sólido** (solo «ceros a mitad»).
- La lectura en frío es del **disco del sistema**; el USB de la biblioteca no se tocó.
- Los 36 RAR son de una colección concreta (scans en español, sobre todo): no se extrapola a otras.
- Sin RAR corruptos «de verdad» (los daños se fabricaron) y sin cifrados.

## 8. Qué NO se hace aquí
Implementar nada en ZascArr; añadir `unar` a la imagen; abrir, renombrar, mover, convertir o borrar originales; montar la biblioteca; ampliar a 7z, TAR o formatos sin extensión.
