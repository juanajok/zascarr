# ADR 0012: Credenciales del `.env` — inicialización, conservación y protección

- Estado: **Propuesto** · 2026-10-18. Nace del veredicto «DEVUELTO» de la revisión del informe M4 fase 1 (candidato
  `0a591d6f91a6b54f8cecb1e675afc59dc0290873`): contraseña de base de datos por defecto, `.env` con permisos abiertos y
  fuentes mostradas como activadas. **Esta decisión cubre solo los dos primeros**; el tercero es un hallazgo aparte.
- Relacionado: [ADR 0004](0004-exposicion-de-red.md) (el instalador fija la contraseña de acceso antes de publicar el
  puerto: mismo principio, otra credencial), CLAUDE.md §3.2 y §5, `SECURITY.md`.

## Contexto — causa y rutas afectadas

Cuatro defectos que se refuerzan entre sí. Cada uno está reproducido por una prueba que **falla sobre `main`** (ver
«Pruebas»):

| # | Defecto | Dónde |
|---|---|---|
| 1 | **Una instalación nueva no termina.** `bootstrap.sh` copia `.env.example` (con `DB_PASSWORD=cambia_esto_ahora`) y, más abajo, **aborta** porque la contraseña es la de ejemplo. El coleccionista —que no abre un editor de texto— se queda sin instalar. La barrera era correcta; faltaba lo que la hiciera innecesaria: inicializar bien. | `bootstrap.sh` (validación) |
| 2 | **Compose pone en servicio una base con una contraseña publicada en el repositorio.** `${DB_PASSWORD:-SuperSecretPassword123}`: sin `.env` visible (un `docker compose up` a secas, un `.env` que falta, el arnés de validación de la Pi con el valor de ejemplo) arrancaba igual, en silencio. | `docker-compose.yml` (PostgreSQL y aplicación) |
| 3 | **El `.env` lo lee cualquiera y lo cambia el usuario de servicio.** Ningún `chmod` en todo el instalador: queda con el `umask` (644). Peor: `chown -R <usuario de servicio> <ZASCARR_ROOT>` dejaba la carpeta que contiene el `.env`, el repo y el enlace `.env` del repo **a nombre del usuario de servicio** (`media`, el mismo de Sonarr, Prowlarr, Transmission…). Proteger solo el contenido del fichero no habría bastado: **borrar o renombrar una entrada depende del permiso sobre la carpeta**, no sobre el fichero. | `bootstrap.sh` (camino en frío), README |
| 4 | **El mismo usuario puede cambiar lo que root ejecuta**: `docker-compose.yml`, `Dockerfile`, `scripts/*.sh` y el enlace `.env` que Compose sigue por defecto estaban en una carpeta suya. | ídem |

Rutas de arranque revisadas: `bootstrap.sh` · `docker compose up` a mano (README, «instalación manual») ·
`docker compose run --rm zascarr alembic …` · `scripts/update.sh` · `scripts/rollback.sh` · la aplicación lanzada fuera
de Compose · el arnés de validación de la Pi (`docs/design/guion-validacion-pi-mvp.md`) y los de ensayo.

## Decisión

### 1. Contrato

> **Ninguna ruta de arranque soportada pone en servicio el sistema con una credencial obligatoria ausente, vacía o
> conocida por defecto.**

| Pieza | Qué hace | Dónde |
|---|---|---|
| Inicialización | `DB_PASSWORD` ausente, vacía o de ejemplo ⇒ se **genera** una propia (192 bits, hexadecimal, del sistema operativo) y se guarda en el `.env` **antes** de crear PostgreSQL. No se muestra nunca. | `scripts/_credenciales.sh`, `bootstrap.sh` |
| Conservación | Una credencial válida **no se toca, no se regenera y no se imprime**. La clave que firma la cookie de sesión **no está en el `.env`**: la app la genera una vez y la guarda en la base de datos (`ensure_secret_key`), así que no hay nada que inicializar ni conservar en el `.env` para ella. | ídem · `services/runtime_settings.py` |
| Base ya creada | Si falta la credencial **y ya existe una base de datos** (`<datos>/postgres/PG_VERSION`), el instalador **se detiene sin cambiar nada** y explica cómo recuperarse. Inventar otra contraseña dejaría la base inaccesible. | ídem |
| Compose | Servicio de un solo uso `credenciales` (imagen de PostgreSQL, sin red, sin escribir, 16 MB, termina enseguida): PostgreSQL y la aplicación esperan a que acabe bien. Rechaza ausente, vacía, solo espacios, comillas y las **conocidas** (sin distinguir mayúsculas). | `docker-compose.yml` |
| Aplicación | Si le llega un `DATABASE_URL` con una contraseña conocida, **no abre ninguna conexión** y arranca en modo solo diagnóstico (el mismo camino de fallo cerrado que «base de datos no disponible»), con el motivo en el log y sin el valor. | `utils/credenciales.py`, `main.py` |
| `update.sh` | Comprueba la contraseña **antes** del backup y de traer código: «NO se ha actualizado nada». Avisa —sin fallar— si el `.env` sigue legible por otros. | `scripts/update.sh` |
| Instalación manual | Inicialización explícita documentada: `sudo bash scripts/credenciales.sh` (crea el `.env`, genera, protege, idempotente). Sin ella, Compose se niega a arrancar con un mensaje en español. | `scripts/credenciales.sh`, README |

**Por qué un servicio y no `${DB_PASSWORD:?}`:** `:?` exige presente y no vacía, pero **no rechaza un valor de ejemplo**, y
además hace fallar `docker compose down/logs/ps` en cuanto falta el `.env` — justo cuando se quiere parar o desinstalar
(`uninstall.sh` está pensado para tolerar un `.env` ausente). El rechazo ocurre al **arrancar**, no al leer el fichero.

**Lista de valores conocidos** (la misma en tres sitios; `tests/test_credenciales_lista.py` comprueba que coinciden):
`cambia_esto_ahora` (la plantilla), `SuperSecretPassword123` (el antiguo valor por defecto de Compose, publicado en el
repo), `changeme`. `.env.example` conserva el placeholder: es la barrera lo que lo hace inofensivo.

### 2. Escribir el `.env`: atómico y sin copias

`env_escribir` compone un temporal `0600` en la **misma carpeta**, le da el propietario y modo del original, hace `sync` y
lo **renombra encima** (atómico en el mismo sistema de ficheros). Un fallo en cualquier paso borra el temporal y deja el
original intacto: ni fichero a medias ni pérdida de la configuración anterior válida. El valor viaja por el entorno de
`awk`, no por argumentos (no sale en `ps`) y se escribe literal (`\`, `&`, `#`, `$`). **No se hacen copias de seguridad
del `.env`**: serían más copias de un secreto. Cada escritura es atómica; no hay transacción entre variables distintas, pero
el orden garantiza lo que importa: la contraseña queda guardada **antes** de crear la base y de preguntar nada. Un
temporal que dejara una muerte súbita (`SIGKILL`, corte de luz) se limpia en la siguiente ejecución.

### 3. Matriz de identidades

El **`.env` administrativo** (de root) no es lo mismo que **los secretos que el proceso necesita**: el contenedor **no
monta el `.env`**; solo recibe las variables que `docker-compose.yml` declara en `environment` (la contraseña de la base
dentro de `DATABASE_URL`, y las claves opcionales que el coleccionista haya puesto). Ni PostgreSQL ni la app pueden leer ni
reescribir el fichero.

| Identidad | `.env` | Carpeta del `.env` (`ZASCARR_ROOT`) | Repo (compose, Dockerfile, scripts, enlace `.env`) | Justificación |
|---|---|---|---|---|
| **root** (instalador y administrador, siempre con `sudo`) | lee y actualiza (`root:root 600`) | `root:root 755` | `root:root`, sin escritura para otros | Quien instala y opera. `update.sh`, `rollback.sh`, `backup.sh` y `uninstall.sh` ya exigen o suponen root: no cambian. |
| **Consumidores de administración** (`update.sh`, `rollback.sh`, `backup.sh`, `bootstrap.sh`, `credenciales.sh`) | los ejecuta root; leen vía `--env-file` | — | los ejecuta root | Acceso mínimo para actualizar, restaurar y operar. Un `docker compose` **sin `sudo`** deja de ver el `.env` (ahora es 600): se usa `sudo docker compose …` (README actualizado). |
| **Usuario de servicio** (`media`, compartido con la suite *arr) | **sin lectura, sin escritura** | **sin** crear, borrar ni renombrar entradas | **sin** escritura | No puede editar, truncar, eliminar, mover ni reemplazar el `.env`, ni redirigir el enlace efectivo, ni cambiar lo que root ejecuta. Conserva lo suyo: `covers/` y `vpn-state/` en `ZASCARR_DATA_DIR` (no se tocan aquí). |
| **Otros usuarios locales** | sin lectura | atraviesan (755) | leen el código (público) | Sin acceso a secretos. |
| **Aplicación y PostgreSQL (contenedores)** | no lo montan | — | — | Solo las variables de `environment`. |

Consecuencias de implementación (todas en `proteger_configuracion`, idempotente):

- `.env`: `root:root 600`. `ZASCARR_ROOT`: `root:root 755`. Repo: `chown -hR root:root` + `chmod -R go-w` (**`-h`**: un enlace
  dentro del repo no puede hacer que se reclame un fichero ajeno).
- **Solo si `ZASCARR_ROOT` es una carpeta dedicada** (`raiz_dedicada`: `<raíz>/zascarr`, que no es el home de nadie y solo
  contiene entradas de ZascArr). Si es compartida —un home, `/opt`…— **no se reclama ni ella ni el repo** (podrían ser de
  otra persona), el `.env` queda igualmente `root 600` y se **avisa** de que quien pueda escribir en esa carpeta podría
  reemplazarlo. Reclamar por error la carpeta personal de alguien es peor que el defecto que se corrige.
- El camino en frío del instalador ya no hace `chown -R <servicio> <ZASCARR_ROOT>` (que además recorría carpetas ajenas).
- La biblioteca y las descargas **no se tocan** (A3).

### 4. Qué no se hace

- **No** se migra a Docker Secrets: el contrato se cumple sin separar secretos. Si algún día hiciera falta (p. ej. para
  ocultar la contraseña de `docker inspect`), se justificará aparte.
- **No** se cambia automáticamente la contraseña de una base ya inicializada.
- **No** hay rotación de contraseña asistida (ver el procedimiento manual abajo).

## Si se pierde la contraseña de una base que ya existe

El instalador se detiene (`No he cambiado ninguna contraseña`). Opciones, de menos a más drástica:

1. **Restaurar una copia del `.env`** en `ZASCARR_ROOT` y volver a ejecutar el instalador. Es lo normal.
2. **Con la base en marcha y sin copia** (operador, en `bash`; la contraseña nueva no se muestra ni va en argumentos):
   ```bash
   NUEVA="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
   printf "ALTER USER comics_admin WITH PASSWORD '%s';\n" "$NUEVA" | sudo docker exec -i zascarr-db psql -U comics_admin -d zascarr
   export NUEVA
   sudo --preserve-env=NUEVA bash -c 'source /opt/zascarr/zascarr/scripts/_credenciales.sh; env_escribir /opt/zascarr/.env DB_PASSWORD "$NUEVA"'
   unset NUEVA
   sudo bash /opt/zascarr/zascarr/bootstrap.sh
   ```
   El socket local del contenedor de PostgreSQL no pide contraseña, por eso funciona aunque no se conozca la antigua.
   (Mecanismo comprobado con la misma imagen en una instancia desechable: la contraseña antigua deja de valer y la nueva
   entra por red.)
3. **Si no hay nada que conservar:** apartar —no borrar— `<datos>/postgres` y volver a ejecutar el instalador: se crea una
   base nueva con contraseña nueva.

## Compatibilidad y migración

- **Instalaciones existentes** (válidas, con la contraseña ya cambiada): no cambia nada de lo que ven. Para endurecer el
  `.env` y el repo basta `sudo bash scripts/credenciales.sh` o volver a ejecutar `bootstrap.sh`; **no cambia la
  contraseña**. `update.sh` no migra permisos: avisa.
- **Instalaciones con el `.env` aún con el valor de ejemplo:** no pueden existir por `bootstrap.sh`; si las hay por haber
  arrancado Compose a mano, la base se creó con la contraseña antigua de Compose: `update.sh` se detiene antes de tocar
  nada y se sigue la sección anterior.
- **Despliegue:** esta decisión no autoriza tocar ninguna instalación real; se despliega aparte, con su propia aprobación.
- **Arnés de validación de la Pi y ensayos locales:** generan su contraseña en lugar de escribir la de ejemplo.

## Pruebas (qué demuestra cada una, y cómo se ejecuta)

| Prueba | Qué mide |
|---|---|
| `tests/test_credenciales_aisladas.py` + `tests/escenarios/*.sh` | Corren **como root en un sistema desechable** (CI, o un contenedor sin red) el `bootstrap.sh` real con un `docker` de pega, con usuarios sintéticos: instalación nueva, reejecución, ausente/vacío/ejemplo, base ya creada, y **lectura, escritura, truncado, borrado, movimiento, reemplazo y redirección del enlace** intentados *como cada identidad*. Con controles positivos. |
| `tests/test_compose_credenciales.py` | Ejecuta el servicio `credenciales` con Docker real (sin red) y mide el código de salida de cada valor; comprueba las dependencias y que el `.env` no se monta. |
| `tests/test_credenciales_lib.py` | La biblioteca en bash: lectura como Compose, lista, generación, escritura atómica con fallo en `awk`/`mv`/`chmod`/`chown`, `raiz_dedicada`. |
| `tests/test_credenciales_update.py` | `update.sh` real: se detiene antes de tocar nada; avisa sin fallar. |
| `tests/test_credenciales_app.py`, `tests/test_clave_de_firma_pg.py` | La guarda de la aplicación (sin abrir conexión) y la clave de firma estable entre reinicios (Postgres real). |
| `tests/test_credenciales_lista.py` | Las tres copias de la lista coinciden. |

Sin un sistema desechable con root las pruebas de identidades **se saltan** y se cuentan como *no ejecutadas*.

## Límites conocidos

- Quien está en el grupo `docker` es equivalente a root: puede leer variables con `docker inspect`. No se intenta evitarlo.
- La heurística «ya hay base» es `PG_VERSION`; una base creada fuera de `ZASCARR_DATA_DIR` no se ve.
- Una raíz compartida no queda a salvo de ser reemplazada (solo se avisa).
- No hay bloqueo entre dos instaladores simultáneos.
- Las **fuentes que aparecían activadas** en el informe M4 son un hallazgo separado, sin comprobar aquí.
