# OPS4 — QA independiente de la autorización corta app→host (2026-11-20)

Revisión de QA de la **fase aislada**: emisor app-side, composición con
reautenticación, verificador host, consumo durable por prefijo propio y barreras
de aislamiento/UI deshabilitada. **No** se ha ejecutado la suite completa, ni
Docker, ni VM, ni la Pi, ni `update.sh`; no se ha editado código, ni se ha hecho
commit/push. La actualización sigue **DESHABILITADA**.

## 1. Snapshot revisado

- `HEAD` del worktree: **`55baba87`** (`feat/ops4-seguridad-443`).
- El árbol está **sucio a propósito** sobre ese commit: la implementación y sus
  pruebas de esta fase están sin commitear. El QA se aplica a este snapshot, no
  a `HEAD` limpio. Si el árbol cambia, hay que repetir los comandos.

Ficheros revisados y ejecutados (sha256 del snapshot):

| Fichero | sha256 |
|---|---|
| `deploy/ops/verificador_autorizacion_ops4.py` | `bd0a653b…d629` |
| `deploy/ops/registro_repeticiones_ops4.py` | `d68ba8fc…c191` |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1…ff14` |
| `tests/test_ops4_autorizacion.py` | `3451b4b8…81bc` |
| `tests/test_ops4_autorizacion_compuesta.py` (nuevo) | `7b3de1a1…a887` |
| `tests/test_ops4_registro_repeticiones.py` | `f28574b0…0219` |
| `tests/test_ops4_aislamiento.py` | `167d45af…9a38` |
| `tests/test_ops4_ui_deshabilitada.py` (sin cambios) | `2545185b…2fac` |

Documentos de referencia usados: [especificación](especificacion-ops4-autorizacion.md)
§5–§12 (criterios AC-AUT-01…19 y requisitos de prueba §11.1),
[contrato app-host](ops4-autorizacion-app-host.md) y
[registro de repeticiones](ops4-registro-repeticiones.md). Los documentos
nuevos sin seguimiento (`benchmark-ops4-autorizacion.md`,
`ui-ops4-autorizacion-2026-11-20.md`) **no** forman parte de esta revisión.

## 2. Comandos y contadores

Todos desde `cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443`, con
`PYTHONPATH=.:src` y el intérprete `.tmp-test-venv/bin/python`.

**Pruebas dirigidas del diff** (autorización, composición, registro, aislamiento,
UI deshabilitada, cortes del registro):

```sh
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python \
  -m pytest tests/test_ops4_autorizacion.py tests/test_ops4_autorizacion_compuesta.py \
  tests/test_ops4_registro_repeticiones.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_ui_deshabilitada.py tests/test_ops4_cortes_registro.py -q
# 167 passed in 4.12s — código de salida 0
```

Repetición con `--basetemp` en disco (no en `tmpfs`) y repeticiones parciales:

```sh
PYTHONPATH=.:src … -m pytest <los 6 ficheros> -q \
  --basetemp=/mnt/Datos/Documentos/Repos/zascarr/.tmp-qa-ops4-443
# 167 passed in 5.64s — directorio temporal borrado después

PYTHONPATH=.:src … -m pytest tests/test_ops4_autorizacion.py \
  tests/test_ops4_autorizacion_compuesta.py -q        # 104 passed in 1.68s
PYTHONPATH=.:src … -m pytest tests/test_ops4_autorizacion.py \
  tests/test_ops4_autorizacion_compuesta.py tests/test_ops4_registro_repeticiones.py \
  tests/test_ops4_aislamiento.py -q                   # 160 passed in 2.21s
```

Pruebas de puerta/paridad vigentes (no tocan la unidad ni el auxiliar real):

```sh
PYTHONPATH=.:src … -m pytest tests/test_ops_paridad.py tests/test_ops4_gate.py \
  tests/test_ops4_ui_gate.py <los 6 ficheros del diff> -q
# 191 passed in 6.63s — 24 casos extra (10 paridad + 9 gate + 5 ui_gate)
```

Recuento por fichero del conjunto de 167: aislamiento 19, composición 59,
autorización 45, cortes del registro 3, registro 37, UI deshabilitada 4.
**Sin `skip`/`xfail`/`NOT RUN` dentro de esos seis ficheros.**

**Ruff** de todos los ficheros tocados o ejercitados:

```sh
/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/ruff check \
  deploy/ops/verificador_autorizacion_ops4.py deploy/ops/registro_repeticiones_ops4.py \
  src/zascarr/services/autorizacion_actualizacion.py tests/test_ops4_autorizacion.py \
  tests/test_ops4_autorizacion_compuesta.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_registro_repeticiones.py tests/test_ops4_ui_deshabilitada.py \
  tests/test_ops4_cortes_registro.py
# All checks passed!
```

**Fallos:** ninguno en las cuatro ejecuciones ni en Ruff.

### Limitación de entorno (declarada, no ocultada)

`/tmp` es `tmpfs`; `/var/tmp`, `/` y `$HOME` están en `ext4` pero son de solo
lectura para este sandbox (`mkdir` → `EROFS`), y no hay ampliación de permiso
disponible en esta sesión. Por eso la exigencia de §11.1 «basetemp en el mismo
filesystem que `/`» **no se ha podido cumplir**. Se ejecutó dos veces
(`tmp_path` por defecto en `tmpfs` y `--basetemp` en el disco NTFS del
workspace), con el mismo resultado. La durabilidad real ante pérdida eléctrica
sigue **NOT RUN** por diseño.

## 3. Cobertura exigida por el encargo

| Requisito | Evidencia (pruebas) | Estado |
|---|---|---|
| **Rechazo sin llamar al callback** | `test_token_invalido_no_llama_al_callback`, `test_campos_estrictos_sin_consumo` (12 mutaciones, `consumos == []`), `test_claves_duplicadas_rechazadas`, `test_firma_de_otro_protocolo_o_con_otra_clave_no_verifica`, `test_id_esperado_es_obligatorio`, `test_id_esperado_liga_el_testigo_a_la_peticion`, `test_clave_o_reloj_invalidos_no_consumen`, `test_e2e_id_esperado_distinto_no_consume` (directorio vacío), `test_e2e_testigo_con_otra_clave_no_consume` | **CUBIERTO** |
| **Replay** | `test_acepta_una_vez_y_rechaza_repeticion`; `test_e2e_aceptada_una_vez_y_repetida_con_registro_durable`; `test_e2e_replay_tras_reapertura_y_purga_de_vistos` (nuevo fd + borrado de `vistos`); `test_e2e_fallo_del_registro_durable_no_acepta`; concurrencia **entre procesos** reales: 6 procesos (`test_procesos_concurrentes_solo_una_aceptacion`) y 8 procesos (`test_procesos_nuevos_no_reutilizan_la_autorizacion`); hilos como caso adicional | **CUBIERTO** |
| **`id_esperado`** | Firma del verificador lo hace obligatorio (sin él `TypeError`); `None`, cadena no-hex, mayúsculas y otro ID → `invalida` **sin consumo**; con coincidencia → `aceptada`. | **CUBIERTO** |
| **Composición con reautenticación** | `test_sin_habilitar_falla_cerrado_sin_reautenticar`, `test_la_funcion_esta_deshabilitada_por_defecto`, `test_la_puerta_es_lo_primero`, `test_confirmacion_requerida_no_reautentica`, `test_contrasena_invalida_no_reautentica`, `test_auth_mode_none_no_reautentica`, `test_auth_mode_no_soportado_falla_cerrado`, `test_cada_resultado_no_ok_deniega_sin_emitir` (INCORRECTA, OCUPADA, BLOQUEADA con `hasta_epoch`, excepción, `None`, objeto, `"ok"`), `test_orden_reauth_antes_de_emitir`, `test_con_ok_emite_una_sola_vez`, clave/ID/emisión fallidos → fallo cerrado, `test_sin_secretos_en_el_resultado` (repr/str), listas cerradas | **CUBIERTO** (con límites de §4) |
| **Prefijo durable** | `PREFIJO_AUTORIZACION="autorizacion-"` ≠ `PREFIJO_SOLICITUD_V3="solicitud-"`; `test_prefijo_propio_de_autorizacion` (marca vacía 0600, no crea la v3), `test_prefijos_distintos_no_se_satisfacen_entre_si`, `test_vistos_v3_no_satisface_ni_se_satisface_por_la_autorizacion` (purga de `vistos` no reabre), `test_el_registro_de_autorizacion_no_vive_en_run_ni_en_vistos`, `test_fallo_de_sincronizacion_en_autorizacion_no_autoriza_ni_borra`, `test_reclamador_durable_para_el_verificador`; barrer de aislamiento: el registro no se importa desde `src/`, auxiliar ni instalador | **CUBIERTO** en el módulo; ruta/owner reales **NOT RUN** |

## 4. ¿Pruebas tautológicas? Verificación por mutación

Método: mutaciones **en memoria** (plugin de pytest en el mismo proceso; no se
escribió ni se revirtió ningún fichero del repo) y ejecución de los tests que
deberían detectarlas. Las seis mutaciones de seguridad probadas **fallan** la
suite; ninguna pasa desapercibida:

| Mutación inyectada | Fallos | Test que la detecta |
|---|---|---|
| El verificador ignora `id_esperado` y toma el ID del testigo | 2 | `-k id_esperado` |
| El verificador llama al callback **antes** de validar | 13 | `-k "token_invalido or campos_estrictos"` |
| `TOLERANCIA_RELOJ_S = 10^9` | 1 | `-k limites_de_ventana` |
| `PREFIJO_AUTORIZACION = PREFIJO_SOLICITUD_V3` (colisión) | 1 | `-k prefijos_distintos` |
| La composición fuerza `Reauth.OK` para todo | 7 | `-k cada_resultado_no_ok` |
| La composición ignora la puerta `habilitada` | 6 | `-k "sin_habilitar or la_puerta_es_lo_primero"` |

Oráculo independiente del **vector canónico** (SPEC §5.4): recalculado con
`hashlib`/`hmac` sin usar el módulo, el HMAC esperado coincide con el literal
fijado en `test_vector_canonico_y_longitud` (174 bytes,
`287259e7…a441e`). Es decir, el vector no se autogenera con la implementación.

## 5. Matriz de criterios (AC-AUT)

| AC | Estado en este snapshot | Nota |
|---|---|---|
| 01 función deshabilitada | **PARCIAL**: app (`no_habilitada` sin reautenticar/emitir) y UI/auxiliar (gate vigente) PASS; shim de unidad sin llamadas **NOT RUN** | integración no existe |
| 02 cada reauth no-OK sin emisión | **PASS** | dobles para todos los resultados, excepción y valores no esperados |
| 03 una emisión con estructura/ID CSPRNG/ttl 60 | **PASS** | `secrets.token_hex(16)`, vector literal |
| 04 aceptada una vez, repetida la segunda | **PASS** | + marca creada una vez |
| 05 inválidos rechazados, callback 0 veces | **PASS** (matiz F1) | se cubre también `id_esperado` |
| 06 N procesos → una aceptación | **PASS** | subprocesos reales, no solo hilos |
| 07 namespace independiente de vistos v3 | **PASS** | cruzado en ambos sentidos |
| 08 fallo de `fsync`/creación/descriptor/ENOSPC | **PASS** en módulo | disco lleno real **NOT RUN** |
| 09 reapertura ve la marca; `/run` no se usa | **PASS** en módulo/estático | elección de ruta real pendiente |
| 10 tabla de mutaciones sin consumo | **PASS** | 12 mutaciones + firma/dominio/claves duplicadas |
| 11 otra clave / `ops.key` | **PARCIAL** | clave sustituta de 32 B y dominio ajeno; no se lee `ops.key` (estático) |
| 12 sin secretos en token/logs/estado/respuesta | **PARCIAL** | token y `repr` PASS; logs/estado/respuesta aún no existen → **NOT RUN** |
| 13 `id_esperado` ausente/distinto → inválida sin consumo | **PASS** | |
| 14 UI/auxiliar/main/unidad/instalador inertes | **PASS** | 19+4 pruebas estáticas/HTML; `UNIDADES` solo `copia`/`restaurar` |
| 15 guardas de unidad/cerrojo tras aceptar | **NOT RUN** | sin integración; fuera de fase |
| 16 envío único y resultado incierto | **NOT RUN** | no hay transporte; ver F3 |
| 17 orden puerta→validación→auth_mode→reauth→clave→emisión | **PASS** (matiz F5) | orden reauth→emisión observado |
| 18 clave ausente/enlace/modo/directorio inseguro | **PARCIAL** | `0700`/grupo escribible y clave inválida cubiertos; provisión real **NOT RUN** |
| 19 listas cerradas y paridad v1/v2 | **PASS** | enums cerrados + `test_ops_paridad.py` (10 casos) |

## 6. Hallazgos (ninguno bloqueante para esta fase)

- **F1 (menor, fuerza de prueba).** En el diff se relajó
  `test_campos_estrictos_sin_consumo` de `is INVALIDA` a
  `in (INVALIDA, CADUCADA)` ([tests/test_ops4_autorizacion.py:178](../../tests/test_ops4_autorizacion.py#L178)).
  Verificado con sonda independiente: los 12 cuerpos producen exactamente
  `invalida`; el `in` no es necesario y enmascara una regresión de clasificación
  (AC-AUT-05 pide «solo según la causa»). `test_formas_y_firmas_invalidas`
  ([…:154](../../tests/test_ops4_autorizacion.py#L154)) mantiene la misma laxitud
  (preexistente). **Recomendación:** volver a `is CodigoAutorizacion.INVALIDA`
  en ambos.
- **F2 (menor, cobertura).** Faltan casos límite baratos: contraseña de exactamente
  512 bytes aceptada (y frontera UTF-8 multibyte), firma con hex en mayúsculas o
  no-hexadecimal, cuerpo vacío (`b"." + firma`), `creada > expira`, y prueba
  directa del orden `fsync(fichero)→fsync(directorio)` para
  `reclamar_autorizacion` (hoy solo vía `reclamar_id`, que comparte
  `_reclamar_marca`). No incumplen AC; son red adicional.
- **F3 (observación).** `test_el_mismo_intento_no_se_reemite_ni_reutiliza_el_id`
  ([…compuesta:332](../../tests/test_ops4_autorizacion_compuesta.py#L332)) valida
  dos intentos **distintos** (dos emisiones con IDs distintos), no la propiedad
  que anuncia su nombre (no reemitir el mismo intento). Eso exige transporte y
  sigue **NOT RUN** (AC-AUT-16); conviene renombrar o completar al integrar.
- **F4 (observación).** Las barreras de `/run`, `ops.key` y «no lee hashes» son
  comprobaciones de texto, útiles como red, no pruebas de la ruta/owner reales.
  `_reclamar_marca` rechaza descriptor no-directorio y modo con bits de grupo/otros,
  pero **no** verifica `uid`/`gid` ni exige `0700` (el módulo delega en un
  llamador de confianza). La provisión real del directorio, retención, cuota y
  poda quedan **NOT RUN** (SPEC §7.2/§7.4).
- **F5 (observación).** El orden `puerta→(confirmación/contraseña)→auth_mode→reauth`
  está implementado y se prueba por partes; no hay un caso conjunto
  «contraseña inválida + `auth_mode=none`» que fije el orden entre validación y
  `auth_mode`. La validación de **sesión/origen** (SPEC §6.1 paso 2) no está en
  la composición: queda para el router futuro, correctamente declarada fuera de
  alcance.
- **F6 (documental).** [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md)
  dice «los 38 tests… pasan»; el fichero tiene ahora 45. Actualizar al integrar
  (no afecta al veredicto).
- **F7.** El árbol contiene documentos nuevos de otros roles (benchmark, spec,
  diseño de UI) **no revisados aquí**.

## 7. Fuera de alcance / NOT RUN (no se presenta como PASS)

Unidad/systemd instalado, root, Docker de producción, VM, Pi, socket real,
`update.sh`, shims de cerrojo/unidad (AC-AUT-15), lectura/provisión real de la
clave dedicada (Q-AUT-1), transporte v4/ENVÍO único y resultado incierto
(AC-AUT-16, Q-AUT-2), puerta `no_habilitada` del host ya integrada, búsquedas
negativas de secretos en logs/estado/respuesta (no existen aún), durabilidad
ante pérdida eléctrica, y basetemp en el mismo filesystem que `/` (limitación de
sandbox declarada en §2).

## 8. Veredicto

**APTO para la fase QA** del contrato aislado app→host: 167/167 pruebas dirigidas
en verde (191/191 con paridad/gates), Ruff limpio, sin fallos ni omisiones, y las
propiedades críticas (rechazo sin callback, replay entre procesos/reapertura,
`id_esperado`, composición reauth, prefijo durable propio) están cubiertas de
forma no tautológica (6/6 mutaciones detectadas).

**Condiciones:** (1) la actualización sigue deshabilitada y sin conectar a UI,
auxiliar, `main.py` ni unidad; (2) corregir F1 al tocar las pruebas; (3) abordar
F2/F3 y la matriz **NOT RUN** antes de integrar o habilitar; (4) este QA vale
solo para el snapshot con los sha256 de §1 — cualquier cambio invalida los
recuentos y exige repetir las pruebas dirigidas.
