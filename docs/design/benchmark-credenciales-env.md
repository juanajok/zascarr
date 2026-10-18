# Ficha — contraseña de la base de datos y protección del `.env` (ensayo M4)

Procedimiento de `docs/design/benchmark-referencias.md` (§13 de `CLAUDE.md`). Esfuerzo proporcional al riesgo: es una
corrección de seguridad y de instalación con evidencia medida propia; las referencias externas **no se han consultado**
(ver «Referencias»).

## 1. Problema local (medido)

Ensayo M4, candidato `0a591d6`, Debian 12 en VM, sin terminal, red cerrada (informe de la fase 1; evidencias 11–13 y 18):

| Hallazgo | Medido |
|---|---|
| **M4-01 — instalación limpia** | `sudo bash bootstrap.sh < /dev/null` copia `.env.example` y termina con **RC=1**: «DB_PASSWORD tiene el valor por defecto. Edita /opt/zascarr/.env…». El README promete «pegar una línea» y tres preguntas. Tras editar el `.env` a mano completa (RC=0) |
| **`.env` legible por todos** | `/opt/zascarr/.env` queda en modo **644**, `root:root`, con `/`, `/opt`, `/opt/zascarr` en 755. Abren el fichero `nobody`, `media` y una cuenta sin sudo (prueba de apertura, sin leer el contenido) |
| Origen | `cp .env.example .env` con la máscara por defecto; ningún `chmod`. `sed -i` posteriores conservan el modo |

## 2. Resultado deseado

1. Una instalación nueva **no exige editar** la contraseña.
2. Una contraseña válida **se conserva** en reejecuciones y nunca se muestra.
3. El `.env` es de `root`, modo 600, **desde su creación** y tras cada modificación.
4. Los consumidores del `.env` siguen funcionando y, si no pueden leerlo, **lo dicen** en español antes de tocar nada.

## 3. Medido para esta corrección

Docker Compose v5.5.1 (anfitrión de desarrollo, `docker compose config` con el fichero de `docker-compose.yml`):

| Caso | Resultado |
|---|---|
| `.env` legible | Resuelve `POSTGRES_PASSWORD` y `DATABASE_URL` con su valor |
| `.env` ilegible, descubrimiento por defecto (enlace del repo) | **Falla en cerrado**: `open …/.env: permission denied`, código 1 |
| `.env` ilegible, `--env-file` explícito | Igual: `permission denied` |
| `.env` ilegible, `-f` desde otro directorio (el comando que imprimía el instalador) | Igual |

Es decir: no arranca con la contraseña por defecto del compose (`SuperSecretPassword123`); pero el mensaje es críptico y en
inglés. Conclusión: con el `.env` cerrado, **los comandos que mostramos deben llevar `sudo`**.

## 4. Consumidores del `.env` (lectura del código)

| Consumidor | Cómo lo lee | Quién lo ejecuta | Acción en esta PR |
|---|---|---|---|
| `bootstrap.sh` | escribe y lee | root (`EUID`=0 exigido) | genera contraseña, crea 600, `env_poner` |
| `update.sh`, `rollback.sh` | `docker compose --env-file` vía `_comun.sh` | root con `sudo` (documentado) | `comprobar_env_legible` en `comprobar_requisitos` |
| `backup.sh` | `docker compose --env-file` | root (escribe en `/var/backups`) | comprobación propia (no carga `_comun.sh`) |
| `etiquetar.sh` | `docker compose run` | **no exigía root** | `comprobar_env_legible`; doc con `sudo` |
| `uninstall.sh` | `docker compose` **y** lectura manual con `grep` | no exigía root | `comprobar_env_legible` **antes** de todo: ilegible ≠ ausente |
| `diagnostico-red.sh` | `docker compose ps` | sin root llega a un aviso previo de `ufw` que ya pide `sudo` | solo ayudas con `sudo` |
| Compose manual (README, ayudas impresas) | `docker compose` con el enlace `repo/.env` | cualquiera | ayudas con `sudo`; README con `umask 077` y `sudo` |
| Contenedores | **no montan el `.env`** (0 montajes; `/app/.env` es un enlace colgante dentro de la imagen) | — | nada |

## 5. Alternativas

| Opción | Decisión |
|---|---|
| Pedir la contraseña en el instalador | Descartada: sin terminal no hay pregunta; y la persona no debe inventar una |
| Seguir exigiendo editar el `.env` | Descartada: es el defecto |
| Generar al crear el `.env` **y** en cualquier reejecución si falta | **Adoptada**, con tres guardas: una puesta por la persona no se pisa; con base ya creada no se inventa; el valor no se imprime |
| Modo 640 `root:docker` | Descartada por ahora: el grupo `docker` ya equivale a root sobre la máquina y no existe siempre; añade un grupo que gestionar. Reabrible si se prueba que un consumidor legítimo lo necesita |
| Modo 600 `root:root` | **Adoptada**: acceso mínimo; todos los consumidores de §4 se ejecutan (o deben) con `sudo` |

## 6. Decisión

Adoptar (propio). `scripts/_credenciales.sh`: `generar_contrasena` (24 bytes del sistema en hexadecimal), `credencial_es_marcador`,
`crear_env_protegido` (`umask 077`), `env_poner` (re-cierra tras `sed -i`; además escapa `#`, que el `set_env_var` anterior
no hacía), `proteger_env`, `preparar_credenciales` y `base_de_datos_creada` (`<datos>/postgres/PG_VERSION`).
Regresiones: `tests/test_credenciales_env.py` y `tests/test_env_consumidores.py`; cada regla se comprobó con una mutación.

## 7. Límites y riesgos que NO cierra esta corrección

- **No se ejecutó `bootstrap.sh` real**: necesita root, Docker y red. Las pruebas cargan el ayudante en un `bash` real y fijan el contrato de
  `bootstrap.sh` por texto. Falta un ensayo en máquina limpia (VM) que no está autorizado en este punto.
- **Instalaciones existentes con base creada y marcador en el `.env`**: se cortan con una explicación (comportamiento previo, ahora con causa y acción).
- `docker-compose.yml` conserva el valor por defecto `${DB_PASSWORD:-SuperSecretPassword123}` y el Postgres publica `127.0.0.1:5432`: no se tocan aquí
  (decisión aparte; con el `.env` legible por el invocante Compose usa su valor, con el ilegible falla en cerrado).
- `/var/backups` es 755: el modo de los volcados se mide en los casos de backup de M4, no aquí.
- El grupo `docker` y root siguen pudiendo leer el secreto por otras vías (`docker inspect`); el objetivo es cuentas locales sin privilegios.
- Los defaults de las fuentes (`comicvine/anilist/tebeosfera/gcd = True`) **no se cambian** (hallazgo separado).

## 8. Referencias

Sonarr/Radarr/Kapowarr/Mylar3/Suwayomi: **no consultadas** para esta ficha (no se infiere soporte ni ausencia por memoria; CLAUDE.md §13).
El criterio aplicado es el de acceso mínimo a secretos y la medición propia del §1 y §3. Pendiente, si el responsable lo pide, comparar
cómo reparten esas referencias la generación y los permisos de sus ficheros de configuración antes de ampliar el alcance.
