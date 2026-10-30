# Aceptación 123b — operaciones recuperables, reinicio seguro y presión de disco (#123)

> **Estado: preparación, NO ejecutada.** Esta entrega deja el inventario, el
> reinicio con reintento acotado, las guardas de espacio, `checks.disk` y el
> procedimiento. La ventana en el host aislado (y, si el PO la autoriza, en la
> Pi) se abre aparte. Hasta entonces **todos los casos de ventana son NOT RUN**;
> no se declara PASS por leer código ni por pasar tests.

## 1. Alcance

Criterios **4** (inventario de operaciones), **5** (reinicio seguro) y **6**
(presión de disco). Se reutilizan los contratos de asignación/alta/vinculación
y el fixture de 123a. **No** hay migraciones, tablas ni columnas nuevas; **no**
hay UI nueva más allá de `/estado`; **no** hay dependencias nuevas.

Fuera de 123b: 123c, la ventana real de reinicio/presión, producción, la
biblioteca real y el crash del importador a mitad (ver §3.1).

## 2. Hosts y ventana

| Host | Uso | Estado |
|---|---|---|
| **Host aislado local con Docker** | Inventario, reinicio de servicio/contenedor/pila y presión con tmpfs real | **NOT RUN** hasta autorización |
| **Pi (producción)** | Solo si el PO exige presión/reinicio en hardware real; ventana propia | **NOT RUN**; no se toca aquí |

No se comparte red, proyecto, contenedores, puertos, binds ni RAM/disco con
producción. La compuerta de aislamiento de 123a-i se reutiliza antes de la
ventana.

## 3. Precisión del PO

### 3.1 Crash del importador a mitad — NOT RUN justificado y aceptado

El importador **no** tiene journal ni operación recuperable persistida. Un
crash a mitad de un ciclo puede dejar trabajo en memoria y no hay forma de
reconciliarlo sin un journal/migración que queda **fuera de 123b**. Por eso:

- **NO se ejecuta** el caso de crash del importador a mitad en esta ventana.
- Se declara **NOT RUN justificado** y **aceptado explícitamente por el PO**.
- No se añade journal, tabla, columna ni migración para cubrirlo.
- Si el PO quiere cubrirlo, va en una entrega separada; no se mezcla con 123b.

El resto de operaciones (asignación, alta, vinculación) sí tienen su contrato
de recuperación y se prueban en los casos 4/5.

### 3.2 Auditoría de comprobaciones de espacio/montaje

Antes de añadir guardas se auditó lo existente:

| Sitio | Qué había | Decisión |
|---|---|---|
| `scripts/backup.sh` | `mountpoint -q` + `stat -c %d` para el disco offsite; **sin** umbral de espacio | Se conservan montaje/dispositivo; el espacio usa el helper único |
| `scripts/instalar_backup.sh` | `mountpoint -q` del disco offsite; **sin** umbral de espacio | No duplica umbral: la primera copia la valida `backup.sh` |
| `bootstrap.sh` | **sin** comprobaciones de espacio/montaje | Fuera de la entrega; solo se audita, no se modifica |
| `scripts/restaurar_datos.sh` | Tenía una copia propia de `df`/margen | Se elimina; carga `scripts/_espacio.sh` |
| `scripts/probar_restauracion.sh`, `update.sh`, `rollback.sh` | Cargan `_comun.sh` | Usan el mismo helper |
| `scripts/medicion/ventana_e.sh` | Preflight de medición: exige 8 GiB libres para los sintéticos | **Ajeno a copias/restauración**; no se escanea ni se cambia |

**Único umbral para copias/restauración:** `necesario + 10 % + 64 MiB`. En los
scripts de copia/restauración vive en `scripts/_espacio.sh` (cargado por
`_comun.sh` y por `restaurar_datos.sh`); en la app, `utils/espacio.py` aplica el
mismo margen para las rutas Python. No hay un segundo umbral en esos scripts.
`scripts/medicion/ventana_e.sh` tiene su propio preflight de medición (8 GiB) y
no es una copia/restauración; `bootstrap.sh` queda fuera y no se toca.

## 4. Fixture 123b

Se parte del fixture sintético de 123a (4 series, 6 números, 40 filas de
archivo, biblioteca pequeña) y se aplica el sidecar:

```bash
export ZASCARR_ENTORNO=123a
python3 scripts/aceptacion/preparar_fixture_123a.py --salida "$VAL/fixture-123a"

# Sembrar en la pila aislada (migraciones a head) y copiar la biblioteca.
export ZASCARR_ENTORNO=123b
python3 scripts/aceptacion/preparar_operaciones_123b.py \
  --database-url "postgresql://...@127.0.0.1:15434/..." \
  --biblioteca "$VAL/fixture-123a/biblioteca"
```

El sidecar **no crea** series, números ni archivos nuevos: reutiliza los del
fixture y solo añade:

- 4 asignaciones: `preparada`, `confirmada`, `limpiada`, `cancelada`;
- 2 altas: `creada`, `deshecha`;
- 2 `import_runs`: uno limpio y otro con error;
- una copia de la asignación `confirmada` bajo `_123b/` (el original no se
  mueve; la fila `files` apunta al destino).

No inventa «en curso» en vinculación: ese estado solo se observa si el candado
consultivo está tomado, y el fixture no lo fuerza.

## 5. Matriz de casos

| Caso | Qué se comprueba | Dónde | Estado |
|---|---|---|---|
| **4.1** | `GET /api/operaciones` devuelve recuentos/estados/fechas de las 4 tablas, sin rutas/nombres | Host aislado | **NOT RUN** |
| **4.2** | `en_curso` solo con candado consultivo tomado; sin candado → `recuperable` | Host aislado + PG | **NOT RUN** |
| **4.3** | El inventario no escanea la biblioteca (`rglob`/`iterdir`/`os.walk` = 0) | Tests + host | **NOT RUN** |
| **5.1** | Reinicio de servicio: reconciliación al arrancar, época/candados, idempotencia | Host aislado | **NOT RUN** |
| **5.2** | Reinicio de contenedor y de pila: mismo contrato | Host aislado | **NOT RUN** |
| **5.3** | Fallo de reconciliación: 3 reintentos con backoff, fallo visible, health no bloqueado | Test de servicio + host | **NOT RUN** |
| **5.4** | `SIGKILL` a mitad de asignación: recuperable, sin reemplazar destinos | Host aislado | **NOT RUN** |
| **6.1** | Guarda de espacio en CBZ, `safe_move`, asignación y portada; no borra | Tests + host | **NOT RUN** |
| **6.2** | Prechequeo en `backup.sh`/`update.sh`/`rollback.sh`/`restaurar_datos.sh`/`probar_restauracion.sh`; `disk_full` | Host aislado | **NOT RUN** |
| **6.3** | `checks.disk` warning/error, sin mirar la biblioteca de red, sin hacer `unhealthy` | Host aislado + tmpfs | **NOT RUN** |
| **6.4** | `/estado` muestra «Disco» con texto y acción segura | Host aislado | **NOT RUN** |
| **08** | No-efectos (producción/biblioteca) | Ventana del PO | **NOT RUN** |

## 6. Procedimiento de ventana

### 6.1 Inventario (4)

1. Aplicar el fixture y el sidecar (§4).
2. `GET /api/operaciones` y guardar el JSON saneado.
3. Comprobar:
   - 4 asignaciones clasificadas (1 completada, 2 recuperables, 1 fallida);
   - 2 altas (1 completada, 1 no aplica);
   - 2 `import_runs` (1 limpio, 1 con errores);
   - `vinculacion` sin «en curso» inventado;
   - ninguna ruta/nombre de archivo en la respuesta.
4. Tomar el candado consultivo de una asignación viva y repetir: esa operación
   pasa a `en_curso`; liberar y vuelve a `recuperable`.
5. Confirmar en logs/estrace que no se recorre la biblioteca.

### 6.2 Reinicio (5)

1. Arrancar la pila aislada con una asignación viva.
2. **Servicio:** `docker compose ... restart zascarr`; esperar `/api/health`;
   comprobar reconciliación y `/api/operaciones`.
3. **Contenedor:** `docker compose ... stop zascarr && ... up -d zascarr`;
   repetir.
4. **Pila:** `docker compose ... down && ... up -d`; repetir.
5. **SIGKILL:** matar el proceso a mitad de la copia (ventana controlada),
   arrancar de nuevo y comprobar que la operación sigue `recuperable`, que el
   destino no se reemplaza y que la biblioteca no se escanea.
6. **Fallo de reconciliación:** inyectar un fallo de BD o del servicio;
   comprobar 3 intentos con backoff, log visible y `/api/health` sigue
   respondiendo (no se bloquea por la reconciliación).

### 6.3 Presión de disco (6)

Usar un **tmpfs real** en el host aislado, no un mock:

```bash
sudo install -d -m 700 "$VAL/disk-small"
sudo mount -t tmpfs -o size=64m tmpfs "$VAL/disk-small"
export ZASCARR_DATA_DIR="$VAL/disk-small"
```

1. Llenar el tmpfs hasta dejar menos del margen (`necesario + 10 % + 64 MiB`).
2. Probar CBZ, `safe_move`, asignación y portada: abortan con
   `EspacioInsuficienteError`, no borran y dejan el original intacto.
3. Probar `backup.sh`, `update.sh`, `rollback.sh`, `restaurar_datos.sh` y
   `probar_restauracion.sh`: abortan antes de copiar/destruir y escriben
   `disk_full` (o el estado equivalente) sin tocar la BD.
4. Configurar `disk_paths`/`disk_warn_free_mb`/`disk_error_free_mb` y comprobar
   `checks.disk` + la fila «Disco» de `/estado`; el semáforo global no pasa a
   `unhealthy` solo por esto.
5. Confirmar que no se mira la biblioteca de red y que no se borra nada.

### 6.4 Crash del importador (NOT RUN)

No se ejecuta. Ver §3.1: sin journal/migración, fuera de 123b, NOT RUN
justificado y aceptado. No se usa esta ventana para probarlo.

## 7. Evidencia

- JSON de `/api/operaciones` y `/api/health` (sin rutas/nombres reales).
- `restore-status.json`/estado de backup con `disk_full` cuando aplique.
- Logs de reconciliación (intentos, backoff) y de los scripts.
- Salida de `df` del tmpfs y del disco de datos.
- Resultado de los tests de asignación/reconciliación y de los prechequeos.
- Tabla PASS/FAIL/NOT RUN firmada por el PO.

## 8. Criterios y límites

- **PASS** solo con evidencia en la ventana; los tests locales no sustituyen la
  ventana real.
- **NOT RUN aceptado:** crash del importador a mitad (§3.1), reinicio real de
  host/Pi y presión real en la Pi si el PO no la autoriza.
- **Riesgos:** el crash del importador queda sin cubrir por diseño; el reinicio
  del host/Pi y la presión real pueden revelar diferencias de hardware; 123c
  sigue fuera.
- No se toca producción, la biblioteca real ni `docs/BACKLOG.md`.
