# OPS4 — B2b: reserva atómica cableada (#443)

**Estado:** implementado y validado en VM sobre `8412f2af` con un `update.sh`
inofensivo; la función sigue **deshabilitada** y no se ha desplegado.
**Base:** `220d8b40` (B2a fusionado).

B2a añadió las primitivas; B2b las conecta al auxiliar y a la unidad. El
contrato de referencia es §B2 de
[`especificacion-ops4-cierre.md`](especificacion-ops4-cierre.md#L695-L799).

## Cambios

- **Fase `reservada`** entre `aceptada` y `preparacion` en el estado v2
  ([contrato](ops4-b1-contrato-estado.md)); el lector de la app la acepta. No
  cambia el número de claves ni invalida estados anteriores.
- **Auxiliar** ([zascarr_actualizar_aux.py](../../deploy/ops/zascarr_actualizar_aux.py)):
  flujo P3–P12. Toma el cerrojo de admisión, comprueba el de operaciones, lee
  el estado, verifica el testigo **sin consumir**, crea la marca de intento,
  escribe la reserva, arranca, espera la confirmación del trabajador y solo
  entonces consume. Ocupado en P4 no escribe estado ni consume; un `id`
  repetido no vuelve a arrancar.
- **Entrada de la unidad** ([zascarr_actualizar_entrada.py](../../deploy/ops/zascarr_actualizar_entrada.py)):
  primera acción = `flock` fd 9 del cerrojo de operaciones; si está ocupado
  sale 75 sin efectos. Si lo toma, exige una reserva vigente (≤ 300 s),
  calcula `head0` y publica `en_curso`/`reservada` antes de `exec` a
  `scripts/update.sh`; el descriptor 9 se conserva y `_cerrojo.sh` lo
  reconoce.
- **Unidad** ([zascarr-actualizar.service](../../deploy/systemd/zascarr-actualizar.service)):
  `ExecStart` apunta a la entrada; `ZASCARR_ACTUALIZAR_UNIDAD=1`,
  `ZASCARR_REPO`, `ZASCARR_OPS_DIR` y `ZASCARR_OPS4_DIR` en el entorno;
  `ReadWritePaths` usa `@ZASCARR_DATA_DIR@` (permite el directorio de datos
  configurado; antes estaba fijado a `/var/lib/zascarr`).
- **Instalador**: copia la entrada y crea `ops4/intentos` (B2a); no activa
  nada.
- **Reconciliación**: una reserva `aceptada` con más de 300 s sin avanzar (o un
  `en_curso` con más de 7200 s) se marca `incierta` antes de admitir otra
  petición; deja de bloquear para siempre. La salida 76 de la entrada (reserva
  no vigente) la cierra el `ExecStopPost` como `fallida`; un 2 de `update.sh`
  sigue siendo `incierta` (puede ocurrir después de efectos).

## Evidencia VM (2026-11-26)

Debian 13 sobre overlay nuevo, sin NIC, material en CD de solo lectura,
instalador real `--sin-systemd`, unidades reales, socket real, clave sintética
del instalador y un **`update.sh` inofensivo** que toma el cerrojo, anota una
línea y duerme 3 s. `git` es un fixture que devuelve un SHA fijo para
`head0`.

| Comprobación | Resultado |
|---|---|
| Primera petición | `aceptada`; estado `en_curso`/`reservada` con `head0` |
| Replay inmediato del mismo `id` | `operacion_en_curso` (P4 tiene prioridad); **una sola** ejecución |
| Petición distinta durante la operación | `operacion_en_curso`; sin segunda ejecución |
| Terminal del `ExecStopPost` | `hecha`, `resultado=hecha`, `codigo=success:exited:0` |
| Cerrojo heredado | la entrada lo toma en fd 9 y `_cerrojo.sh` lo reconoce |
| Reserva huérfana | se reconcilia a `incierta` a los 300 s (prueba unitaria); no se probó en VM |
| Directorio de datos configurado | `ReadWritePaths=@ZASCARR_DATA_DIR@` permite la publicación |

## Límites (NOT RUN)

- El `update.sh` de la VM es un fixture: no se probaron Git real, Docker,
  PostgreSQL, migraciones, salud ni la UI.
- No se probó la Raspberry Pi, un corte de energía, la rotación de clave ni
  el runbook de activación.
- La revisión final de SecOps del SHA que se fusione y las demás puertas de
  OPS4 siguen pendientes. Esta evidencia no autoriza habilitar ni desplegar.
