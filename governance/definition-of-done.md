# Definición de hecho (DoD) — aprobada el 2026-11-26

Un trabajo se cierra cuando se cumple lo que exige su nivel de riesgo y existe evidencia enlazada, no cuando el autor lo considera terminado.

## Común a todo trabajo

- Criterios de aceptación verificados uno por uno.
- Sin hallazgos bloqueantes abiertos del nivel correspondiente.
- Documentación y enlaces actualizados; nada de referencias rotas.
- La evidencia indica el SHA o la fecha concreta a la que se refiere.

## Cambios con código

- Pruebas en verde y, cuando aplique, evidencia del rojo previo por el motivo esperado.
- Suite del proyecto en verde en el entorno declarado; los omitidos se justifican.
- Revisión de seguridad **del SHA final** en los casos que la exigen, incluidos los commits añadidos después.
- Ninguna prueba crítica omitida sin decisión explícita.

## Cambios documentales

- Contraste con la fuente citada; el texto distingue lo comprobado de lo inferido.
- Si se retira una norma, existe aprobación del traslado y consta la fecha.

## Límites

El DoD no sustituye la aprobación de fusión ni la decisión de despliegue, que son actos separados y humanos.

## Reglas migradas

### PRE-18 — Regresión nombrada y sin dependencias por probar

Ninguna dependencia nueva se añade «por testing»: lo que se pueda comprobar con la infraestructura existente se comprueba con ella. Cada bug real se cierra con una **prueba de regresión explícita**, nombrada con el mecanismo del bug, no con una prueba genérica.

## Reglas migradas (segunda tanda)

### PRE-16 — Patrón de pruebas con sesión simulada

El patrón prevalente es `app.dependency_overrides[get_db]` con una `FakeSession` dirigida por cola. Las pruebas ya montadas son la referencia (`tests/test_api_wishlist.py`, `tests/test_api_series.py`); la única excepción que toca Postgres real es `test_title_norm.py`, que se omite sin `TEST_DATABASE_URL`.

### PRE-17 — La suite también con temporal en el dispositivo raíz

La suite se ejecuta también con `pytest --basetemp=<ruta en el disco raíz>`. En una máquina donde `/tmp` es `tmpfs`, el comportamiento que depende del dispositivo (por ejemplo la guarda de rutas obsoletas de `services/importer.py`) difiere de la CI y un fallo real queda enmascarado; ocurrió con la PR #84.

### PRE-19 — Pruebas con Postgres real

Con `TEST_DATABASE_URL`, siempre una base cuyo nombre lleve «test»: la sesión migra esa base a `head` una vez (`tests/conftest.py`). Lo que necesite otro estado (por ejemplo «sin migrar») crea su propia base con `tests._pg.bd_efimera()`. Los subprocesos de Alembic usan `tests._pg.alembic`, que quita la raíz del repo de `PYTHONPATH` para que el `alembic/` del repo no sombree el paquete. Detalle en [diagnóstico de Postgres en pruebas](../docs/design/diagnostico-postgres-pruebas.md).

### PRE-20 — Git como documentación

- Commit pequeño y atómico: un cambio de dominio por commit; el renombrado del proyecto fue un commit, no diez.
- Mensajes en español con el formato `<área>: <qué> (<porqué> si no es obvio)`.
- No se commitea depuración local (`.env`, perfiles, volcados).
- Al cerrar una historia P0/P1 se actualiza `docs/BACKLOG.md` a «Hecho» con la nota del mecanismo: cómo se cerró, no solo que se cerró.
