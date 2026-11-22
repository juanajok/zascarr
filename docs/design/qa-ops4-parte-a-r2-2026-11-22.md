# QA acotado — Parte A de OPS4/#443 sobre `48526e03` (2026-11-22)

> **Rol QA · solo lectura.** SHA auditado: **`48526e036d0fefb91a3f5b02280e5d3e0bbe3b7f`**
> («fix(ops): cerrar P1 de UI-UX de OPS4 (#443)»), rama `feat/ops4-seguridad-443`,
> árbol limpio al iniciar. No se ha editado código, config, unidades ni instalador; no se
> ha ejecutado Pi, Docker real, PostgreSQL real, systemd del host, `update.sh`, el
> instalador ni despliegue alguno. **Este informe no autoriza fusionar, habilitar ni
> desplegar**; decide el PO con la revisión SecOps del SHA final. El único fichero escrito
> por esta QA es este.

## 1. Veredicto

| Cuestión | Veredicto | Base |
|---|---|---|
| ¿La fusión enciende algo? | **No** — GO de seguridad del apagado | Bandera `False` por defecto (config y Compose), `POST /ui/actualizar` → 404 antes de leer clave, unidades sin `[Install]`, instalador sin `enable`, suite dirigida verde (§2). |
| Fusionar como «cierre A» del contrato | **NO-GO en este SHA** | CA-A-07, CA-A-08, CA-A-10, CA-A-11 y CA-A-12 no están cerradas; CA-A-06 y CA-A-09 solo en parte (§3). La propia revisión declara pendientes el rebase, los módulos muertos y los recuentos de la fase A. |
| Habilitar la función | **NO-GO (absoluto)** | Todo B1–B10 sigue sin implementar/validar y hay un defecto nuevo de UI con la bandera encendida (§7, QA-1). |
| Despliegue | **No autorizado** | Sin cambios de política (spec A8/§7.1). |

## 2. Evidencia ejecutada

Entorno: venv de pruebas del repo, **Python 3.14.4**, pytest 9.2.0, ruff 0.17.5;
`PYTHONPATH=.:src`; sin `TEST_DATABASE_URL`, sin Docker, sin systemd. Comandos y resultados
de esta sesión:

| Comprobación | Resultado |
|---|---|
| `pytest tests/test_ops4_*.py tests/test_instalar_ops4.py` (comando que cita la revisión) | **994 passed, 0 failed** |
| `pytest` + `tests/test_ops_paridad.py tests/test_c6_o1_paridad_pg.py tests/test_paridad_de_entradas_pg.py` (selección real de las 1004) | **1011 recogidas: 1004 passed, 7 skipped, 0 failed** (los 7, PostgreSQL opt-in) |
| Grupo TDD «unidad, estado final, auxiliar, escritor, instalador, lector app» | **145 passed, 0 failed** (coincide con la revisión) |
| UI OPS4: `test_ops4_ui_actualizacion.py test_ops4_ui_deshabilitada.py test_ops4_ui_gate.py test_ops4_estado_actualizacion.py` | **49 passed, 0 failed** |
| `test_aviso_version.py test_web_componentes.py test_estado_puntos.py test_web.py` | **193 passed, 0 failed** |
| `ruff check src/` y `ruff check --select S src/` | **All checks passed** |
| Ruff de los ficheros tocados (deploy/ops, tests, `web/actualizacion.py`) | **All checks passed** |
| `git status --porcelain` al iniciar | vacío; HEAD `48526e03`; `git diff` vacío |
| `pytest --collect-only` de toda la suite (solo recuento, sin ejecutar) | **11426 tests recogidos** |

Durante la sesión apareció en el árbol un documento **no rastreado de otro rol**
(`docs/design/secops-ops4-parte-a-r2-2026-11-22.md`), ajeno a esta QA. El árbol limpio que
exige A6/CA-A-13 debe revalidarse al fijar el SHA final.

## 3. Trazabilidad CA-A (spec §3) → tests/evidencia en `48526e03`

| CA | Estado | Evidencia / hueco |
|---|---|---|
| CA-A-01 | **Cumple** | `tests/test_ops4_unidades.py:38-60` (sin `ExecStartPost`, un `ExecStopPost` con `-` y las 3 variables, sin `[Install]`); `tests/test_instalar_ops4.py:149` (unidad instalada). |
| CA-A-02 | **Cumple** | `tests/test_ops4_estado_final_unidad.py:83-217`: tabla pura + ejecución de la cadena real (`success`, `75`, `1`, `timeout`, `signal`, `killed`), sin estado, terminal, reloj invertido. |
| CA-A-03 | **Cumple** | Misma cadena + `tests/test_ops4_escritor_estado.py` (monotonía, `id`/`inicio_epoch`, `actualizado_epoch`, fsync/rename). |
| CA-A-04 | **Cumple** | `test_ops4_estado_final_unidad.py:202-209` (fallo durable ⇒ 1; prefijo `-` en la cadena) y `:149` (sin estado ⇒ 0). |
| CA-A-05 | **Cumple** | `tests/test_ops4_auxiliar.py:182-264`: escritura solo antes del `start`, carrera T-17 con terminal síncrono (éxito y fallo del start). |
| CA-A-06 | **Parcial** | El instalador sí copia `escritor_estado_actualizar_ops4.py` (`scripts/instalar_actualizacion_ops4.sh:126,149`) y el cierre manual de imports cuadra, pero **no existe la prueba de cierre transitivo** que pide la CA; `test_instalar_ops4.py:37-64` solo comprueba 3 módulos (no el escritor nuevo). |
| CA-A-07 | **No cumple** | Rama sin rebasar: **105 commits delante / 129 detrás** de `origin/main` (`ab33c147`), merge-base `61f4d53a`; diff **129 ficheros, +19239/−24**. La revisión lo declara pendiente. |
| CA-A-08 | **No cumple** | Siguen en el árbol los módulos retirados por A3: 15 en `deploy/ops/` (`admision_*`, `ejecutor_*`, `experimento_*`, `modelo_aprobacion`, `modelo_fases`, `protocolo_actualizar_ops4`, `lector_credenciales`, `limite_intentos`, `prueba_viva`, `validar_inventario`) y 3 en `src/zascarr/services/` (`actualizacion_transporte.py`, `solicitud_actualizacion.py`, `ops_actualizacion_protocolo.py`). |
| CA-A-09 | **Parcial** | Default `false` confirmado en `config.py:280-285` y `docker-compose.yml:163-167`, pero **no** hay la nota de desviación en ADR 0026/`ops4-ui-integracion.md` (el ADR no tiene sección de desviaciones de despliegue) ni prueba estática de los defaults; `tests/test_ops4_alcance_apagado.py` (TA-09) no existe. |
| CA-A-10 | **No cumple** | Quedan textos y cifras obsoletos: `ops4-protocolo-v4.md:41-42` («no hay socket, ruta web, auxiliar ni unidad», 853 pruebas); `ops4-transporte-v4.md:34` («no hay ruta UI ni unidad»); `ops4-verificacion-contrasena.md:53` («todavía sin conectar»); `ops4-autorizacion-app-host.md:93` (791/8880); `ops4-ui-integracion.md:35` (916/8906); `ops4-validacion-suite-2026-11-20.md:118` (892). |
| CA-A-11 | **No cumple** | Último dictamen SecOps: `9e97aa9f` (`secops-ops4-verificacion-final-2026-11-21.md:7`). Después hay **7 commits**, 5 de código (`4c07e49e`, `9646aaec`, `07161e2a`, `5d775319`, `48526e03`); no hay dictamen del SHA que se fusionaría. El diff de la rama frente a main no toca `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py`, así que no se dispara la regla específica de CLAUDE.md §5.8, pero A6 sigue siendo preceptiva. |
| CA-A-12 | **Parcial** | Dirigidos y Ruff verdes (§2). **Suite completa en este SHA: no ejecutada** (NOT RUN); no consta ejecución en Python 3.11; `systemd-analyze verify` NOT RUN. La cifra 8995/2431 no es evidencia de ejecución (§5). |
| CA-A-13 | **Cumple en lo declarado** | No se ha ejecutado instalador/`--activar`/`update.sh`/Pi/Docker/systemd ni desplegado. `git status` estaba vacío al iniciar (matiz del documento ajeno en §2). |
| CA-A-14 | **Cumple** | `git diff` frente a merge-base sin cambios en `alembic/versions/`; esquema del fichero de estado 1 (sin `schema: 2`). |
| CA-A-15 | **Parcial** | La revisión declara «integrada, apagada por defecto» y B no implementado, pero no registra SHA final, ni rol de las cifras, ni las CA abiertas de este informe. |

**Tests obligatorios TA (§6.2):** TA-01/02/03/04/05/07/08/10 con cobertura real (los
ficheros existen y pasan); **TA-06** existe pero aún asume que los módulos retirados
existen; **TA-09 no existe** (hueco de la batería estática de alcance apagado).

## 4. Tests TDD de estado/unidad/auxiliar/UIUX — calidad

- **Estado/finalizador:** buenos. Tabla pura + **ejecución de la cadena real** de
  `ExecStopPost` sustituyendo solo la ruta del programa, sin systemd.
- **Escritor/permisos:** buenos. `0640`, dueño por grupo del directorio, lector estricto
  (enlaces, directorios, JSON inválido, escritura ajena), fsync/rename y monotonía.
- **Auxiliar:** buenos. Orden de admisión, no consumir en cerrojo ocupado, y T-17 con
  callbacks reales (terminal síncrono antes de volver).
- **UIUX:** **insuficientes para lo que dice cerrar el commit** (§7). El commit
  `48526e03` titula «cerrar P1 de UI-UX» pero solo añade **una** prueba (`fallida`) y no
  cubre `incierta` desde fichero, `auth_mode="none"`, el aviso de versión condicional ni
  el caso `OCUPADA`.
- «TDD: primero el test, luego el código» **no es verificable** desde el historial: cada
  commit trae test y código juntos.

## 5. Coherencia de cifras

- **Selección 1004: reproducible, pero mal documentada.** Con la selección que incluye
  paridad (`tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ops_paridad.py
  tests/test_c6_o1_paridad_pg.py tests/test_paridad_de_entradas_pg.py`) salen **1004
  passed y 7 skipped** en este SHA. La línea que cita `tests/test_ops4_*.py
  tests/test_instalar_ops4.py` da **994**, no 1004 (`ops4-revision-pr1159-2026-11-21.md:142`);
  la cabecera «OPS4/paridad/instalador: 1004» sí es correcta **si se incluye paridad**, y
  omite los 7 omitidos. Hay que corregir la línea o explicitar la selección y los skips.
- **Suite completa 8995/2431: aritméticamente coherente, sin evidencia de ejecución en el
  SHA.** La colección del árbol da exactamente **11426** tests y 11426 = 8995 + 2431; pero:
  - el [registro canónico de suite](ops4-validacion-suite-2026-11-20.md) se queda en
    **8882 passed, 2431 skipped** (y en su §final aún dice «892 pruebas OPS4/paridad»,
    contradiciendo el 1004 del mismo documento, línea 89);
  - `ops4-matriz-evidencia.md:11` afirma que «la repetición completa terminó en 8995 …
    7 avisos», y la misma revisión, en su evidencia de sesión, declara **NOT RUN: suite
    completa** (`ops4-revision-pr1159-2026-11-21.md:147-148`).
  - El salto 8994→8995 coincide exactamente con el test añadido por HEAD: la cifra es
    compatible con una proyección (recogidos − omitidos) y **no se puede distinguir de una
    ejecución** sin el log. **En esta QA la suite completa es NOT RUN** y CA-A-12/A7 no se
    puede dar por cumplida con «la suite pasó en otro SHA».
- **Cifras stale cruzadas:** 853 (`ops4-protocolo-v4`), 791/8880
  (`ops4-autorizacion-app-host`), 892/8882 (`ops4-solicitud-v4`), 916/8906
  (`ops4-ui-integracion`), 892 vs 1004 en el mismo documento de validación. A5 sigue
  abierta.

## 6. ¿Se ha colado Parte B?

**No se ha colado funcionalidad de habilitación.** Verificado en el diff
`07161e2a..HEAD` y en el código:

- Esquema del fichero de estado sigue siendo **1**; sin `fase`, `head0`, `sha_destino`,
  reconciliación ni reserva atómica (`deploy/ops/escritor_estado_actualizar_ops4.py:38,188`;
  `src/zascarr/services/estado_actualizacion.py:32,129`). El lector rechaza `schema: 2`.
- Sin migración Alembic, sin cambios en `update.sh`, `docker-compose.yml` ni `.env` en los
  commits de cierre; protocolo v4 intacto; `/ui/estado` no muestra el último intento (B7).
- La revisión declara expresamente «no fases, no HEAD0/S, no reconciliación, no vista en
  `/ui/estado`», y el código coincide.
- **Matiz de alcance:** el cierre incluye **H-5 (estado `0640`/chown)**, que la spec §2.2
  asigna a **B1**, y la guarda de monotonía, que la spec admite en A1. H-5 no enciende
  nada y está probado; debe registrarse como elemento de B adelantado, no como «A
  completo».
- **Deriva de numeración:** benchmark A1–A8, spec A1–A10 y «Cierre A (A1–A6)» de la
  revisión no significan lo mismo (la revisión manda a A7–A10 del pipeline lo que en la
  spec son A2/A3/A5/A6). Dificulta la trazabilidad; conviene fijar un solo mapa.

## 7. UI corregida por `48526e03`: comportamiento y cobertura

Comprobado además con render en memoria (TestClient / llamada directa a la ruta, sin
host):

| Punto | Comportamiento en `48526e03` | ¿Prueba automática? |
|---|---|---|
| P1-1 `href /estado` | **Corregido** (`actualizacion_resultado.html:7`; `GET /ui/estado` ya no se usa desde el resultado) | **Sí** — `tests/test_ops4_ui_actualizacion.py:222-252` comprueba `href="/estado"` |
| `fallida` sin verde de éxito | **Corregido**: aviso `warn`/`role="alert"` con «La actualización no terminó bien…» | **Sí, débil** — se comprueba el texto, no el tipo/rol ni la ausencia de `aviso ok` (`:222-252`) |
| `incierta` leída del fichero | **Corregido**: `warn`/`alert` y «No vuelvas a intentarlo…» (`actualizacion.py:117-121`) | **No** — solo se prueba la `INCIERTA` del servicio, con la respuesta simple de tests (`:99-111`) |
| `auth_mode="none"` con bandera encendida | **Corregido en comportamiento**: no se pinta formulario; aviso con enlace `/ui/ajustes` (`estado.html:15-27`) | **No** — ningún test renderiza `/estado` con bandera `true` y auth `none` |
| Aviso de versión condicional (P1-6) | **Parcial**: plantilla condicionada (`_aviso_version.html:2`), pero `pollVersion` sigue inyectando «Esta página solo informa; no instala nada» (`estado.html:319`) y lo pisaría cada sondeo; con auth `none` el aviso dice «Puedes actualizar…» aunque no hay formulario | **No** |
| P1-2 mensaje del estado final | **Parcial**: para `hecha` sigue pintándose como aviso principal «Solicitud aceptada. La actualización se está preparando.» y el resultado real va en `.caption` | **No** |
| P1-3 no reintento | **Parcial**: texto en la página de resultado; `/estado` sigue ofreciendo el formulario sin aviso persistente (eso es B1.6/B7) | **No** (solo texto de `INCIERTA` del servicio) |
| P2-1 «aún» | **Corregido** (`estado.html:28`) | **Sí** — `test_ops4_ui_deshabilitada.py:66` actualizado |

**QA-1 (nuevo, P1, bloquea habilitar — no la fusión apagada).** El override de
`INCIERTA` se aplica a **cualquier** respuesta con `id` cuando el fichero no existe o es
de otro intento: `actualizacion.py:105-121` lee con `id_esperado=resultado.id` y
`estado_actualizacion.py:129` devuelve `INCIERTA` ante un `id` distinto (y también si el
fichero falta). Como el servicio devuelve `id` también en rechazos de transporte
(`solicitud_actualizacion_v4.py:130`; `OCUPADA` en `actualizacion_transporte_v4.py:123`),
una segunda solicitud mientras hay otra operación en curso muestra **«No se pudo confirmar
el resultado. No vuelvas a intentarlo…»** en vez de «Hay otra comprobación en curso; espera
un momento». Reproducido en esta QA con estado de otro `id`: el mensaje correcto
desaparece. Corrección propuesta: dejar que el fichero mande solo cuando el resultado de la
solicitud sea `ACEPTADA` (o `INCIERTA`) y añadir pruebas de `OCUPADA` con fichero
ausente/de otro intento. Hueco de prueba: ningún test lo cubre.

## 8. Hallazgos priorizados

| ID | Nivel | Hallazgo | Efecto |
|---|---|---|---|
| QA-1 | **P1** | `OCUPADA`/rechazos con `id` se pintan como `INCIERTA` «no reintentar» (§7) | Bloquea habilitar; no alcanzable con bandera `false` |
| QA-2 | **P1** | Cifra de suite completa 8995 presentada como ejecutada sin registro; `NOT RUN` en la propia revisión; 1004 mal documentada (§5) | Bloquea fusión por CA-A-12/A7; corregir o repetir suite en el SHA final |
| QA-3 | **P1** | A5 incompleta: textos «sin conectar/no hay unidad» y cifras stale en varios docs (§3) | Bloquea fusión por CA-A-10 |
| QA-4 | **P1** | A2/A3 sin hacer: rama apilada (129 ficheros) y módulos muertos/protocolo v3 presentes | Bloquea fusión por CA-A-07/08 (o aceptación explícita del PO) |
| QA-5 | **P1** | Sin dictamen SecOps del SHA final (`9e97aa9f` + 7 commits) | Bloquea fusión por CA-A-11 |
| QA-6 | **P2/CA** | Sin TA-09 (`test_ops4_alcance_apagado.py`), sin prueba de cierre de imports (CA-A-06) y sin nota de desviación de Compose (CA-A-09) | Bloquea el cierre formal de A; no la seguridad del apagado |
| QA-7 | **P1 (habilitar)** | P1-2/P1-3/P1-6 parciales y P1-4 sin prueba; `pollVersion` contradice la plantilla | Bloquea habilitar |
| QA-8 | **P2** | «Cierre A» sin documento de cierre: el commit dice «cerrar P1» pero el informe UIUX versionado sigue listando P1-1/P1-4/P1-6 como abiertos | Trazabilidad del merge |
| QA-9 | **P2** | `_logs_visor.html:48` conserva `href="/ui/estado"` (preexistente, ajeno a A) | Deuda conocida; no bloquea |

## 9. Condiciones para pasar a GO de fusión apagada

1. **A2/A3**: rebasar/separar el alcance o dejar por escrito la aceptación del PO de
   fusionar apilado y con módulos muertos (hoy 129 ficheros y 105 commits por delante).
2. **A5**: actualizar los textos y cifras stale; corregir la selección 1004 (o el comando)
   y declarar los 7 `skipped`.
3. **A7/CA-A-12**: ejecutar la **suite completa en el SHA final** (y Python 3.11), pegar
   comandos/recuentos o declarar NOT RUN sin presentarlo como PASS; `systemd-analyze
   verify` si se usa, NOT RUN explícito.
4. **A6/CA-A-11**: dictamen SecOps del SHA exacto que se fusione, con árbol limpio
   (revalidar tras integrar los informes).
5. **Cierre documental de UIUX**: registrar en un addendum que P1-1 y P2-1 quedan
   cerrados, que P1-2/P1-3/P1-4/P1-6 son parciales/están probados solo en parte y que
   QA-1 queda como condición de habilitación.
6. **No desplegar**: la fusión no cambia la política (A8).

## 10. Condiciones de habilitación (NO-GO)

Además de B1–B10, CE-1…CE-12 e I-1…I-9 y de la revisión SecOps del SHA final: cerrar
QA-1, QA-7 y los P1/P2 de UIUX pendientes (último intento B1.6/B7, formulario `auth none`
con prueba, aviso de versión JS, `hecha` sin mensaje de aceptación principal, copy llano,
campos/accesibilidad); y validar el circuito real en host aislado (B4), nunca en la Pi ni
producción. Hasta entonces la función sigue apagada, sin clave, sin socket y sin acción
visible.

## 11. NOT RUN (declarado, no PASS)

- Suite completa en `48526e03`; suite/validación en Python 3.11; `systemd-analyze verify`.
- Docker/PostgreSQL reales; `update.sh` real bajo la unidad; Pi; systemd del host;
  instalador OPS4 sobre host real (con y sin `--activar`); socket/unidad reales.
- Navegador real, lector de pantalla, anchos 1280/375; servidor/producción.
- Cualquier despliegue, provisión de clave o cambio de `.env`/Compose desplegado.

## 12. Gestión del documento

Único fichero escrito por esta QA: este. No se ha modificado ni ejecutado nada del
sistema anfitrión ni de la Pi. Las cifras de §2 son de esta sesión; las de §5 se contrastan
con los documentos citados, no se presentan como ejecutadas. Este informe **no concede**
GO de fusión ni de habilitación: solo describe el estado y las condiciones verificadas.
