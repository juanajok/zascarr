# ADR 0015: Lector de RAR con `unar` — riesgo aceptado y mitigaciones (#418)

- Estado: **Aceptado** · 2026-11-07 (decisión del PO sobre la PR #455, tras el dictamen de SecOps A-1 y el informe de QA).
- Relacionado: ADR 0011 (sin Redis), ADR 0012 (credenciales del `.env`), `docs/design/especificacion-BL-PORT3.md`,
  `docs/design/evaluacion-lector-rar-tanda2-2026-10-23.md`, `SECURITY.md`.

## Contexto

La portada de una serie sale del primer archivo utilizable. El 87 % de los `.cbr` de una biblioteca real son RAR (4 o
anterior) y no había forma de leerlos sin un programa externo. El PO eligió `unar` (con `lsar`), por subproceso, y descartó
las bibliotecas RAR embebidas y `unrar`.

Hechos (dictamen de SecOps sobre #455, `0fab248`):

| Hecho | Detalle |
|---|---|
| Superficie nueva | `unar`/GNUstep es un analizador de ficheros de terceros en C/Objective-C. Abre archivos de la biblioteca, que **llegan por P2P** (aMule y Transmission la alimentan) |
| Sin aislamiento respecto de la aplicación | corre como el **mismo usuario y en el mismo contenedor**: ve `DATABASE_URL` en el entorno del padre y la biblioteca montada en lectura y escritura |
| Versión | Debian bookworm empaquetaba `unar`/`lsar` `1.10.7+ds1+really1.10.1-2+b2`: **código de la v1.10.1**, anterior a la 1.10.8; con `gnustep-base-runtime`/`libgnustep-base1.28` `1.28.1+really1.28.0-5` (medido en la imagen el 2026-11-07). **Desde #528 (2026-11-09) la imagen es trixie y lleva `unar`/`lsar` `1.10.8+ds1-9` con `gnustep-base` `1.31.1-3`** |
| Vulnerabilidades conocidas | en tres búsquedas SecOps no halló CVE aplicable a Linux (la de XADMaster, CVE-2024-22405, es de macOS; las de GNUstep son de `gdomap`, antiguas). **Ausencia de resultados no es ausencia de fallos**: no hay análisis del código ni *fuzzing* |
| Limitación funcional | `unar` no extrae un RAR 5 **sólido** (v1.10.1 y 1.10.8): da `ilegible` → marca → cascada de portada, sin error 500 (AC-07 aceptado) |

## Decisión

**Se acepta el riesgo de ejecutar `unar` dentro del contenedor de la aplicación**, con este alcance y estas mitigaciones, en
la misma PR que introduce el lector:

1. **El subproceso** (`utils/lector_rar.py`): sin shell, ruta absoluta, entorno mínimo (`PATH`, `HOME` temporal, `LANG`,
   `TMPDIR`), grupo de procesos propio muerto al vencer; **tiempo**, **memoria residente** (128 MiB, vigilada cada 20 ms: no se
   usa `RLIMIT_AS`, que rompe `unar`), **salida** y **bytes escritos** acotados; **un solo lector** a la vez con espera acotada
   (2,5 s); extracción **por índice** a un temporal propio, verificada por tamaño y CRC32 y decodificada con tope de píxeles.
   Sin red y sin escribir junto al original.
2. **El contenedor** (`docker-compose.yml`): `security_opt: [no-new-privileges:true]` y un tope de 256 procesos (`deploy.resources.limits.pids`; `pids_limit` no puede convivir con `deploy.resources.limits` en este Compose) para la aplicación.
3. **La imagen** (`Dockerfile`): `unar` solo en la etapa `runtime`. `gnustep-base-runtime` es dependencia **dura** de `unar`
   (`--no-install-recommends` no evita sus ejecutables), así que se **borran todos los ficheros ejecutables y de servicio del paquete**
   (`/usr/bin`, `/usr/sbin`, `/etc/init.d`, `/etc/default`: `gdomap`, `gdnc`, `defaults`, `pl*`, `xmlparse`, `sfparse`, `cvtenc`…;
   `gpbs` no existe en bookworm) por su lista de `dpkg -L`; `lsar`/`unar` solo necesitan las bibliotecas. La CI comprueba **dentro de la
   imagen de producción** (`scripts/comprobar_imagen_rar.py`, como `zascarr`): que no quedan, que no hay `setuid`/`setgid` fuera de la base
   de Debian, y que se leen los fixtures RAR con el `unar` v1.10.8 de la imagen (la suite usa el 1.10.8 del ejecutor).
4. **Pruebas**: `lsar`/`unar` falsos para la lógica, RAR reales mínimos (RAR 4, RAR 5, RAR 4 sólido) y los seis RAR 4 hostiles
   del generador de SecOps (traversal, ruta absoluta, enlace simbólico, comodines, salto de línea, tamaño falso) con `unar` real
   en la CI, con una puerta que falla si alguna se salta.

## Qué NO cubre (riesgo residual aceptado)

- Un fallo de ejecución de código en `unar` equivaldría a comprometer la aplicación (leer `/proc/<ppid>/environ`, tocar los
  tebeos): el entorno mínimo protege lo que se hereda, no lo que el proceso puede leer. `no-new-privileges` y `pids_limit` lo
  acotan, no lo evitan.
- No se ha hecho análisis del código de `unar` ni *fuzzing*; las pruebas con RAR hostil son siete sondas, no una auditoría.
- Bomba de descompresión real, RAR cifrado y multivolumen reales, y lectura en frío desde el USB: sin probar (NOT RUN).
- El hash del paquete `rar` 6.24 de RARLAB con el que se crearon los RAR 4 de prueba no es verificable contra un valor publicado.

## Consecuencias

- Un mantenedor que quiera endurecer más tiene tres palancas pendientes: ejecutar `unar` con otro usuario o contenedor,
  `PR_SET_DUMPABLE=0` en la aplicación y un perfil seccomp. Ninguna se hace aquí.
- Si aparece una CVE de `unar`/XADMaster/GNUstep aplicable a Linux, **se retira el lector** (la portada vuelve a la cascada
  sin RAR) hasta actualizar; basta con quitar `unar` de la imagen: el aviso de `/api/health` ya contempla su ausencia.
- Antes de desplegar siguen abiertas las puertas P-1..P-6 de la spec (imagen ARM, medición en la Pi, etc.).
- **Cómo apagarlo sin reconstruir la imagen:** `LECTOR_RAR_ENABLED=false` en el `.env` (declarada solo en `config.py`; por defecto `true`;
  el compose la pasa al contenedor). Apagado, ningún RAR se envía a `unar`/`lsar`: el recorrido de portada lo trata como no candidato
  **sin gastar intento ni dejar marca**, la cascada sigue (antigua → externa → 404, sin 500) y `/api/health` no avisa de que falta la
  herramienta. Los `.cbr` que son ZIP y los CBZ no cambian. **Apagarlo conserva lo ya generado (H-3, aceptado por el PO el 2026-11-08):** las portadas
  de RAR ya guardadas en `covers/v3` se siguen sirviendo y las marcas de fallo existentes no se tocan ni se borran; apagarlo solo impide
  leer RAR nuevos. Quien quiera retirar también lo ya generado debe borrar a mano esos ficheros de `covers/v3` (nada los borra solo).
  Al volver a encenderlo, un archivo con marca vigente no se reabre y uno sin marca se vuelve a intentar.
- **Comportamiento conocido (G-2, aceptado por el PO el 2026-11-07):** si el turno del lector (2,5 s) vence porque otra portada lo tiene,
  la petición da 404 `no-store` y el `<img>` cae al marcador hasta recargar. En una rejilla fría de 12 series RAR, QA midió 11 de 12
  con portada con ≈ 0,3 s/serie y 3 de 12 con ≈ 2 s/serie (no medido en la Pi). Se mide en la Pi y, si sale mal, se sube el turno o se
  precalienta la caché: historia aparte.
- **H-1 (decisión del PO, 2026-11-07):** si en el recorrido se saltó un RAR candidato **por falta de turno** y aun así sale la portada de
  un archivo posterior, esa portada se sirve **sin escribir `covers/v3` y con `Cache-Control: no-store`**: la siguiente petición, con el lector
  libre, prueba el RAR y guarda la correcta. Así un RAR legible no pierde para siempre su portada frente a un CBZ posterior por una carga
  pasajera. Un RAR saltado por tener marca vigente no cuenta como ocupado; una serie solo de CBZ se cachea como antes.
- **En cada actualización de la imagen base** (`python:3.11-slim-trixie` desde #528) o del paquete `unar` hay que repasar el *tracker* de
  `unar`/XADMaster y de GNUstep y volver a correr
  `scripts/comprobar_imagen_rar.py`. El PO descartó el 2026-11-07 cambiar de base en la PR de #455 ("historia aparte"); esa
  historia es la **#528 (2026-11-09)**, que pasa a `trixie` (`unar`/`lsar` 1.10.8, GNUstep Base 1.31.1) y usa
  `lsar -j -json-skip-solid-information` para que el listado de un sólido grande no reviente el tope de 4 MiB. Los topes de
  entradas/bytes/salida siguen igual; `listar` reintenta una vez sin el flag si el binario es antiguo (1.10.1). La medición en
  la Pi del pico de memoria con una salida grande queda **NOT RUN** (no se toca la Pi en #528). El interruptor
  (`LECTOR_RAR_ENABLED`) sigue siendo la palanca para apagarlo sin reconstruir.
