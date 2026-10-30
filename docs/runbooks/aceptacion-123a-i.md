# Aceptación 123a-i — «Sabemos restaurar» (#123)

> **Estado: preparación, NO ejecutada.** Esta PR deja el procedimiento, la
> compuerta, el fixture y el script de restauración solo-datos. La ventana en la
> Pi y en el host aislado se autoriza aparte. Hasta entonces, **todos los casos
> son NOT RUN**; no se declara PASS por leer el código ni por pasar los tests.

## 1. Alcance y hosts

Casos: **00** compuerta, **01** manifiesto, **02** restauración de aplicación,
**03** estado tras restaurar, **09** dump real a nivel de BD y **10** datos sin
cambiar código. **08** (no-efectos) es transversal.

Fuera: 04, 05, 06, 06b, 07 y la PR de `rollback.sh` (123a-ii); 123b; 123c;
restauración en producción; biblioteca real; cambios funcionales.

| Host | Casos | Motivo |
|---|---|---|
| **Pi (producción)** | **09, 08** y el registro de IDs de producción | 09 solo restaura en base desechable y no arranca la app; 08 compara producción |
| **Host aislado con Docker** | **00, 01, 02, 03, 10** y testigos adversos | Se reconstruye la imagen y se arranca la app sin compartir RAM/disco con producción |

Esta asignación es la del brain (2026-10-29) y **sustituye** el «Pi para el
camino feliz» del 27-oct. Está **pendiente del visto bueno del PO** antes de
ejecutar. Si el PO la cambia, se mueve el caso completo (incluida su evidencia),
no se parte entre hosts; y 02/03/10 no se ejecutan en la Pi sin una ventana
propia y una compuerta a cero.

## 2. Decisiones que hay que confirmar antes de la ventana

1. **Candidato:** `aa7a064` + commit de aislamiento. No se usa la pareja
   histórica `2f8db0a → fdb5519`; esa pareja es de 123a-ii.
2. **Dump de 02/03:** el brain nombra `update_20261029_210527.sql.gz`
   (`dd075aa → aa7a064`) y dice a la vez «no se usa un dump real para 02/03».
   Si ese dump contiene el catálogo real, no se puede publicar ni sirve para el
   token de 03 sin sembrarlo. **Decisión pendiente:**
   - **A (recomendada):** 02/03 con un **dump sintético del fixture** creado en
     el host aislado en `aa7a064`; 03 usa los recuentos 4/6/40/3 y el token.
   - **B:** 02/03 con el update dump de #304; 03 toma los recuentos del dump y
     el token queda **NOT RUN** salvo que se siembre y se cree un dump nuevo al
     inicio de la ventana.
   El procedimiento de §6 sirve para A y B; lo que cambia es el dump y el oráculo.
3. **09:** se prefiere `backup_20261027_165226.sql.gz` (pre-R) y, si no está,
   el ancla `update_20261025_172001.sql.gz`. Los manifiestos de `/anclas` pueden
   no traer `codigo_desplegado`: se crea un **manifiesto de ensayo sidecar** sin
   modificar el original. Un exit 2 no es PASS.
4. **10:** dump **sintético** del fixture en `aa7a064`; no se usa el dump real
   pre-R. Si el PO prefiere el real, se copia al host aislado con `0600`, se
   borra al terminar y se declara.
5. **Fixture 6 números:** el detalle aprobado suma 5 (S1: 1 y 3; S2: 1; S3: 1 y
   2; S4: 0) pero el recuento cerrado es 6. El generador añade **S2 #2** para
   respetar el 6 y conserva el hueco de S1. Queda escrito aquí y en el cuerpo de
   la PR; si el PO prefiere otro número, se cambia el generador antes de la
   ventana.

## 3. Entorno aislado

### 3.1 Copia y aislamiento

```bash
VAL=/srv/123a-host                  # host aislado; en la Pi, /srv/123a-pi
sudo install -d -m 700 "$VAL"
sudo git clone --no-hardlinks <repo> "$VAL/zascarr"
cd "$VAL/zascarr"
git checkout -B 123a/aa7a064 aa7a064
```

Crear el **commit de aislamiento** (solo `docker-compose.yml`, 5 líneas):

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("docker-compose.yml")
s = p.read_text()
cambios = [
    ("name: zascarr\n", "name: zascarr-123a\n"),
    ("container_name: zascarr-db", "container_name: zascarr-123a-db"),
    ('- "127.0.0.1:5432:5432"', '- "127.0.0.1:15432:5432"'),
    ("container_name: zascarr-orquestador", "container_name: zascarr-123a-orquestador"),
    ('- "${ZASCARR_BIND_ADDRESS}:8000:8000"',
     '- "${ZASCARR_BIND_ADDRESS}:18000:8000"'),
]
for viejo, nuevo in cambios:
    assert s.count(viejo) == 1, viejo
    s = s.replace(viejo, nuevo)
p.write_text(s)
PY
git add docker-compose.yml
git commit -m "123a: aislar el compose de la copia"
git diff HEAD^ -- docker-compose.yml --stat   # solo 5 líneas
```

No se añaden líneas de fuentes al compose. Las fuentes se apagan por datos
(§5) para que el aislamiento sea el mismo diff en cualquier commit.

### 3.2 `.env`

```bash
umask 077
cat > "$VAL/.env" <<EOF
DB_PASSWORD=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
ZASCARR_DATA_DIR=$VAL/data
HOST_LIBRARY_DIR=$VAL/library
HOST_DOWNLOADS_DIR=$VAL/downloads
HOST_AMULE_INCOMING_DIR=$VAL/incoming
ZASCARR_BIND_ADDRESS=127.0.0.1
TZ=Europe/Madrid
COMICVINE_API_KEY=
PROWLARR_API_KEY=
TRANSMISSION_USERNAME=
TRANSMISSION_PASSWORD=
AMULE_PASSWORD=
FORUM_ENABLED=false
FORUM_URL=
BASE_URL=
ALLOWED_HOSTS=
EOF
chmod 600 "$VAL/.env"
install -d -m 700 "$VAL"/{data,library,downloads,incoming,backups,status,evidencia}
```

Exportar **siempre** antes de los scripts:

```bash
export REPO_DIR="$VAL/zascarr"
export ZASCARR_ROOT="$VAL"
export ENV_FILE="$VAL/.env"
export COMPOSE_FILE="$VAL/zascarr/docker-compose.yml"
export BACKUP_DIR="$VAL/backups"
export BACKUP_STATUS_DIR="$VAL/status"
export HEALTH_URL="http://127.0.0.1:18000/api/health"
export HEALTH_TIMEOUT=120   # segundos TOTALES de espera; default 120
export DB_NAME=zascarr
export DB_USER=comics_admin
```

`restaurar_datos.sh` **no** usa defaults de producción: si falta una de estas
variables, se detiene.

### 3.3 Compuerta 00

En la Pi, contra la configuración real (solo lectura):

```bash
bash scripts/verificar_aislamiento_123a.sh \
  --entorno "$VAL" \
  --compose "$VAL/zascarr/docker-compose.yml" --env "$VAL/.env" \
  --prod-compose /opt/zascarr/zascarr/docker-compose.yml \
  --prod-env /opt/zascarr/.env
bash scripts/verificar_aislamiento_123a.sh \
  --prod-compose /opt/zascarr/zascarr/docker-compose.yml \
  --prod-env /opt/zascarr/.env \
  --ids-antes "$VAL/evidencia/ids-produccion.txt"
```

En el host aislado no hay producción: se usa una **copia de referencia saneada**
de la config de producción (mismos proyecto/contenedores/puertos/red/binds, sin
secretos) y se compara contra ella. Los IDs de producción se registran en la Pi.

La compuerta exige **0 colisiones** de proyecto, `container_name`, puertos
publicados, red y binds; y que **todos** los binds de la copia estén bajo `$VAL`.
Cualquier colisión, bind fuera del entorno, override inesperado o ID de
producción cambiado: **DETENER**.

También se ejecuta `rollback.sh --dry-run` dentro de la copia, solo para ver el
plan y confirmar que apunta a la copia:

```bash
sudo env REPO_DIR="$REPO_DIR" ZASCARR_ROOT="$ZASCARR_ROOT" \
  ENV_FILE="$ENV_FILE" BACKUP_DIR="$BACKUP_DIR" HEALTH_URL="$HEALTH_URL" \
  bash "$REPO_DIR/scripts/rollback.sh" --dry-run
```

## 4. Fixture sintético

El generador exige `ZASCARR_ENTORNO=123a`, escribe 4 series, 6 números, 40
filas de archivo (30 `.cbz`, 9 `.cbr`, 1 `.cb7`; 24 con issue, 2 `is_missing`,
1 sin hash, 1 con `formato_contenido`), 3 operaciones y 3 wishlist. La
biblioteca son 38 ficheros reales (2 filas missing), ≤ 5 MB.

```bash
export ZASCARR_ENTORNO=123a
python3 scripts/aceptacion/preparar_fixture_123a.py --salida "$VAL/fixture"
```

El generador deja `biblioteca/`, `seed.sql`, `token.txt`, `secret_key.txt` y
`resumen.json`. **No se publican** `seed.sql`, `token.txt` ni `secret_key.txt`:
contienen el secreto sintético y el token.

Copiar la biblioteca al montaje del compose **preservando mtime** (el token
firmado incluye `mtime_ns`):

```bash
cp -a "$VAL/fixture/biblioteca/." "$VAL/library/"
```

Sembrar en la pila aislada, con las migraciones ya aplicadas:

```bash
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d postgres
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm zascarr \
  alembic upgrade head
# Marca de la BD aislada: sin ella el generador no trunca ni aplica nada (solo en la pila aislada, nunca en producción).
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U comics_admin -d zascarr -c "COMMENT ON DATABASE zascarr IS 'zascarr-123a-aislada';"
# El generador puede aplicar con psql si el host lo tiene:
python3 scripts/aceptacion/preparar_fixture_123a.py \
  --salida "$VAL/fixture" --reset \
  --aplicar --database-url "postgresql://comics_admin:<password>@127.0.0.1:15432/zascarr"
```

`--aplicar` exige **host local** (`127.0.0.1`, `localhost` o `::1`) y **puerto
15432**. Una URL sin puerto (5432 por defecto), con otro puerto o con host remoto
se rechaza **antes de llamar a `psql`**, incluso con `--reset`/`--force`. Es una
guardia contra el error humano; la compuerta real sigue siendo
`verificar_aislamiento_123a.sh`. La URL no admite parámetros (`?host=…`, `?port=…`),
varios hosts ni fragmentos, y la BD debe llevar la marca `zascarr-123a-aislada`
(`COMMENT ON DATABASE`, arriba): sin ella se rechaza antes de truncar o aplicar.

Si no hay `psql` en el host, aplicar `seed.sql` con `psql` dentro del contenedor
`postgres`; el fichero está en `$VAL/fixture/seed.sql`. El test PG real de la PR
aplica ese `seed.sql` con `ON_ERROR_STOP=1` sobre una base migrada a head.

Comprobar antes de crear el dump:

```sql
select (select count(*) from series), (select count(*) from issues),
       (select count(*) from files), (select count(*) from vinculacion_operaciones),
       (select count(*) from wishlist);
-- 4 | 6 | 40 | 3 | 3
```

### 4.1 Dump y manifiesto del fixture (para 01/02/03/10)

```bash
TS=$(date +%Y%m%d_%H%M%S)
DUMP="$VAL/backups/update_${TS}.sql.gz"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  pg_dump -U comics_admin zascarr | gzip > "$DUMP"
chmod 600 "$DUMP"
SHA=$(sha256sum "$DUMP" | awk '{print $1}')
BYTES=$(stat -c %s "$DUMP")
ALEMBIC=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U comics_admin -d zascarr -At -c "select version_num from alembic_version" \
  | tr -d '[:space:]')
HEAD=$(git -C "$REPO_DIR" rev-parse HEAD)
jq -n --arg backup "$(basename "$DUMP")" --arg sha "$SHA" --argjson bytes "$BYTES" \
  --arg alembic "$ALEMBIC" --arg head "$HEAD" \
  --arg created "$(date -Iseconds)" --arg id "123a-fixture-${TS}" \
  '{schema: 1, backup: $backup, sha256: $sha, bytes: $bytes,
    codigo_destino_sha_completo: $head, codigo_desplegado_sha_completo: $head,
    alembic: $alembic, created_at: $created, origin: "123a fixture", id: $id,
    verificacion: {gzip: "ok", cabecera: "ok",
      tablas: ["alembic_version", "series", "files", "wishlist"], sha256: "ok"}}' \
  > "$VAL/backups/MANIFIESTO-update_${TS}.json"
chmod 600 "$VAL/backups/MANIFIESTO-update_${TS}.json"
```

Este manifiesto acredita el HEAD actual en los dos campos de código, que es lo
que exige `restaurar_datos.sh` para una restauración solo-datos. El mismo dump
sirve para 01, 02/03 y 10; si se quiere separar 10, se crea otro TS con el mismo
procedimiento.

## 5. Apagar fuentes e integraciones

Las variables `*_ENABLED` del `.env` **no las pasa el compose**; las fuentes se
gobiernan desde `runtime_settings` y pisan al `.env`. El generador ya siembra
`comicvine_enabled=false`, `anilist_enabled=false`, `tebeosfera_enabled=false`,
`gcd_enabled=false`, `prowlarr_enabled=false`, `transmission_enabled=false`,
`amule_enabled=false` y URLs vacías. Antes de arrancar la app, comprobar en
`/api/health` que `fuentes` salen `disabled` y que no hay llamadas salientes.

Con datos reales (solo si el PO elige B para 02/03, o para 10 con dump real):
antes de arrancar, apagar las integraciones en `runtime_settings` y, durante la
ventana de health, poner la base en solo lectura para la app:

```sql
update runtime_settings
set values = values || '{"comicvine_enabled": false, "anilist_enabled": false,
  "tebeosfera_enabled": false, "gcd_enabled": false,
  "prowlarr_enabled": false, "transmission_enabled": false,
  "amule_enabled": false, "prowlarr_url": "", "transmission_url": "",
  "amule_url": ""}'::jsonb
where id = 1;
alter database zascarr set default_transaction_read_only = on;
```

Al terminar: `alter database zascarr set default_transaction_read_only = off;`.
Esta técnica es nueva; se registra como parte de la evidencia y no se usa con el
fixture sintético si no hace falta.

## 6. Casos

### 123a-00 — compuerta

- Ejecutar §3.3.
- Guardar la salida (0 colisiones), la tabla de proyecto/contenedores/puertos/red/binds
  y los IDs de producción antes/después.
- **Testigo adverso:** copia sin el commit de aislamiento (o con `name: zascarr`):
  la compuerta debe dar colisiones y salir ≠0.
- **Resultado:** PASS solo si 0 colisiones y IDs sin cambios.

### 123a-01 — manifiesto

- Dump de 02/03 (§4.1) con manifiesto de esquema 1 de #334.
- Comprobar: `sha256`, `bytes`, `codigo_destino`/`codigo_desplegado`, `alembic`,
  `id`, `created_at`, `origin`, `verificacion`; `gzip -t`, cabecera y 4 tablas.
- Validación DB-only: `probar_restauracion.sh --dump <dump> --manifest <manifiesto>`
  (no arranca la app).
- **Testigo adverso:** cambiar un carácter del `sha256`; debe abortar con
  `manifest_no_coincide`.
- **Resultado:** PASS solo con exit 0 y manifiesto completo.

### 123a-02 — restauración de aplicación

Con el candidato `aa7a064` + aislamiento y el dump de §4.1:

```bash
bash scripts/restaurar_datos.sh \
  --dump "$VAL/backups/update_<TS>.sql.gz" \
  --manifest "$VAL/backups/MANIFIESTO-update_<TS>.json" \
  --sha "$(git -C "$REPO_DIR" rev-parse HEAD)" \
  --alembic-esperada 0020 \
  --yes
```

El script:
1. exige árbol limpio y `HEAD == --sha`;
2. comprueba `docker compose config` con proyecto `zascarr-123a` (nunca `zascarr`);
3. valida manifiesto, SHA, bytes, `gzip -t`, cabecera y tablas;
4. compara `version_num` del dump y de la BD actual **antes** del `dropdb`;
5. crea `rollback-safety_<TS>.sql.gz` verificada;
6. para la app, `dropdb --force`, `createdb`, `psql ON_ERROR_STOP`;
7. arranca con `up -d` **sin build ni git reset**;
8. espera el health hasta `HEALTH_TIMEOUT` **total** (reintentos cada 2 s),
   exige HTTP 200 y `.checks.database == "ok"`, y comprueba recuentos,
   vínculos y que el `HEAD` no cambió. Un solo `curl` no basta: la app tarda
   unos segundos en arrancar tras `up -d`.

Evidencia: comandos, salida, tiempo, copia previa, health 200, URL `:18000`.
**No se usa `rollback.sh` en 123a-i**: el candidato es el actual y la pareja
histórica es de 123a-ii. Si el PO elige B, el dump cambia pero el procedimiento
es el mismo.

### 123a-03 — estado tras restaurar

- Esquema/Alembic: `0020` esperado y obtenido.
- Recuentos: los del dump/manifiesto; con fixture A: `series=4`, `issues=6`,
  `files=40`, `operaciones=3`, `wishlist=3`.
- `files` con issue = 24; `is_missing=2`; `sha256_hash IS NULL=1`;
  `metadata ? 'formato_contenido'=1`.
- Sin huérfanos en `files`, `issues`, `wishlist`; `vinculacion_operaciones` con
  series existentes (el script lo comprueba).
- UI: `/ui/pendientes`, `/ui/series` y la lista con `serie=<S1>` responden 200.
- Token: `POST /ui/pendientes/carpetas/asistente/vinculacion/confirmar` con el
  token de `token.txt` devuelve el mismo informe; `secret_key` SHA-256 antes y
  después idéntico. La cadena se cierra en 15 min; si caduca, se registra y
  `ignorar_caducidad` es solo respaldo.
- **Testigo adverso:** copia del dump con un vínculo roto o un recuento cambiado;
  el oráculo debe fallar.
- **Resultado:** PASS solo si todos los oráculos pasan; si el token caduca, 03
  queda parcial/NOT RUN en ese punto, no PASS.

### 123a-09 — dump real en base desechable (Pi)

- Usar la copia de `/anclas` (preferida `backup_20261027_165226`; alternativa
  `update_20261025_172001`), **sin arrancar la app**.
- Verificar `sha256sum`, `gzip -t`, permisos; crear manifiesto de ensayo sidecar
  si falta `codigo_desplegado`.
- `probar_restauracion.sh --dump <dump> --manifest <manifiesto>`; **exit 0**.
- Oráculo adicional: `vinculacion_operaciones`, vínculos/huérfanos, `N de M`,
  tablas, Alembic.
- **Testigo adverso:** dump truncado o hash del manifiesto alterado; debe
  rechazarse.
- **Resultado:** PASS/FAIL; si el dump ya no está o no verifica, **NOT RUN**
  (no FAIL).

### 123a-10 — datos sin cambiar código (host aislado)

- Dump sintético del fixture en `aa7a064` (§2.4), con manifiesto que acredite el
  HEAD.
- `restaurar_datos.sh --dump ... --manifest ... --sha <HEAD> --alembic-esperada 0020 --yes`.
- Verificar `HEAD` antes/después, health 200, recuentos/vínculos, UI, `git status`
  limpio, sin `build`/`git reset`, y que no se montó la biblioteca real.
- **Testigo adverso:** `--sha` incorrecto debe abortar antes del `dropdb`; dump
  con un vínculo roto debe fallar el oráculo.
- **Resultado:** PASS solo si el código no cambió y los datos coinciden.

### 123a-08 — no-efectos

Antes y después de cada carrera en la Pi:

```bash
bash scripts/verificar_aislamiento_123a.sh --ids-antes "$VAL/evidencia/ids-produccion.txt" ...
# ... carrera ...
bash scripts/verificar_aislamiento_123a.sh --ids-despues "$VAL/evidencia/ids-produccion.txt" ...
docker ps --format '{{.ID}} {{.Names}} {{.Status}}'
```

Comprobar contenedores, volúmenes, puertos, base y biblioteca de producción;
`docker compose config` de producción sin cambios; ninguna ruta de la biblioteca
real montada en la copia. **PASS solo si todo es idéntico.**

## 7. Evidencia

Una ficha por caso:

```text
Caso: 123a-0X
Host: pi | host-aislado (alias)
Resultado: PASS | FAIL | NOT RUN
Hora: ISO 8601 con zona
Candidato: <SHA completo + aislamiento>
Dump: <alias/id> | sha256=<...> | bytes=<...> | manifiesto=<id>
Alembic esperado/obtenido: 0020/0020
Recuentos: series ... issues ... files ... operaciones ... wishlist ...
Filas encontradas: N de M
Salud: HTTP 200; checks.database=ok
UI: /ui/pendientes 200; /ui/series 200
Token: mismo informe sí/no; secret_key SHA antes=... después=...
No-efectos: IDs producción antes=... después=...; binds=...
Testigo adverso: qué se alteró -> fallo esperado -> fallo obtenido
Comando: ...
Salida clave: ...
Desviaciones: ...
```

En GitHub solo recuentos, IDs, estados y hashes. Nada de rutas/nombres reales,
tokens, `secret_key` ni capturas con datos reales. El detalle completo se queda
en `$VAL/evidencia`, `0600`.

## 8. Paradas, limpieza y límites

**Parar** si: colisión ≠ 0; ID de producción cambiado; bind fuera del entorno;
árbol sucio; dump/manifiesto ausente o inválido; `gzip`/cabecera/tablas fallan;
Alembic incompatible; health ≠ 200; recuento/vínculo distinto; dos intentos
fallidos; memoria/espacio por debajo del umbral; ventana agotada. Un caso
detenido es **FAIL o NOT RUN**, nunca PASS.

**Limpieza:** `docker compose -p zascarr-123a down -v` acotado a la copia; borrar
el repo de la copia; borrar dumps reales copiados; conservar la evidencia
saneada fuera de la retención. No tocar `docs/BACKLOG.md`, el checkout principal
ni otros worktrees.

**Esta PR no ejecuta nada**: no crea dumps/restauraciones reales, no arranca la
Pi, no cambia `rollback.sh`/`probar_restauracion.sh`/`backup.sh` y no declara
PASS de ningún caso. Los PASS/FAIL/NOT RUN de la ventana se publican después,
caso por caso, con su host.
