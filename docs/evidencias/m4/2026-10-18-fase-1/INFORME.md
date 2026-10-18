# M4 — Fase 1: preparación de la VM, M4-01 y M4-02 (2026-10-18)

**Resultado de la fase: el candidato NO queda aceptado.** M4-01 = FAIL. M4-02 = resultados parciales (no PASS global). Ninguna tarjeta se cierra por esta fase.
Candidato: `0a591d6f91a6b54f8cecb1e675afc59dc0290873` (espejo Git local con `main` = candidato; no se usó el `main` actual). Plan: #226 (`f2c45c4b276c07dfea0a7c2baf96cc712f84fdcb`).
Datos: exclusivamente sintéticos (9 CBZ de 3 series). Evidencias numeradas 00–16 (esta carpeta). Este informe distingue **medido** de **no medido**.

## 1. Consumo y aislamiento

| Concepto | Autorizado | Usado |
|---|---|---|
| Tiempo | 90 min | ≈10 min (01:43:38 → 01:53 CEST) |
| Descarga | 3 GB | ≈0,9 GB (imagen Debian 349 MB + 533,6 MB recibidos por la VM) |
| Almacenamiento del ensayo en el anfitrión | 25 GB | 4,3 GB |
| Espacio libre mínimo del anfitrión | ≥10 GB | 434 GB (nunca por debajo) |
| VM | 2 vCPU / 4 GB / 20 GB + 2 GB sin usar | tal cual (ev. 09, 14) |

Aislamiento: sin carpetas compartidas, USB ni discos físicos; sin socket Docker del anfitrión; QEMU/KVM sin privilegios. En el anfitrión solo se abrió `127.0.0.1:2222` (SSH). Fase de ensayo con `restrict=on`: sin salida ni DNS (comprobado, ev. 09). No se tocó el Docker del anfitrión, ni grupos/permisos de `/dev/kvm`, ni paquetes del anfitrión. VM **apagada** al terminar (sin proceso qemu ni puerto abierto).

## 2. Manifiesto de artefactos (ev. 01, 03–09)

| Artefacto | Versión / identificador |
|---|---|
| Debian | `debian-12-genericcloud-amd64.qcow2`, build `20261015-2632` (12.15), SHA-512 `56c0bd55b6623f2739f377e983d2872e7b208d0cb9c3ba4e93d3f72929026da03637c598b3bd472b29998c31c8a4c17d8e6ae1c556852a8b83a66a09bf5c2b37` verificado contra `SHA512SUMS` de cloud.debian.org (la URL redirige a un espejo oficial; el contenido se validó por la suma) |
| Bundle del candidato | SHA-256 `10d107b11e5fe1a46bb5e2ba52df0afa2e88cf624da8c827e11c2c64af2f6642` |
| `bootstrap.sh` entregado | SHA-256 `e8860ff299a72821c3caca7b663f0e9cf98a0055508f54d138937214d8344fc4` (idéntico a `git show 0a591d6:bootstrap.sh`) |
| Docker (APT oficial, huella `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`) | docker-ce y docker-ce-cli `5:29.8.2-1~debian.12~bookworm`; containerd.io `2.4.2-2`; buildx `0.38.0-1`; compose `5.6.0-1` (seleccionadas y registradas antes de instalar) |
| Imágenes base | `postgres:15-alpine` `sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81`; `python:3.11-slim-bookworm` `sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89` |
| Dependencias Python resueltas | ev. 07 (p. ej. fastapi 0.143.3, SQLAlchemy 2.1.5, alembic 1.20.0, uvicorn 0.54.0, asyncpg 0.32.0) |
| Git / Python en la VM | git 2.39.5-0+deb12u3, python3 3.11.2 |

## 3. Adaptaciones del arnés (no son resultados del producto)

1. **Espejo Git local**: `url./srv/espejo/zascarr.git.insteadOf https://github.com/juanajok/zascarr.git` en el git del sistema. Los scripts resuelven contra el espejo (`main` = candidato). **No acredita conectividad con GitHub.**
2. **Imagen construida desde caché**: sin red no se puede ejecutar `apt`/`pip` del `Dockerfile`. En la fase con red se construyó una vez el mismo `Dockerfile` desde el espejo (etiqueta `zascarr-prebuild:cache`). `bootstrap.sh` construyó después `zascarr-zascarr:latest` con las capas de `apt`/`pip` en `CACHED` (ev. 13). **M4-01 no ejercita la descarga de dependencias ni una construcción en frío.**
3. Docker instalado **antes** por APT: la rama de `bootstrap.sh` que instala Docker con `get.docker.com` es **NOT RUN**.
4. Acceso por SSH desde el anfitrión por el puerto local; biblioteca sintética creada en la VM antes del ensayo.

## 4. M4-01 — instalación limpia: **FAIL**

Los intentos se registran por separado:

| Ejecución | Entrada | Resultado |
|---|---|---|
| **Intento 1 — instalación limpia** (ev. 10–12) | VM limpia (sin `/opt/zascarr`, sin `.env`, sin usuario `media`, sin contenedores), `sudo bash bootstrap.sh < /dev/null`, sin terminal, valores por defecto, rutas `/media/library` y `/media/data` sintéticas | **FAIL: RC=1** en ≈1 s tras crear lo previo. Copia `.env.example` a `/opt/zascarr/.env` y se detiene en «Validando .env»: *«DB_PASSWORD tiene el valor por defecto. Edita /opt/zascarr/.env y pon una contraseña segura.»* |
| Intento 2 — **tras intervención manual** (ev. 13) | Misma VM; yo sustituí `DB_PASSWORD` por una contraseña sintética generada en la VM y relancé `sudo bash /opt/zascarr/zascarr/bootstrap.sh < /dev/null` | RC=0 bajo **condiciones modificadas**. **No convierte el intento 1 en PASS.** |

Clasificación: **comportamiento del candidato, no del arnés** (no faltaba ningún recurso; no depende del espejo ni de la red). El aborto es seguro frente a arrancar con una contraseña de ejemplo, pero **incumple la instalación limpia sin intervención manual**: el README promete «pegar una línea» y tres preguntas, y el paso manual forma parte del defecto. El mensaje es claro y en español; eso no cambia el veredicto.
Salvedad de alcance: esta prueba es **sin terminal**; no demuestra que falle todo camino interactivo. El control de contraseña que lee el código (`bootstrap.sh`, «Validando .env») es incondicional: no hay camino en el flujo ensayado que la genere.

Efectos colaterales del intento 1 (registrados): usuario/grupo `media`, clon en `/opt/zascarr/zascarr` (commit `0a591d6`, comprobado), `.env`, y carpetas **vacías** `Comics`, `Comics/_Specials`, `Comics/_Omnibus`, `Manga`, `BD`, `Tebeos`, `Fumetti`, `Manhwa`, `Graphic Novels`, `_Unsorted` dentro de la biblioteca. Los ficheros de la biblioteca **no cambiaron** (huella de ficheros idéntica antes/después: `9e2490a9…be2d`, 9 ficheros; ev. 08 y 14).

### Intervenciones registradas
- Una: edición de `DB_PASSWORD` en `.env` (sintética, 24 caracteres, no se reproduce aquí) entre los intentos 1 y 2.
- Ninguna otra intervención en el instalador; ningún código de producto modificado.

## 5. M4-02 — salud y esquema: resultados parciales (no PASS global)

Medidos sobre la instalación del intento 2 (condiciones modificadas por la intervención de §4):

| Comprobación | Resultado | Evidencia |
|---|---|---|
| Aplicación accesible | PASS: `/estado` 200, `/api/health` 200, `/` 307 | 15 |
| CSS del candidato servido | PASS: `/static/web.css` 200, 55.828 B, SHA-256 `ce87a9e2…daca0f` = el de `git show 0a591d6:src/zascarr/static/web.css` | 15 |
| Salud de base de datos | PASS: `database: ok`, contenedor `healthy` | 14–16 |
| Esquema Alembic | PASS: `alembic_version=0019`, cabeza del código `0019 (head)` | 14–16 |
| Límite de memoria **efectivo** | PASS: 536.870.912 B (512 M) en app y BD, en `docker inspect` **y** en el `memory.max` del cgroup v2 | 14, 16 |
| Reinicios / OOM | PASS en lo observado: reinicios 0, `oom_kill` 0, `dmesg` sin OOM (muestra de ≈2 min; no se provocó OOM) | 14, 16 |
| Accesos no previstos (puertos) | PASS: `8000` y `5432` solo en `127.0.0.1`; resto: SSH y DNS local de systemd. En el anfitrión solo `127.0.0.1:2222` | 14 |
| Estado global | `degraded` por Transmission/aMule/VPN ausentes en la VM: **no es por sí solo un fallo del candidato en este entorno** | 14 |
| **Fuentes externas desactivadas** | **FAIL de la condición** (ver §6) | 14, 15 |

Memoria en reposo (informativa, sin umbral): app 98 MiB, BD 72 MiB, CPU ≈0,4 % / 0,06 %.
Recuentos tras el arranque: 0 series, 0 archivos (la auditoría de biblioteca escaneó y calculó hash de 9 ficheros, sin importar).

## 6. Fuentes externas: **FAIL de la condición operativa**

- `config.py` del candidato: `comicvine_enabled`, `anilist_enabled`, `tebeosfera_enabled` y `gcd_enabled` tienen `default=True`; `/api/health` los muestra como `enabled`. La instalación limpia **no** los deja apagados.
- Las integraciones de descarga/foro (Prowlarr, Transmission, aMule, foro) siguen otra política: `FORUM_ENABLED=false` (comprobado en el contenedor). No se mezclan las dos categorías.
- Para este ensayo se exigió que estuvieran desactivadas → **FAIL de esa condición de configuración**.
- Lo siguiente **no equivale a apagarlas**: red cerrada (conservada), **0** intentos de salida/DNS en los logs de la aplicación, y los ciclos del orquestador omitidos por falta de aceptación legal (`orchestrator.*_skipped_no_legal_acknowledgment`). **Activación accidental efectiva de consultas externas: no acreditada**. Tráfico externo: no observado *con la red cerrada*.
- Para un ensayo posterior podrán fijarse los cuatro flags a `false` por configuración soportada; sería una **adaptación documentada del ensayo**, no una corrección de los defaults ni prueba de que una instalación limpia los deja apagados. No se ha cambiado ningún default.

## 7. Hallazgo de seguridad separado: `.env` con permisos 0644 — alcance medido (ev. 17–18)

Inspección autorizada (30 min; misma VM y red cerrada; superposición temporal sobre `m4-01`, que quedó intacta: hash idéntico antes/después y marcada de solo lectura; VM apagada, sin QEMU ni puerto 2222; la superposición temporal se eliminó). No se leyó ni imprimió el contenido, no se ejecutó `bootstrap.sh`, no se cambió ningún permiso ni secreto y no se tocaron las fuentes. El arranque escribió en la superposición temporal, como estaba previsto.

**Medido**

| Elemento | Resultado |
|---|---|
| `/opt/zascarr/.env` | modo `644`, dueño `root:root`, 4.104 B, sin ACL (sin indicador `+`; `getfacl` no está instalado y no se instaló) |
| Ruta de acceso | `/` 755 root · `/opt` 755 root · `/opt/zascarr` 755 `media:media` · `/opt/zascarr/zascarr` 755 `media:media`: **todo atravesable por cualquiera** |
| Enlace en el repo | `/opt/zascarr/zascarr/.env` → `/opt/zascarr/.env` (`readlink -f` coincide: es el mismo fichero) |
| Apertura sin leer (éxito/denegación) | `ensayo` (sesión sin sudo, sin grupos adicionales): **ABRE** · `nobody`: **ABRE** · `media` (usuario de servicio): **ABRE** |
| Dentro de la imagen | `/app/.env` es un enlace a `/opt/zascarr/.env` que **no se resuelve** en el contenedor: **el secreto no está incorporado a la imagen** (no existe `.dockerignore`, pero el `COPY` conservó el enlace, no el fichero). Los contenedores no montan el `.env` (0 montajes) |
| Otras superficies | `/var/lib/zascarr/postgres` 700 (bien); `/var/lib/zascarr` y `/var/backups` 755 root. No existen copias aún: el modo de los volcados queda por medir en los casos de backup |

**Conclusión (medida, no inferida): exposición efectiva a cualquier identidad local sin privilegios**, no solo un modo permisivo. Qué cubre y qué no: la VM no tiene más cuentas ni servicios locales; el riesgo real depende de qué otras cuentas y servicios tenga la máquina (en la Pi compartida: Transmission, aMule, Prowlarr, Kavita u otros usuarios). No se probó si algún contenedor o servicio concreto puede abrirlo.

**Origen (por lectura del código):** `bootstrap.sh` lo crea con `cp .env.example .env` y nunca ajusta el modo; el usuario de servicio no es el dueño.

**Quién necesita leerlo (por lectura del código; no probado con cambios):** `bootstrap.sh` exige `EUID=0`; los demás scripts (`update.sh`, `backup.sh`, `rollback.sh`, `_exposicion.sh`, `diagnostico-red.sh`) lo pasan con `--env-file` a `docker compose`, que lo lee **el proceso del que invoca** (en la práctica root con `sudo`; los scripts documentan `sudo`). La excepción a validar es `etiquetar.sh`, que solo comprueba su existencia, y cualquier uso de `docker compose` manual desde el repo mediante el enlace. El demonio de Docker y los contenedores no lo leen. **Este reparto es una hipótesis de lectura**: la decisión de propietario/modo debe probarse con instalación, actualización, backup y rollback en un ensayo posterior; no se ha aplicado `chmod`.

## 8. Límites de esta fase

Una sola instalación, un ensayo de ≈2 min de ejecución estable, tráfico nulo, biblioteca de 9 ficheros. Inspección del `.env` (§7): una sola máquina sin otras cuentas. No se ejercitó: construcción en frío, rama `get.docker.com`, instalación con `.env` preparado por el usuario (flujo interactivo), reinicio, actualización, restauración, presión de disco, #143. **No hay aceptación del candidato** y no se cierra ninguna tarjeta. M4-03…M4-20 siguen sin autorización; tampoco hay correcciones de producto ni más descargas.

## 9. Resumen de resultados

| Caso | Resultado |
|---|---|
| M4-01 instalación limpia | **FAIL** (intento 1); intento 2 completa solo tras intervención manual |
| M4-02 salud y esquema | **Parcial**: PASS en app, CSS, BD, 0019, memoria efectiva, sin OOM/reinicios, puertos; **FAIL** «fuentes externas desactivadas» |
| Hallazgo `.env` 0644 | **Abierto**; alcance medido: **exposición efectiva a identidades locales sin privilegios** (§7) |
| M4-03…M4-20 | **NOT RUN** (no autorizado) |
