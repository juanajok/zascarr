# Copias de seguridad operativas (#334, E2)

Fecha: 2026-10-28. Alcance: **B1** (copia programada, fuera del disco, manifiesto,
aviso en `/estado` y retención por referencia viva). La restauración periódica en
una base desechable es **B2**, en una PR aparte.

## Por qué

`scripts/backup.sh` existía, pero en la Pi no estaba instalado y escribía en el
mismo disco que los datos. Peor: la retención `find -mtime +14` borraba también
los `update_*` emparejados con una referencia de rescate, y al desaparecer el
dump `podar_refs_huerfanas()` se llevaba la referencia. El resultado era una
instalación sin copias y con la única vía de vuelta en riesgo.

## Arquitectura

```
systemd timer (diario, 04:00 + jitter)
   └─ backup.sh (host, root)
        ├─ pg_dump | gzip → BACKUP_DIR (disco de datos)
        │     + MANIFIESTO-<dump>.json
        ├─ copia verificada → BACKUP_OFFSITE_DIR (disco de respaldo)
        │     + manifiesto
        ├─ sincroniza los dumps con ref de rescate viva
        ├─ retención por referencia, no solo por edad
        └─ status.json → BACKUP_STATUS_DIR
                              │ bind mount read-only
                              ▼
                    contenedor: /run/backup-status/status.json
                              │
                    /api/health (checks.backup + warnings.backup)
                              │
                    /estado (fila «Copias de seguridad» + aviso)
```

Se reutiliza el patrón de la VPN: un fichero JSON del host montado read-only. No
hay tabla nueva ni migración.

## Retención: por referencia viva

La regla es la que pidió el responsable: **si un dump tiene una referencia de
rescate viva, no se borra, sin importar su edad**. Se enumeran:

- `refs/zascarr/update/<TS>` → protege `update_<TS>.sql.gz`.
- `refs/zascarr/rollback-rescue/<TS>` → protege `rollback-safety_<TS>.sql.gz`.

`aplicar_retencion [dir]` aplica la misma regla al directorio local y al offsite.
Los `backup_*` sin referencia caducan a `RETENTION_DAYS` (14). `podar_refs_huerfanas()`
y `podar_refs_rescate_rollback()` siguen podando solo las refs cuyo dump ya no existe.

Esto protege la pareja de `fdb5519` (`20261025_172001`, que a los 15 días habría
sido elegible) y la de `6ffd855` (`20261028_130600`), además de cualquier futura.

## Manifiesto

`escribir_manifiesto` en `_comun.sh` (atómico, `0600`, `jq`):

```json
{
  "schema": 1,
  "backup": "backup_<TS>.sql.gz",
  "sha256": "…",
  "bytes": 0,
  "codigo_desplegado_sha_completo": "6ffd855…",
  "alembic": "0020",
  "created_at": "…",
  "origin": "backup.sh (timer systemd)",
  "id": "backup-<TS>",
  "verificacion": {"gzip": "ok", "cabecera": "ok", "tablas": ["alembic_version", "series", "files", "wishlist"], "sha256": "ok"},
  "offsite": {"copia": true, "sha256": "…", "bytes": 0, "verificada": true}
}
```

`update.sh` usa la misma función para su `update_<TS>`, **después del
fast-forward**: `codigo_destino_sha_completo` es el commit anterior y
`codigo_desplegado_sha_completo` el que acaba de quedar; añade
`referencia_emparejada` y `cubre_rollback_de_codigo`. El manifiesto se escribe
una vez conocido el commit nuevo, no antes del `merge`.
El manifiesto del offsite añade `origen_copia` y `sha256_origen`.

> Corrección puntual (2026-10-28): la pareja `20261028_154503`, creada antes de
> este arreglo, se corrigió con un backfill manual de su manifiesto. No es un
> procedimiento nuevo ni se repite en cada despliegue.

## Verificación

Antes de anunciar una copia:

1. `gzip -t`.
2. Cabecera `PostgreSQL database dump`.
3. `COPY public.alembic_version`, `series`, `files` y `wishlist`.
4. SHA-256 y bytes en el manifiesto.
5. La copia offsite se verifica contra el SHA local; si no coincide, se descarta.
6. `mountpoint` y dispositivo distinto **antes** de escribir en el offsite.

## Aviso en `/estado`

`status.json` (en `BACKUP_STATUS_DIR`, `0644`, sin rutas ni nombres de la
biblioteca):

- `status`: `ok` | `degraded` (copia diaria correcta; aviso secundario, p. ej. anclas) | `failed` (copia, verificación u offsite).
- `error`: `offsite_mount_missing`, `pg_dump_failed`, `gzip_invalid`,
  `header_missing`, `tables_missing`, `manifest_failed`, `offsite_copy_failed`,
  `offsite_verify_failed`, `anchor_sync_failed`, `unexpected`.
- `last_success_at_epoch`, `last_local_success_at_epoch`, `last_attempt_at_epoch`.

`/api/health` añade `checks.backup` y `warnings.backup`:

- `ok` si la última copia completa es ≤26 h.
- `warning` entre 26 y 48 h, o si hay un aviso secundario (anclas).
- `error` si la última copia falló (incluido el offsite), nunca corrió o supera 48 h.

Un fallo de backup deja el `status` global en `degraded` (no en `unhealthy`: la
BD sigue siendo el único fallo duro) y el HTTP sigue en 200. `/estado` pinta la
fila y el detalle en «Avisos».

## Instalación (ventana de #334)

- Unidades versionadas en `deploy/systemd/`: `zascarr-backup.service` y
  `zascarr-backup.timer` (04:00, `Persistent=true`, `RandomizedDelaySec=15min`).
- `/usr/local/bin/backup.sh` es un wrapper de 3 líneas a
  `${ZASCARR_REPO}/scripts/backup.sh`.
- `/etc/default/zascarr` (600) fija `ZASCARR_REPO`, `BACKUP_DIR`,
  `BACKUP_OFFSITE_DIR`, `BACKUP_OFFSITE_MOUNT`, `BACKUP_STATUS_DIR` y
  `RETENTION_DAYS`.
- `scripts/instalar_backup.sh --dry-run` enseña el plan; `--yes` instala,
  habilita el timer y hace la primera copia con verificación.
- El aviso en `/estado` requiere desplegar B1 (el compose monta el estado y el
  `health.py` lo lee). La copia y la retención funcionan aunque el aviso se
  despliegue después.

## Pruebas

- `tests/test_backup_script.py`: éxito local/offsite, `pg_dump` caído, dump sin
  cabecera, montaje ausente, offsite no escribible y hash del offsite manipulado.
- `tests/test_retencion_ancla.py`: los dumps con ref viva sobreviven con mtime de
  20 días; los demás se borran; la misma regla en el offsite; la ref sin dump se
  poda y las vivas se conservan.
- `tests/test_health.py`: fresco, fallido, degradado, 30 h, 50 h, ausente y JSON
  inválido; la BD caída sigue siendo `unhealthy`.
- `tests/conftest.py`: las pruebas que no son de backups parten de una copia
  reciente, para no convertir cada `/api/health` en `degraded`.

## B2 — restauración en base desechable

Implementada en la misma tarjeta (#334):

- `scripts/probar_restauracion.sh`: `--dump` (por defecto el `backup_*` más
  reciente), verificación + manifiesto + `sha256sum -c`, base
  `zascarr_restore_<TS>_<pid>`, `psql --ON_ERROR_STOP`, `dropdb --force` con
  `trap`; solo el contenedor `postgres`, nunca la app.
- Oráculo: recuentos de los bloques `COPY` del dump frente a los restaurados;
  28 tablas; 4 de dominio; `alembic` del manifiesto. El fixture real (13 MB,
  28 tablas, 1.339 `files`) no es un número fijo en el código.
- `restore-status.json` separado; `checks.restore`/`warnings.restore`; fila
  «Restauración» en el panel; 35/70 días; `degraded`, HTTP 200.
- `zascarr-restore.service`/`.timer` (día 1, 05:00 + jitter); instalador de B1
  extendido; primera restauración.
- Hook en `update.sh`: solo `HIZO_UPDATE=1` (no-op excluido), después del
  healthcheck y del manifiesto post-fast-forward; si falla, `warn` + estado,
  sin rollback de la app. El despliegue se invoca con `--rama main` (#351).
- Pruebas: `test_restore_script.py` (adversas), `test_restore_pg.py` (Postgres
  real), `TestHealthRestore`; `test_update_manifest.py` con `--rama main`.

## Límites

- No se toca la biblioteca de tebeos.
- Las copias contienen rutas y nombres reales: se quedan en la Pi y su disco de
  respaldo; en GitHub solo se publican recuentos, identificadores, estados y hashes.
- `docs/BACKLOG.md` no se toca en B1; el cierre de E2 se actualiza cuando #334
  esté completa (B1 + B2).
