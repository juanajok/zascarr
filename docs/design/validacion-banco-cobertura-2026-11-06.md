# Validación del banco de cobertura española (#135) — 2026-11-06

> **Estado:** **PASS del arnés en seco**; **cobertura real NOT RUN** (no se ha lanzado ninguna
> petición) y **revisión humana NOT RUN**. Este documento no declara cobertura.
> **Base:** `main` al 2026-11-06. Sin dependencias nuevas, sin migración, sin red en las
> pruebas. Corpus v1: `sha256:7f1a0f1f916a8572278c3fea149490029c235b01e7293a9718fe9c8b300665b2`.

## 1. Qué se entrega (preparación y ejecutor real)

- **Corpus v1**: 30 casos (8 serie, 8 edición/publicación, 8 número/formato, 6 campo),
  6 editoriales y formatos variados; **12 acreditados** y **18 en borrador** (2 de ellos
  `sin_identidad_acreditada`). Las etiquetas acreditadas llevan evidencia y verificador
  `juanajok (PO)`; las de borrador siguen propuestas y no suman a coincidencias. El PO
  puede corregir/retirar casos antes de la ejecución real.
- **Fixtures saneados** (`docs/design/fixtures-cobertura/seco.json`): 8 ensayos que ejercitan
  `ok`, `sin_resultados`, `fallo_transitorio`, `limite_de_cortesia`, `fuente_apagada`,
  `configuracion_incompleta`, `sin_metodo_autorizado` y un campo ausente. Sin URL ni claves.
- **Arnés** `scripts/medicion/banco_cobertura.py`: `--seco` valida corpus, fixtures, parser,
  registro, métricas e informe; `--real` exige autorización versionada (ámbito, presupuesto,
  caducidad y SHA del corpus) y, sin ella, sale con **exit 2 y cero peticiones**. Con
  autorización válida, el ejecutor revalida el permiso, **carga los interruptores de Ajustes
  desde `runtime_settings`** (ADR 0013; si no hay BD/fila sigue con el `.env`), llama a los
  clientes existentes (que pasan por `pedir_con_cortesia` de #134), respeta los topes
  efectivos y para por presupuesto, cortesía, fuente apagada o 3 fallos consecutivos.
  **No se ha ejecutado con datos reales**: el estado de cobertura sigue `NOT RUN`.
- **Métricas con denominadores**: por fuente × unidad, separando disponibilidad técnica de
  precisión/cobertura editorial; sin porcentajes con denominador 0 y solo cantidades si n<10;
  `sin_extractor`/estados no se mezclan con editorial.
- **Plantilla de autorización** en `docs/design/banco-cobertura/autorizacion-plantilla.json`
  (sin valores reales; se copia a `autorizacion-<id>.json` cuando el PO la conceda).
- **Manifiestos** con `sha256`: `docs/design/banco-cobertura/manifiesto-corpus-v1.json` y
  `docs/design/fixtures-cobertura/manifiesto.json`.

## 2. PASS — arnés en seco

Comando ejecutado (sin red):

```bash
python scripts/medicion/banco_cobertura.py --seco \
  --corpus docs/design/corpus-cobertura-v1.json \
  --fixtures docs/design/fixtures-cobertura/seco.json \
  --salida /tmp/medicion-cobertura-2026-11-06
```

Resultado: **8 ensayos**, informe con `cobertura: NOT RUN` y PASS/FAIL/NOT RUN separados;
cero peticiones; sin sockets ni clientes. En subproceso se comprueba además que `httpx` y
`zascarr.services.discovery` **no** se cargan. `tests/test_banco_cobertura.py`: **58 passed**.

Cubierto por pruebas (PASS):

- corpus inválido rechazado (claves, tamaño, duplicados, procedencia, URL/query);
- fixtures de los estados de #133 + `no_ejecutado` y saneado;
- `--seco` de punta a punta, cobertura `NOT RUN`, JSONL sin URL/query/claves;
- `--seco` no importa ni construye clientes ni llama a `pedir_con_cortesia` (doble que falla);
- `--real` **sin autorización** → exit 2, cero peticiones y filas
  `no_ejecutado: sin_autorizacion`; autorización caducada, fuera de ámbito (incluido por
  capacidad/unidad/caso), con SHA distinto, fecha naive, tipos estrictos o sin presupuesto →
  rechazada; el fichero no-UTF8 también sale con 2, nunca traceback;
- mapeo de `CortesiaEnEspera`/`FuenteApagada`/`ReintentosAgotados(429/500)` a los estados de
  #133/#134;
- SHA del corpus leído una vez en bytes y comparado con el manifiesto;
- PASS calculado de los datos (no «30 casos» fijo), JSONL append-only, sin rutas ni SHA de
  entorno en el informe, centinela de salida y lista blanca de campos.
- ejecutor real con cliente inyectado (cero red): ejecuta y para por presupuesto; fuente
  apagada → cero peticiones; 429 → `limite_de_cortesia` sin reintento extra; 3 fallos →
  parada; revalidación final del permiso (SHA/ámbito/casos) antes de cualquier petición;
- **overlay de Ajustes**: un `comicvine_enabled=True` en `runtime_settings` deja de dar
  `fuente_apagada`; sin fila/BD se mantiene el `.env` y `fuente_apagada`;
- **tope por fuente**: cuando una fuente llega a `max_por_fuente` solo se saltan sus celdas
  (`limite_por_fuente`) y las demás continúan; el tope global (`max_peticiones`) sí detiene
  todo el banco;
- métricas con n=0, n<10 (sin porcentaje), n≥10 (con denominador), no acreditadas, ausencias y
  campos faltantes por campo.

## 3. NOT RUN — lo que no se puede afirmar

- **Cobertura editorial real**: no hay ejecución autorizada; ninguna cifra de cobertura. Un
  `--seco` con sintéticos **no** acredita cobertura (criterio 9).
- **Revisión humana**: verificador `juanajok (PO)`; sin `coincidencia_verificada`,
  `ambiguo`/`incorrecto` reales ni `revision_simple` declarada todavía.
- **Ejecución real del piloto**: ejecutada el 2026-11-06 con la autorización
  `piloto-cobertura-2026-11-06`; la cobertura sigue `NOT RUN` hasta la revisión humana.
  La ejecución con el tope por fuente corregido se repite y se registra en
  `/tmp/medicion-cobertura-piloto-2`.
- **Red real y disponibilidad de fuentes**: no medida; los fixtures no la representan.
- **Precisión/cobertura con porcentajes**: imposible sin revisión; además el corpus es
  intencional (no aleatorio), así que la cifra no se extrapola a la población.

## 4. Qué falta para cerrar el piloto

1. **Corpus**: hay 12 etiquetas acreditadas con evidencia y 18 en borrador; solo las
   acreditadas suman a coincidencias. Los 2 casos `sin_identidad_acreditada` siguen marcados.
2. **Autorización**: `piloto-cobertura-2026-11-06` concede el piloto (80 peticiones, 20 por
   fuente). No hace falta una nueva para repetir la pasada con el tope corregido.
3. **Revisor**: el verificador editorial es el PO (`juanajok`); si se quieren revisar
   desacuerdos, un segundo; si no hay segundo, el informe declarará `revision_simple`.
4. **Ejecución**: fuentes encendidas en Ajustes (el arnés ya aplica el overlay de
   `runtime_settings`), ejecución secuencial con el comando del PR y salida nueva; después,
   revisión humana de candidatos y actualización del informe de cobertura.
5. **Ninguna cifra de cobertura** se publica antes de 4: el resultado de este documento es
   `NOT RUN`.

## 5. Límites y privacidad

- Corpus intencional, 30 casos, una instalación y una fecha: no se extrapola.
- Sin datos privados, URLs, query, claves ni credenciales en corpus, fixtures, registro e
  informes.
- El arnés no activa fuentes, no escribe en la base ni en la caché y solo escribe su salida
  (`--salida`).
