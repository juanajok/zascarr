# Protocolo del piloto del banco de cobertura española (#135)

> **Estado:** guion operativo del piloto de **12 casos** y **80 peticiones máximas**. **No autoriza
> nada por sí mismo** ni declara cobertura: la autorización es
> [`banco-cobertura/autorizacion-piloto.json`](banco-cobertura/autorizacion-piloto.json), firmada por
> el PO. Hasta que haya ejecución real y revisión humana, la cobertura es **NOT RUN**.
> **Base:** [`banco-cobertura-espanola.md`](banco-cobertura-espanola.md) §5–§9,
> [`validacion-banco-cobertura-2026-11-06.md`](validacion-banco-cobertura-2026-11-06.md) y corpus v1
> (`sha256:1c9a5d0f5e8cc7dd95771aa6ec8d131b4e3ec55b55878a2e8eeaf6d6a9cdd6dd`).
> **Prerrequisito de código:** PR-3 (ejecución real). La entrega de preparación (PR-1/PR-2) valida y
> sale con **3 / NOT RUN** sin lanzar peticiones; si el arnés devuelve 3, no se ha ejecutado nada.

## 1. Quién hace qué (roles, no nombres)

El PO cubre los placeholders en el acta de designación. Este documento no inventa firmantes.

| Rol | Placeholder | Qué hace | Qué no hace |
|---|---|---|---|
| **PO** | `[PO]` | Acredita el corpus, firma la autorización, designa revisores y aprueba el cierre. | No ejecuta ni etiqueta candidatos. |
| **Ejecutor** | `[EJECUTOR]` | Lanza `--real` en la Pi, custodia el registro y anota incidencias. | No decide identidad ni ajusta etiquetas. |
| **Verificador editorial** | `[VERIFICADOR]` | Contrasta candidatos con la etiqueta y la evidencia; marca campos presentes/ausentes. | No usa la fuente evaluada como verdad ni fuerza el éxito. |
| **Segundo verificador** | `[SEGUNDO]` | Revisa `ambiguo` y desacuerdos; deja constancia de ambos veredictos. | No sustituye al PO. Si no existe, se declara `revision_simple`. |

Preferiblemente son personas distintas. Si el PO acumula roles, lo declara en el acta y el informe lo
anota; el ejecutor no revisa la tanda que él mismo lanzó salvo autorización expresa.

## 2. Antes de la primera petición

- [ ] **PR-3 desplegado.** Sin él, `--real` sale con 3 y `NOT RUN`: no hay ejecución que revisar.
- [ ] **Corpus acreditado por el PO.** Los **12 casos del piloto** ya llevan la etiqueta **corregida**
      (años de la edición española, no de la obra; `numero` numérico) y un dossier de evidencia pública
      en [`banco-cobertura/evidencia-acreditacion-v1.md`](banco-cobertura/evidencia-acreditacion-v1.md).
      Siguen en `acreditacion: "borrador"` a propósito: **el PO revisa el dossier y los pasa a
      `verificada`** (o corrige). Los otros 18 casos no entran en el piloto y siguen como propuesta.
      Hasta esa revisión, lo editorial queda `no_acreditada` y el piloto no puede hablar de aciertos.
- [ ] **SHA vigente.** `sha256sum docs/design/corpus-cobertura-v1.json` debe coincidir con
      `sha_corpus`. Al acreditar el corpus cambia: actualiza también
      [`banco-cobertura/manifiesto-corpus-v1.json`](banco-cobertura/manifiesto-corpus-v1.json); si no,
      el arnés rechaza por `sha_corpus_distinto`.
- [ ] **Autorización firmada.** Sustituir `PENDIENTE_DE_FIRMAR_POR_EL_PO` en `id` y `concede`; revisar
      `desde`/`hasta` (2026-11-06 → 2026-11-13, `+00:00`), `presupuesto_peticiones: 80`,
      `max_por_fuente: 20`, los 12 `casos` y los 24 pares `fuente:unidad`.
      **El arnés no detecta el placeholder**: `concede` no vacío pasa la validación; la puerta es
      humana.
- [ ] **Clave `nota` del JSON (ya resuelta).** Se retiró del fichero: el contrato del arnés
      (`CLAVES_AUTORIZACION`) no admite claves fuera de su lista. El aviso de firma y de SHA vive en
      `condiciones`. Si se vuelve a añadir, `--real` sale con 2 y cero peticiones.
- [ ] **Fuentes encendidas y configuradas en Ajustes** (Comic Vine con su clave; AniList, Tebeosfera y
      GCD encendidas). No se activan por `.env` ni por el arnés. Una fuente apagada o incompleta deja
      `no_ejecutado` con su causa y **sin petición**.
- [ ] **Pi lista:** un solo worker, sin otras tareas scrapeando las mismas fuentes y con la ventana
      acordada. La cortesía de #134 es compartida por proceso.
- [ ] **Salida nueva:** `docs/design/medicion-cobertura-2026-11-06-piloto/<tanda>/`, vacía.
      `registro.jsonl` es append-only: no reutilizar una carpeta de una ejecución anterior.
- [ ] **Revisores designados** (`[VERIFICADOR]` y `[SEGUNDO]`, o `revision_simple` declarada).

## 3. Orden de ejecución: secuencial, una fuente a la vez

Se ejecuta en **seis tandas, una por unidad**. En cada tanda el arnés recorre los casos y, para cada
caso, las cuatro fuentes en orden fijo (`comic_vine → anilist → tebeosfera → gcd`), **de una en una**:
nunca hay dos fuentes en paralelo ni dos tandas solapadas. No se lanza la tanda siguiente hasta cerrar
la anterior.

| # | Tanda (unidad) | Casos | Celdas con método | Peticiones HTTP previstas |
|---|---|---|---|---|
| 1 | `serie` | ES-001, ES-005, ES-007 | 12 | 12 |
| 2 | `edicion` | ES-010 | 2 | 2 |
| 3 | `publicacion` | ES-014, ES-016 | 4 | 2 |
| 4 | `numero` | ES-018, ES-019 | 2 | 0 |
| 5 | `formato` | ES-022 | 1 | 1 |
| 6 | `campo` | ES-026, ES-028, ES-029 | 12 | 9 |
| | **Total** | **12 casos** | **33** | **26** |

Cada caso se prueba en **su unidad esperada**; no se repite la misma llamada bajo dos unidades. El plan
no es 12 × 6 × 4: con 288 celdas y un tope de 20 por fuente, una sola ejecución agotaría el tope y
dejaría casos sin tocar.

Dos avisos de alcance que el ejecutor debe esperar:

- **7 celdas de Comic Vine no harán petición con el corpus actual**: `find_issue` necesita `volume_id`
  (en `etiqueta_editorial.campos`) y `numero`; `get_issue_detail`, `issue_id` (en `campos`). Hoy
  `campos` está vacío y falta `numero` en los casos de publicación. Salen
  `no_ejecutado: fuera_de_alcance`, no son fallos ni ausencias. Si el PO aporta esos identificadores al
  acreditar, serán 33 peticiones y el SHA cambiará.
- **La tanda `numero` no hará peticiones**: documenta el hueco de Comic Vine (`fuera_de_alcance`) y los
  `sin_metodo_autorizado` del resto; no mide acierto editorial.

Comando, una vez por tanda (`<restante>` = 80 − peticiones ya anotadas; nunca 80 en cada tanda):

```bash
python scripts/medicion/banco_cobertura.py --real \
  --autorizacion docs/design/banco-cobertura/autorizacion-piloto.json \
  --corpus docs/design/corpus-cobertura-v1.json \
  --casos <casos> --unidades <unidad> \
  --fuentes comic_vine,anilist,tebeosfera,gcd \
  --max-peticiones <restante> --max-por-fuente 20 \
  --salida docs/design/medicion-cobertura-2026-11-06-piloto/<tanda>
```

El arnés registra `peticiones: 1` por celda que llega a llamar al cliente y `0` si el caso no trae el
dato (`fuera_de_alcance`). Los reintentos internos van en la política de #134. El presupuesto es
**global del piloto**: el arnés solo lo aplica por invocación, así que el ejecutor lleva la cuenta de las
peticiones HTTP reales y pasa el resto.

## 4. Qué se anota por ensayo y dónde

El arnés escribe en `<salida>/`: `registro.jsonl` (una línea por ensayo, append-only), `informe.json` e
`informe.md` (parciales de esa tanda). Nada fuera de esa carpeta.

| Qué | Dónde | Quién |
|---|---|---|
| `ensayo_id`, `caso_id`, `fuente`, `capacidad`, `unidad`, `metodo` | `registro.jsonl` | Arnés |
| `estado_tecnico`, `estado_fuente_133`, `motivo_no_ejecutado`, `peticiones`, `reintentos` | `registro.jsonl` | Arnés |
| `candidatos` saneados (`rank`, `id_externo`, `etiqueta_propuesta`), `hash_respuesta`, `condiciones` | `registro.jsonl` | Arnés |
| `resultado_editorial`, `campos_evaluados`, `campos_presentes`, `campos_ausentes`, `revision`, `desacuerdo` | `revision-<tanda>.json`, una fila por ensayo/candidato; el cierre la incorpora al informe | Verificador / segundo |

El registro del arnés es **append-only**: no se edita una línea; una corrección abre una línea nueva con
`motivo_correccion`. La hoja de revisión es la fuente de los veredictos: no se reescribe el JSONL a
mano. Si PR-3 aplica `--revision`, se le pasa la hoja; si no, se adjunta al informe y este la cita. El
ejecutor no consulta la etiqueta al lanzar; el verificador la ve después y documenta la evidencia (copia
propia, ISBN, catálogo público), nunca la salida de la fuente evaluada como verdad.

## 5. Desacuerdos editoriales

- Cada candidato se marca `coincidencia_verificada`, `ambiguo` o `incorrecto`; los campos se marcan
  presentes/ausentes por separado. Un campo ausente no convierte por sí solo la coincidencia en
  incorrecta.
- Un `ambiguo` o un desacuerdo va al **segundo verificador**, que revisa por separado y deja ambos
  veredictos y el motivo en `desacuerdo`. **No se fuerza el éxito**: un `incorrecto` se publica como
  incorrecto y un desacuerdo no resuelto queda `identidad_acreditada: false` / `no_acreditada`.
- **Si no hay segundo verificador**, el informe declara `revision_simple` y no usa la expresión
  «verificada por dos». Lo no resuelto se informa aparte; no se descarta en silencio.
- No se ajusta el corpus con los resultados a la vista. Si una etiqueta estaba mal, se corrige en una
  **versión nueva** del corpus (`v2`), con su SHA y su autorización; la v1 congelada no se edita.

## 6. Parada y presupuesto

| Condición | Efecto | Qué hace el ejecutor |
|---|---|---|
| Sin autorización, caducada, SHA distinto o fuera de ámbito | Exit 2, **cero peticiones** | No ejecutar; corregir y pedir firma. |
| Fuente apagada o configuración incompleta | `no_ejecutado`, **cero peticiones** | Encender/configurar en Ajustes y repetir la tanda en una carpeta nueva; no es un fallo transitorio. |
| `limite_de_cortesia` | Parada de la tanda | Esperar; no reintentar fuera de #134; reanudar solo con autorización vigente. |
| 3 fallos transitorios consecutivos de una fuente | Parada de la tanda | No compensar con más tráfico; registrar y revisar la fuente. |
| 20 peticiones en una fuente o 80 en el piloto | Parada de la tanda | Cerrar el parcial con `NOT RUN`; no gastar el resto «por gastar». |
| Caducidad de la autorización a mitad | Parada | No reutilizarla; nueva autorización con fechas nuevas. |

El tope por fuente detiene la tanda completa, no solo esa fuente. Si se agota el presupuesto: no se pide
más, no se baja la cortesía, no se reintenta fuera de política; se guarda el informe parcial con
`presupuesto_agotado`/`NOT RUN` y se pide **nueva autorización** para continuar. No se reutiliza una
autorización agotada. El respeto de #134 es condición de parada, no un detalle. Una tanda repetida no se
escribe en la carpeta anterior: se abre `<tanda>-reintento` y se conserva la primera como incidencia.

## 7. Publicación del informe

- Un único informe: `docs/design/medicion-cobertura-2026-11-06-piloto.md` + `.json`, con las seis
  tandas y sus `registro.jsonl` como anexo. No se publican seis informes parciales como si fueran el
  piloto.
- Cabecera: SHA del ejecutor, versión y SHA del corpus, `id`/ámbito de la autorización, fechas, modo,
  fuentes encendidas, presupuesto, condiciones y roles que revisaron.
- Secciones de §7 de la spec: alcance, matriz fuente × unidad, métricas con numerador y denominador
  (cantidades si n < 10), PASS/FAIL/NOT RUN separados, demostrado/ambiguo/pendiente, límites, evidencia
  y cierre.
- **Saneado:** sin URL, query, cookies, cabeceras, claves, credenciales, rutas ni datos personales. Solo
  identificadores de caso, fuente, método, estados, códigos, hashes y referencias públicas. El arnés
  valida la salida, pero el verificador la relee antes de commitear.
- Lo redacta el verificador, lo aprueba el PO y se publica como PR de documentación en el repo. No se
  publica fuera del repo, no activa fuentes y no cambia reglas de producto. Si aparece una URL o una
  clave, se para, se corrige y se regenera; no se commitea.

## 8. Qué no se puede afirmar y límites

- **12 casos no son una muestra representativa**: el corpus es intencional (no aleatorio) y el piloto
  cubre 12 de 30 casos, una instalación y una fecha. No se extrapola a la población ni al corpus
  completo.
- **80 peticiones no generalizan**: el plan base usa 26 (33 si se añaden los identificadores de Comic
  Vine); el techo no convierte el piloto en una medición de cobertura.
- El piloto **valida el arnés y da una primera señal**; no es un veredicto de cobertura. No hay una
  cifra única de cobertura, ni «la fuente X cubre el Y %», ni porcentajes con denominador 0.
- `disponibilidad_tecnica` no es cobertura editorial; `sin_resultados` es ausencia, no `incorrecto`; un
  `no_ejecutado` no es falta de cobertura. Las etiquetas `identidad_acreditada: false` no suman a
  coincidencias.
- Con `revision_simple` no se dice «verificada por dos». Un `--seco` no acredita cobertura.
- El informe no autoriza integración, despliegue ni cambios de producto; cualquier propuesta va al
  backlog o a una spec nueva, no se aplica desde el piloto.

## 9. Cierre

El PO firma el cierre con el `id` de la autorización, las tandas ejecutadas, las incidencias, el tipo de
revisión y el SHA del corpus revisado. El piloto termina cuando el informe está saneado y aprobado; la
ejecución del corpus completo (30 casos) es otra autorización y otro informe.
