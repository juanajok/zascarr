# Validación del banco de cobertura española (#135) — 2026-11-06

> **Estado:** **PASS del arnés en seco**; **cobertura real NOT RUN** (no se ha lanzado ninguna
> petición) y **revisión humana NOT RUN**. Este documento no declara cobertura.
> **Base:** `main` al 2026-11-06. Sin dependencias nuevas, sin migración, sin red en las
> pruebas. Corpus v1: `sha256:1c9a5d0f5e8cc7dd95771aa6ec8d131b4e3ec55b55878a2e8eeaf6d6a9cdd6dd`.

## 1. Qué se entrega (preparación, PR-1 + PR-2)

- **Corpus v1 en borrador**: 30 casos (8 serie, 8 edición/publicación, 8 número/formato,
  6 campo), 6 editoriales y formatos variados. **Todas las etiquetas son propuestas**:
  `acreditacion: "borrador"`, `identidad_acreditada: false`; **2 casos** están marcados
  además `sin_identidad_acreditada` para comprobar que no suman a coincidencias. El PO debe
  verificar/ajustar etiquetas y procedencia antes de la ejecución real.
- **Fixtures saneados** (`docs/design/fixtures-cobertura/seco.json`): 8 ensayos que ejercitan
  `ok`, `sin_resultados`, `fallo_transitorio`, `limite_de_cortesia`, `fuente_apagada`,
  `configuracion_incompleta`, `sin_metodo_autorizado` y un campo ausente. Sin URL ni claves.
- **Arnés** `scripts/medicion/banco_cobertura.py`: `--seco` valida corpus, fixtures, parser,
  registro, métricas e informe; `--real` exige autorización versionada (ámbito, presupuesto,
  caducidad y SHA del corpus) y, sin ella, sale con **exit 2 y cero peticiones**. No se ha
  ejecutado el modo real.
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
`zascarr.services.discovery` **no** se cargan. `tests/test_banco_cobertura.py`: **43 passed**.

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
- métricas con n=0, n<10 (sin porcentaje), n≥10 (con denominador), no acreditadas, ausencias y
  campos faltantes por campo.

## 3. NOT RUN — lo que no se puede afirmar

- **Cobertura editorial real**: no hay ejecución autorizada; ninguna cifra de cobertura. Un
  `--seco` con sintéticos **no** acredita cobertura (criterio 9).
- **Revisión humana**: sin verificadores designados; no hay `coincidencia_verificada`, ni
  `ambiguo`/`incorrecto` reales, ni `revision_simple` declarada.
- **Piloto de 12 casos / 80 peticiones**: no autorizado ni ejecutado.
- **Red real y disponibilidad de fuentes**: no medida; los fixtures no la representan.
- **Precisión/cobertura con porcentajes**: imposible sin revisión; además el corpus es
  intencional (no aleatorio), así que la cifra no se extrapola a la población.

## 4. Qué falta para autorizar el piloto

1. **PO acepta o corrige el corpus v1** y acredita etiquetas con evidencia (§3.2/§3.3 de la
   spec): hoy las 30 son borrador y ninguna suma a coincidencias. Los 2 casos
   `sin_identidad_acreditada` deben seguir marcados.
2. **Autorización versionada** con `id`, `ambito`, `presupuesto_peticiones` (80),
   `max_por_fuente` (20), `desde`/`hasta`, `concede` (persona del PO), `condiciones` y
   `sha_corpus` igual al del manifiesto. Copiar la plantilla a
   `docs/design/banco-cobertura/autorizacion-<id>.json`.
3. **Revisores designados**: verificador editorial y, si se quieren revisar desacuerdos, un
   segundo; si no hay segundo, el informe declarará `revision_simple`.
4. **Fuentes encendidas y configuradas** en Ajustes (nunca por el arnés) y **ejecución
   secuencial** con `--real --autorizacion <ruta> --casos ... --max-peticiones 80`; parada por
   presupuesto, cortesía o 3 fallos transitorios. Después, revisión humana y actualización del
   informe de cobertura (PR-3).
5. **Ninguna cifra de cobertura** se publica antes de 2–4: el resultado de este documento es
   `NOT RUN`.

## 5. Límites y privacidad

- Corpus intencional, 30 casos, una instalación y una fecha: no se extrapola.
- Sin datos privados, URLs, query, claves ni credenciales en corpus, fixtures, registro e
  informes.
- El arnés no activa fuentes, no escribe en la base ni en la caché y solo escribe su salida
  (`--salida`).
