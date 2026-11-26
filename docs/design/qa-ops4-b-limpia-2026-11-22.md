# QA final — OPS4/#443 historia B, SHA `3aa4ec16` (PR #1233, rama limpia) (2026-11-22)

> **Rol QA · solo lectura.** SHA auditado **`3aa4ec1646ffb97c310e16c1a4dded8ab6318c74`**,
> rama `feat/ops4-b-limpia-443`, PR **#1233** (draft, base `main`). Worktree
> `.worktrees/ops4-b-limpia`; árbol limpio al iniciar (`git status --porcelain` vacío) y
> sin commits nuevos de esta QA. Esta QA **no ejecutó localmente** Pi, Docker real,
> PostgreSQL real, systemd del host, `update.sh`, el instalador sobre un host real ni
> despliegue alguno. **No se ejecutó
> la suite completa en esta sesión** (la ejecutó CI, §2); no se tocó código. El único
> fichero escrito es este informe. **No autoriza habilitar ni desplegar**;
> la fusión apagada la decide el PO con este informe y la revisión SecOps.

---

## 1. Veredicto

| Cuestión | Veredicto |
|---|---|
| **Fusionar apagado** (esta PR, bandera `false`) | **GO con condiciones C1–C5.** No hay defecto de ejecución con los valores por defecto ni P0/P1 de habilitación alcanzable; CI del *merge ref* en Python 3.11 **completa verde** (suite, PostgreSQL real, ruff y builds) y 0 fallos. Las condiciones son de alcance, documentación, pruebas estáticas y dictamen; ninguna cambia comportamiento. |
| Declarar cerrada la **Parte A** (CA-A-01…15 / §6.2) | **NO-GO en este SHA** mientras C1–C5 sigan abiertas: el árbol conserva un módulo muerto que A3 manda retirar, la documentación contradice al SHA, faltan TA-09 y la prueba de cierre de imports y la limpieza retiró la suite dedicada del registro durable (27 casos) sin sustituto completo (§4, H1–H3/H7). |
| **Habilitar** (bandera `true`, socket/unidad, `update.sh` real) | **NO-GO absoluto.** B1–B10, CE-1…CE-12 e I-1…I-9 no están implementadas/validadas; hay además huecos de UI de la ruta encendida (§4, H6). No alcanzable con el valor por defecto. |
| **Despliegue** | **No autorizado.** Sin cambios de política (spec §7.1): nada de `.env`/Compose desplegado, `--activar`, Pi ni clave de producción. |

---

## 2. Evidencia ejecutada

Entorno local: venv de pruebas del repo, **Python 3.14.4**, pytest 9.2.0, ruff 0.17.5,
`PYTHONPATH=.:src`, sin `TEST_DATABASE_URL`, sin Docker ni systemd. SHA y base:
`git rev-parse HEAD` = `3aa4ec16…`; padre `2c773e53`; `origin/main`/GitHub `main` =
`9fe0be06` (12 commits por detrás, merge-base `2c773e53`); PR #1233 **draft**,
`mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`.

| Comprobación | Resultado |
|---|---|
| Selección documentada OPS4/instalador: `pytest -q tests/test_ops4_*.py tests/test_instalar_ops4.py` | **364 recogidas, 364 passed, 0 failed** (19,15 s) |
| Bloque UI + estado + escritor + instalador + unidades + auxiliar + aislamiento (168 recogidas) | **168 passed, 0 failed** (12,70 s) |
| Bloques relacionados no OPS4: `test_aviso_version.py`, `test_compose_env.py`, `test_env_consumidores.py`, `test_estado_puntos.py`, `test_estado_copia_fallida.py`, `test_web_estado_cortesia.py`, `test_auth.py`, `test_web_auth.py`, `test_auth_hx_redirect.py`, `test_config_crawl_delay.py`, `test_config_disco.py` | **182 passed, 0 failed** (40,21 s) |
| Tests de temporización estabilizados en la PR: `test_lector_rar.py`, `test_ensayo_f1bis_arnes.py` | **123 passed, 1 skipped, 0 failed** (80,60 s) |
| Recuento de la suite completa (solo `--collect-only`, sin ejecutar) | **11376 recogidas** = 8922 + 2454, exactamente las cifras de la PR |
| Ruff: `ruff check src/ deploy/ops/ tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ensayo_f1bis_arnes.py tests/test_lector_rar.py` y `ruff check --select S src/` | **All checks passed!** |
| Ruff `--select S deploy/ops/` (fuera del CI, que solo escanea `src/`) | 2 hallazgos preexistentes en el auxiliar (S603/S607 de `subprocess.run(["systemctl", …])`, argv y `PATH` fijos); no es superficie de la app |
| Sonda de entrypoints instalados: instalación en layout de producción y `python3 -I` | Finalizador sin estado ⇒ `0` sin crear nada; auxiliar con stdin vacío ⇒ `{"v":4,…,"resultado":"rechazada","codigo":"no_disponible"}` y `0` |
| CI de la PR, run [45039419879](https://github.com/juanajok/zascarr/actions/runs/45039419879), sobre el **merge ref** `1cf92de` (`3aa4ec16` + `9fe0be06`), Python 3.11 | **Suite unitaria: SUCCESS — 9034 passed, 2345 skipped, 1 xfailed, 8 warnings, 0 failed (428,10 s)**; **Pruebas con Postgres real: SUCCESS — 2542 passed, 0 failed, 0 skipped (1337,89 s)**; `ruff`, build amd64 y build ARM64: SUCCESS. `mergeStateStatus: CLEAN` |

**Coherencia de cifras.** La colección local da 11376 = 8922 + 2454, la aritmética exacta
de la PR. CI ejecutó el árbol fusionado en Python 3.11 y da **0 failed** con más pruebas
efectivas (2345 skipped frente a 2454, por `unar`/Docker presentes en el runner); la
diferencia de recuento es de entorno, no de resultado. Por tanto la suite reportada queda
**acreditada por CI**, no solo proyectada; esta QA no la repite.

**Desglose de las 364** (la selección es coherente con OPS4/instalador; no hay ficheros
ajenos): UI 18 (`test_ops4_ui_actualizacion` 9, `ui_deshabilitada` 4, `ui_gate` 5), estado
host+app 109 (`estado_actualizacion` 32, `estado_final_unidad` 36, `escritor_estado` 41),
instalador+unidades 18 (11+7), auxiliar+aislamiento 23 (18+5) y autorización/protocolo/
solicitud/transporte 196 (49+59+21+21+17+29). **15 de esas 364 ejercitan un módulo que no se
instala** (§4, H1). El registro durable —módulo **sí instalado** y que decide el consumo de
un solo uso— perdió su suite dedicada (`test_ops4_registro_repeticiones.py`, 27 casos en la
rama anterior); aquí solo tiene cobertura indirecta (≈9 casos E2E en
`test_ops4_autorizacion_compuesta.py`, 1 en `test_ops4_protocolo_v4.py` y 1 en la UI), sin
los casos de `fsync`/rename/descriptor/directorio inseguro/disco lleno (H7).

---

## 3. No se ha colado habilitación

- Bandera **`false`** por defecto en `config.py:285-286` y en Compose
  (`docker-compose.yml:164`: `${OPS4_ACTUALIZACION_HABILITADA:-false}`); no aparece en
  `.env.example` ni se escribe en ningún script. Para encenderla hace falta una decisión
  explícita de root en el `.env`.
- `POST /ui/actualizar` comprueba la bandera **antes** de leer la clave, reautenticar o
  tocar el socket y devuelve **404** (`src/zascarr/web/actualizacion.py:79-81`); probado con
  la ruta real (`tests/test_ops4_ui_actualizacion.py:28-39`, `test_ops4_ui_gate.py:88-93`).
- `/estado` solo pinta el botón deshabilitado y el texto «no está disponible» con la bandera
  apagada (`estado.html:28-29`); el test exige **cero** `form`/`a`/`script`/`hx-*`/`on*` y
  un único `button disabled` (`test_ops4_ui_deshabilitada.py:40-76`).
- Unidades **sin `[Install]`** (solo el comentario en `zascarr-actualizar.service:40` y
  `…socket:16`), sin `ExecStartPost` y con **un** `ExecStopPost` con prefijo `-`
  (`…service:13-18`). El instalador **no** usa `systemctl enable`; `--activar` solo hace
  `systemctl start` **no persistente** del socket (`scripts/instalar_actualizacion_ops4.sh:157-164`).
- Sin migración Alembic nueva (`git diff origin/main...HEAD -- alembic/` vacío); sin cambios
  en `update.sh`, `_cerrojo.sh` ni `instalar_ops.sh`; `src/zascarr` no importa `deploy.ops`;
  `OPS4_*` no reutiliza clave/socket de copia/restauración. La app ve `/run/zascarr-ops`
  montado `ro` (`docker-compose.yml:217`) y no escribe estado.
- Sin `.env`, claves ni sockets versionados; el diff solo añade los ficheros esperados
  (58 ficheros, +8295/−8) y no toca `services/seguridad.py`, `web/ajustes.py` ni
  `services/reautenticacion.py`.

---

## 4. Hallazgos

**H1 — P2 · Módulo muerto residual que A3 manda retirar (CA-A-08).**
`deploy/ops/admision_v4_actualizar_ops4.py` sigue en el árbol. La spec de cierre lo retira
expresamente («el auxiliar no la importa», `especificacion-ops4-cierre.md:319-322`); el
instalador no lo copia (`instalar_actualizacion_ops4.sh:145-151`) y el auxiliar no lo importa
(implementa la misma secuencia en `zascarr_actualizar_aux.py:88-148`). Solo lo usan tests:
`test_ops4_protocolo_v4.py:11` (13 de sus 21 casos recogidos), `test_ops4_transporte_v4.py:11`
y el E2E de UI `test_ops4_ui_actualizacion.py:114-192` (este simula el host con `admitir_v4`,
no con `procesar` del auxiliar). `test_ops4_aislamiento.py:7-21` no lo incluye en `MUERTOS`, así
que la barrera no lo detecta. Efecto: parte de las 364 acredita código que nunca se instala
y el E2E no recorre el código privilegiado real; no hay ruta alcanzable con la bandera
apagada. Además, `registro_repeticiones_ops4.py:118-133` conserva la función v3
`reclamar_id`/`PREFIJO_SOLICITUD_V3`, sin llamadores (el módulo sí se instala y se usa para
el namespace `autorizacion-`). La afirmación de la PR «sin el protocolo v3» es cierta para
los módulos retirados, no para este resto.

**H2 — P2 · La documentación no cuenta la verdad del SHA (A5 / CA-A-10).**
Quedan cifras y frases de árboles anteriores: `ops4-ui-integracion.md:35` y
`ops4-auxiliar-unidad.md:46` («916 pruebas / suite 8906/2431»), `ops4-solicitud-v4.md:30`
(«892 / 8882/2431»), `ops4-autorizacion-app-host.md:93` («791 / 8880/2431») y, en el mismo
párrafo `:96-97`, «el contrato permanece sin importar desde web, API, main ni el auxiliar»
(falso: la ruta web usa el servicio). `ops4-protocolo-v4.md:41-42` mantiene «853 pruebas» y
«No hay socket, ruta web, auxiliar ni unidad»; `ops4-transporte-v4.md:4,29,34` dice «No está
conectado… no existe una unidad» y «874». `ops4-matriz-evidencia.md:33-65` enlaza **24
tests que ya no existen** y varios documentos retirados; ADR 0026:51 enlaza un informe
SecOps no presente. Docstrings de módulos también desactualizados: «no instalado ni
conectado» (`registro_repeticiones_ops4.py:1`), «no está conectado al auxiliar»
(`verificador_autorizacion_ops4.py:12`), «No se instala» (`zascarr_actualizar_aux.py:7`),
«no está conectada» (`clave_autorizacion.py:1`), «no hay escritor»
(`services/estado_actualizacion.py:3`) o «nada de aquí se importa desde web…»
(`services/autorizacion_actualizacion.py:26-28`). Efecto: sin efecto de ejecución, pero
A5/CA-A-10 sigue abierta y el SHA no es autodescriptivo.

**H3 — P2 · Faltan pruebas estáticas obligatorias (CA-A-06 / §6.2).**
No existe `tests/test_ops4_alcance_apagado.py` (TA-09): el default `false` de config y
Compose, la ausencia de migración y la ausencia de `.env` de producción no están
automatizados (los he comprobado a mano, §3). Tampoco hay prueba de **cierre transitivo de
imports** (CA-A-06): `test_instalar_ops4.py:44-49` comprueba auxiliar, finalizador y solo
tres módulos (protocolo, verificador, registro), pero **no** `escritor_estado_actualizar_ops4.py`,
que el instalador sí copia (`instalar_actualizacion_ops4.sh:148-151`) y el auxiliar importa.
Si desapareciera de la lista, ningún test lo detectaría; mi sonda de layout de producción
(§2) confirma que hoy funciona, pero no es una garantía automática.

**H4 — P2 · Falta la nota de desviación de Compose/.env (A4 / CA-A-09).**
Ni ADR 0026 ni `ops4-ui-integracion.md` advierten de que el `.env` de root puede encender la
UI y de que encenderla es una decisión de habilitación con puertas (§7), como pedía A4;
tampoco hay prueba estática de los defaults. Sin efecto con el valor por defecto (`false`).

**H5 — P2 · No consta dictamen SecOps del SHA que se fusiona (A6 / CA-A-11).**
No hay informe SecOps/QA/UI-UX de `3aa4ec16` en el árbol ni en la PR (sin comentarios ni
reviews); los documentos arrastrados citan dictámenes de SHAs anteriores de la rama apilada
(`87b87a34`, `9e97aa9f`, `48526e03`), que no están versionados aquí. La PR invoca «Parte A
sin P0» sin enlace al dictamen del SHA final. La regla de CLAUDE.md §5.8 **no** se dispara
(el diff no toca `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py`),
pero A6 sigue siendo preceptiva. Efecto: es la condición formal que falta para el «cierre A».

**H6 — P1 solo si se enciende · La ruta encendida está sin probar y con copy incoherente.**
Con bandera `true` nadie renderiza `/estado`: no hay test del formulario con
`auth_mode=password` ni del aviso con `auth_mode="none"` (`estado.html:15-27`), ni del
`_aviso_version.html` condicional. El JS `pollVersion` sigue inyectando «Esta página solo
informa; no instala nada» (`estado.html:319`) y pisaría el copy de la plantilla cuando la
función esté encendida; con `auth none` el aviso dice «Puedes actualizar desde el
formulario» aunque no se pinta formulario; el resultado `hecha` sigue mostrando como aviso
principal «Solicitud aceptada…» (P1-2 parcial). **No alcanzable con `false`**, pero bloquea
habilitar. Positivo: el defecto QA-1 de la ronda anterior está corregido y probado —el
estado solo se lee si el resultado es `ACEPTADA` (`web/actualizacion.py:105-108`) y existe
`test_ocupada_no_se_convierte_en_incierta_por_leer_estado`
(`test_ops4_ui_actualizacion.py:256-278`)— igual que «Volver a Estado» (P1-1).

**H7 — P2 · Cobertura perdida de un control de seguridad (registro durable).**
El SHA limpia retiró `tests/test_ops4_registro_repeticiones.py` (27 casos; 409 líneas), pero
conserva e instala `deploy/ops/registro_repeticiones_ops4.py`, que es el consumo durable de
un solo uso del que depende la autorización. Quedan los flujos principales cubiertos de
forma indirecta (aceptación/repetida, ID distinto, otra clave, replay tras reapertura, fallo
del registro, concurrencia: `test_ops4_autorizacion_compuesta.py`; 1 E2E en
`test_ops4_protocolo_v4.py::test_v4_con_consumo_durable_real`), pero se pierden los casos
dedicados de fallo de `fsync`/rename, disco lleno, directorio escribible por grupo,
descriptor inválido, colisión de nombres y separación de namespaces v3/autorización. La
barrera `test_ops4_aislamiento.py` pasó de 24 a 5 casos (los retirados eran, en parte, de
módulos eliminados; la pérdida es legítima solo en esa parte). No es un defecto de ejecución
con la bandera apagada, pero es una red de regresión de seguridad que la PR no debe perder
sin sustitución o aceptación explícita (CA-A-06/A2).

---

## 5. Condiciones

**Para fusionar apagado (GO pleno; C1–C5 son baratas y no cambian comportamiento):**

1. **C1 (CA-A-08):** retirar `deploy/ops/admision_v4_actualizar_ops4.py` y adaptar los tests
   que lo importan (protocolo/transporte/UI) y `test_ops4_aislamiento.py`; o, si el PO decide
   conservarlo, dejarlo escrito en la PR con el motivo. Retirar o justificar `reclamar_id`
   (v3) del registro instalado.
2. **C2 (CA-A-10):** actualizar cifras, frases y enlaces al SHA real en los documentos de
   H2, y los docstrings de módulos; arreglar el enlace roto de ADR 0026. Los recuentos
   vigentes son **364** y **8922/2454** en local / **CI: 9034/2345/1 xfail, 0 failed**.
3. **C3 (CA-A-06/§6.2):** añadir `tests/test_ops4_alcance_apagado.py` (TA-09), una prueba
   de cierre transitivo de imports que compare lo que copia el instalador con lo que importan
   el auxiliar y el finalizador (incluido `escritor_estado_actualizar_ops4.py`) y reponer o
   portar la suite dedicada del registro durable (`test_ops4_registro_repeticiones.py`,
   H7), o dejar por escrito la aceptación del PO de esa pérdida de cobertura.
4. **C4 (CA-A-09):** añadir la nota de desviación de Compose/.env en ADR 0026 y en
   `ops4-ui-integracion.md`, con prueba estática de default `false`.
5. **C5 (CA-A-11 y CI):** dictamen SecOps del SHA `3aa4ec16` (o constancia firmada de que no
   se dispara §5.8 y de por qué se acepta) y marcar la PR «ready». La CI del merge ref ya
   está verde (incluido PostgreSQL real); si `main` vuelve a avanzar, repetir CI sobre el
   nuevo merge ref. Sin habilitar `.env`/Compose; nada de `--activar`, Pi ni despliegue.

**No fusionar como habilitado ni desplegar en el mismo acto.** El mensaje de merge y la
documentación deben decir «integrada, apagada por defecto; habilitar exige B1–B10, CE,
revisión SecOps y autorización expresa».

**Para habilitar (NO-GO absoluto):** B1–B10 implementadas y verificadas, CE-1…CE-12 e
I-1…I-9 resueltas/declaradas, B4 (host aislado con `update.sh` real, Docker/PostgreSQL y
systemd desechables) y B5/B6, migración de estado 1→2 y reconciliación, reserva atómica del
cerrojo, sandbox/refresco, UI de último intento (B7) y **C6**: cerrar H6 y los P1 de UI/UX,
probar la ruta encendida (formulario, `auth none`, `pollVersion`) y contar con dictamen
SecOps del SHA final, runbook y autorización expresa del PO. Nada de esto se autoriza aquí.

---

## 6. NOT RUN (declarado, no PASS)

- Suite completa y **Python 3.11** en local: **no ejecutadas por esta QA** (la tarea lo
  prohíbe; CI las ejecutó sobre el merge ref y dieron 0 fallos, §2). Python 3.11 local no
  probado.
- PostgreSQL real **local** (contenedor propio): no ejecutado por esta QA; el job de CI
  «Pruebas con Postgres real» sí lo acreditó en el merge ref (2542 passed, 0 failed).
- `systemd-analyze verify`; systemd del host; socket/unidad reales; instalador sobre host
  real o Pi (con y sin `--activar`); `update.sh` real; Pi; navegador real y anchos
  1280/375; lector de pantalla; cualquier despliegue, provisión de clave o cambio de
  `.env`/Compose desplegado.
- Dictamen SecOps/QA/UI-UX del SHA `3aa4ec16`: **no consta** (§4, H5).
- Medición de cobertura (`coverage`): no ejecutada.

**Gestión:** único fichero escrito por esta QA: este. No se modificó código ni se ejecutó
nada del host. Este informe no concede GO de habilitación ni de despliegue; el GO de
fusión apagada queda condicionado a C1–C5 y a la decisión del PO.

**Nota de cierre (worktree compartido).** Todas las ejecuciones de esta QA se hicieron con el
árbol limpio del SHA `3aa4ec16`. Al terminar la sesión aparecieron en el worktree cambios
**no rastreados de otros roles**, ajenos al SHA auditado: `M tests/test_ops4_aislamiento.py`
(3 barreras nuevas), `?? tests/test_ops4_registro_repeticiones.py` y
`?? docs/design/secops-ops4-b-limpia-2026-11-22.md` (16:52). Si se integran en la PR, el SHA
cambia y A6/CA-A-13 exigen revalidar árbol limpio, CI y dictamen del SHA nuevo; este informe
no los cubre.
