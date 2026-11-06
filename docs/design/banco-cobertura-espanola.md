# SPEC: Banco de cobertura española con evidencia (#135, MIT-M8-US03) — preparación v1.0

> **Estado:** v1.0 **de preparación, no de ejecución**. Define el banco, el corpus, el registro, las
> métricas y el arnés para que sean construibles. **No autoriza consultas externas**: un ensayo con
> respuestas sintéticas puede validar el arnés, pero **no acredita cobertura**. La ejecución real y la
> revisión humana son un paso posterior, con permiso separado (§11). **Cobertura: NOT RUN en esta entrega.**
> **Base contrastada:** `721345a` (worktree `.squad/wt-135`, rama `feat/135-banco-cobertura`), con #133 y
> #134 ya en `main`; sus contratos se reutilizan, no se duplican. (El documento de #133 cita `3562f3a`; el
> código y las líneas que usa esta spec son los de `721345a`.)
> **Semilla:** issue #135 (10 criterios), contrato padre #111 (cuatro dimensiones), #133
> (`docs/design/estados-fuentes-133.md`), #134 (`utils/cortesia.py`, `utils/peticiones.py`,
> `docs/design/cortesia-compartida.md`) y ADR 0003 (vocabulario editorial).
> **Decide el PO.** Esta spec no activa fuentes, no cambia reglas de producto y no declara cobertura.

---

## 0. Resumen y alcance de la entrega

**Qué es el banco.** Un procedimiento y un arnés para medir, con evidencia acreditable, **qué capacidad y
qué cobertura editorial española** aporta cada fuente **por unidad editorial** (serie, edición, publicación,
número, formato y campo), sin inferir de la web y sin convertir la evaluación en una regla de producto.
No elige fuentes automáticamente ni activa conectores.

**Qué se entrega ahora:** esta spec, el esquema del corpus versionado, la matriz de ensayos, el esquema de
registro reconciliado con #133, las métricas con denominadores, el contrato del arnés en modo `--seco`, el
formato de informe y el plan de validación humana. **No** se entrega la ejecución real.

**Qué no se puede declarar:** cobertura verificada, capacidad nueva «disponible» ni una cifra de cobertura
obtenida de respuestas sintéticas. Un `--seco` correcto demuestra que el arnés funciona; el resultado de
cobertura es `NOT RUN` hasta que exista ejecución autorizada + revisión humana (§7, §9).

**Corte de la historia:** el issue ya prevé separar preparación de ejecución. Se confirma: **preparación
ahora (PR-1 y PR-2), ejecución después con permiso separado (PR-3)**; no se da el diseño por cobertura
demostrada (§11).

---

## 1. Contratos que se reutilizan (no se reimplementan)

### 1.1 Cuatro dimensiones separadas (#111)

El banco no colapsa nada en una etiqueta. Hereda las cuatro dimensiones del contrato padre:

| Dimensión | En el banco |
|---|---|
| **Capacidad** | `soportada` / `no soportada` / `desconocida`, por fuente y unidad (§2) |
| **Configuración** | `completa` / `incompleta` (clave ausente), antes de cualquier petición |
| **Disponibilidad operativa** | `habilitada` / `apagada` / `limitada por cortesía` (#134) |
| **Resultado de la petición** | `ok`, `sin_resultados`, `fallo_transitorio`, `limite_de_cortesia`, `configuracion_incompleta`, `fuente_apagada` (#133) |

La **calidad editorial** (`coincidencia_verificada`, `ambiguo`, `incorrecto`) es una quinta capa, separada
de las anteriores. Un éxito técnico con identidad incorrecta existe y se registra; una fuente apagada no es
un fallo técnico ni una ausencia de cobertura.

### 1.2 Estados técnicos de #133 (conjunto cerrado)

| Estado | Significado | ¿Petición? |
|---|---|---|
| `ok` | Respondió y devolvió al menos un candidato | sí |
| `sin_resultados` | Respondió correctamente sin candidatos | sí |
| `fallo_transitorio` | Error de red, HTTP o del cliente | sí |
| `configuracion_incompleta` | Encendida pero falta clave/ajuste | **no** |
| `limite_de_cortesia` | Pidió esperar y no cabe en el presupuesto | sí/limitada |
| `fuente_apagada` | Desactivada en Ajustes | **no** |

Contrato: `services/discovery.py:60-66` (`ESTADOS_DE_FUENTE`), `:75` (`CAPACIDAD_BUSQUEDA`), `:87-105`
(`EstadoFuente` con `fuente`, `capacidad`, `motivo`, `reintentar_en`) y clasificación de cada excepción en
`:200-260`; documento: `docs/design/estados-fuentes-133.md:7-25,29-37`. #133 solo tiene **una capacidad
verificada**, `busqueda`; el banco **no** añade capacidades a #133: usa identificadores propios de ensayo
(§2) y no las publica como «verificadas» en la app.

### 1.3 Cortesía y autorización de #134

El banco no hace peticiones «a mano»: usa los clientes migrados y `utils/peticiones.py:228`
(`pedir_con_cortesia`), que aplica política por fuente y host, redirecciones manuales, reintentos y
presupuesto (`utils/cortesia.py:169` `PoliticaFuente`, `:206` `politica_de`, `:229` `fuente_habilitada`,
`:486` `esperar`, `:500` `bloquear`). Errores con código corto y sin URL: `utils/peticiones.py:52-88`
(`ErrorDePeticion`, `RedireccionNoPermitida`, `DemasiadasRedirecciones`, `ReintentosAgotados`,
`RespuestaNoTransitoria`), más `FuenteApagada`/`CortesiaEnEspera` (`utils/cortesia.py`).

Mapeo al registro del banco (§4): `FuenteApagada` → `fuente_apagada`; configuración incompleta
comprobada antes de instanciar → `configuracion_incompleta`; `CortesiaEnEspera` o
`ReintentosAgotados(ultimo_codigo=429)` → `limite_de_cortesia`; otra excepción de red/HTTP/parseo →
`fallo_transitorio`; lista vacía → `sin_resultados`; lista con candidatos → `ok`. Es exactamente la
clasificación de #133 (`services/discovery.py:200-260`).

### 1.4 Vocabulario editorial (ADR 0003)

Se usa el vocabulario del ADR 0003, no uno propio: **serie** (`Series`), **edición** (línea de publicación
con numeración propia; **no existe como entidad** y no se inventa), **publicación/número** (`Issue`),
**formato de publicación** (`IssueFormat`; no confundir con formato de archivo), **campo** (dato de
metadatos). «Obra» no es entidad. En el banco, «edición» es una **unidad de evaluación observable**
(¿la fuente distingue la línea editorial española?), no una entidad nueva ni una migración.

---

## 2. Matriz fuente × capacidad × unidad editorial

### 2.1 Unidades evaluadas por separado

| Unidad | Qué acredita | Qué **no** acredita |
|---|---|---|
| **Serie** | Identificar la serie/agrupación (`Series`) | Una edición española concreta |
| **Edición** | Distinguir una línea editorial (sello, país, idioma, colección) | Que ZascArr modele ediciones (ADR 0003: no existe entidad) |
| **Publicación** | Identificar una publicación concreta (`Issue`) | Que el número baste como identidad |
| **Número** | Etiqueta de número dentro de una edición | Un número suelto sin edición |
| **Formato** | Formato de publicación (`IssueFormat`: grapa, tomo, álbum…; `models/__init__.py:55-63`) | Formato de archivo (CBZ/CBR) |
| **Campo** | Campos concretos que devuelve el método autorizado | Campos que solo se ven en la web |

**Regla dura (criterio 1):** un acierto en **serie** no suma ni se cuenta como acierto en **edición,
publicación, número, formato o campo**. Cada celda de la matriz se mide y se informa por separado.

### 2.2 Métodos autorizados en el código vigente

Solo cuentan los métodos que existen en el código; la web no acredita ningún campo (criterio 4).

| Fuente | Método autorizado | Qué devuelve | Cita |
|---|---|---|---|
| Comic Vine | `search_series(query)` | serie: id, título, sinopsis, portada, año, nº de números, URL | `comic_vine.py:122-136` |
| Comic Vine | `find_issue(volume_id, number)` | publicación/número: issue, sinopsis, portada, fecha, créditos | `comic_vine.py:149-162` |
| Comic Vine | `get_issue_detail(issue_id)` | campos de una publicación concreta | `comic_vine.py:137-147` |
| AniList | `search_manga(query)` | serie: títulos, sinopsis, portada, año, capítulos, volúmenes | `anilist.py:105-108` |
| Tebeosfera | `search_series(query)` | dos tablas: colecciones (ediciones/tiradas) y sagas | `tebeosfera.py:198-204` |
| GCD | `search_series(query)` | serie: título, años, idioma, país, URL | `gcd.py:109-143` |

### 2.3 Matriz de capacidad (planificación, no resultado)

`S` = método autorizado que devuelve la unidad; `P` = evidencia parcial, no identidad acreditada;
`—` = sin método autorizado en el código (**no se prueba**; no se declara «no soportada» sin evidencia);
`n/a` = no aplica a esa fuente por su modelo.

| Unidad | Comic Vine | AniList | Tebeosfera | GCD |
|---|---|---|---|---|
| Serie | **S** (`search_series`) | **S** (`search_manga`) | **S** (`search_series`, sagas/colecciones) | **S** (`search_series`) |
| Edición | `—` | `—` | **P** (`search_series` distingue colección/saga; sin sello/país parseado) | **P** (`search_series` expone idioma/país; sin editorial/formato en el método) |
| Publicación | **P** (`find_issue` exige `volume_id` de CV; no identifica edición española por sí solo) | `—` | **P** (la entrada de colección no es una publicación concreta) | `—` |
| Número | **S** (`find_issue`) | `—` | `—` | `—` |
| Formato | `—` | `—` | **P** (colección/saga no es `IssueFormat`) | `—` |
| Campo | **S** (`search_series`, `get_issue_detail`) | **S** (`search_manga`) | **P** (`search_series`) | **P** (`search_series`) |

**Lectura obligatoria:** `S` autoriza a **probar**; no acredita cobertura. `P` obliga a registrar
`ambiguo`/`campo_ausente` hasta que la ejecución real y la revisión humana digan otra cosa. `—` produce
`no_ejecutado` con motivo `sin_metodo_autorizado`; **no** se convierte en «sin cobertura» ni en noticia de
que la fuente no lo tenga. Una capacidad no verificada no se presenta como disponible (criterio 3), igual
que en #133 (`docs/design/estados-fuentes-133.md:23-25`).

### 2.4 Matriz de campos por método

Campos que el método **devuelve y el cliente parsea**; no se infieren campos de la web.

| Campo | CV `search_series` | CV `find_issue`/`get_issue_detail` | AniList | Tebeosfera | GCD |
|---|---|---|---|---|---|
| Título | sí | `name` | sí (romaji/inglés) | sí | sí |
| Sinopsis | sí | sí | sí | sí | **no** |
| Portada (URL) | sí | sí | sí | sí | **no** |
| Año inicio | sí | — | sí | sí | sí |
| Año fin | — | — | — | — | sí |
| Idioma / país | — | — | — | — | sí |
| Nº de publicaciones/capítulos | sí (`count_of_issues`) | — | sí (`chapters`, `volumes`) | sí (`count_of_issues`) | **no** |
| Número de publicación | — | sí | — | — | — |
| Fecha de portada | — | sí | — | — | — |
| Créditos / personajes / sagas | — | sí | — | — | — |
| Formato de publicación | — | — | — | — | — |

`campo_ausente` se registra **por campo** y puede coexistir con una coincidencia editorial en otro campo
(criterio 5). Un campo vacío no convierte la coincidencia en incorrecta por sí solo; se informa aparte.

---

## 3. Corpus versionado

### 3.1 Esquema

Archivo: `docs/design/banco-cobertura/corpus-v1.json` (inmutable una vez congelado; cambios = `v2`).
Manifiesto junto a él con `sha256` de cada caso y del archivo.

```json
{
  "version": "v1",
  "creado": "2026-11-06T00:00:00+00:00",
  "criterios_inclusion": "edición española publicada, identificable por copia propia o dato bibliográfico público; sin datos personales",
  "tamano_objetivo": 30,
  "estratos": {"serie": 8, "edicion_publicacion": 8, "numero_formato": 8, "campo": 6},
  "casos": [{
    "caso_id": "ES-001",
    "estrato": "serie",
    "consulta": "consulta de búsqueda de la serie",
    "unidad_esperada": "serie",
    "etiqueta_editorial": {
      "obra": "…", "serie": "…", "editorial": "…", "coleccion": "…",
      "pais": "ES", "idioma": "es", "edicion": "…", "numero": "…",
      "formato": "single_issue|trade_paperback|hardcover|omnibus|graphic_novel|album|manga_tankobon|digital",
      "anio": 2007, "campos": {}
    },
    "identidad_acreditada": true,
    "procedencia": "copia_propia|isbn|deposito_legal|catalogo_publico",
    "evidencia": "identificador o referencia pública saneada",
    "verificador": "id-humano",
    "fecha_verificacion": "2026-11-06",
    "desacuerdo": null,
    "notas": ""
  }]
}
```

### 3.2 Tamaño, selección y procedencia

- **v1: 30 casos** (propuesta para aceptar en el DoR): 8 de serie, 8 de edición/publicación, 8 de
  número/formato, 6 de campo. Al menos **6 editoriales**, 3 tradiciones (tebeo, BD, manga), formatos
  variados (grapa, tomo, integral, álbum, tankobon) y **2 casos deliberadamente sin identidad acreditada**
  para probar que no cuentan como coincidencia.
- Casos **estratificados a propósito**, no aleatorios: la cifra no se extrapola a la población (limitación
  del informe, §7). Se incluyen casos difíciles (editorial pequeña, edición antigua, homónimo) sin
  seleccionarlos porque fallen.
- **Procedencia permitida:** copia propia (colofón/ISBN/depósito legal), catálogo público de biblioteca o
  editorial, o dato bibliográfico público. **Prohibido:** datos privados del coleccionista, scraping de la
  fuente evaluada, la propia fuente como verdad de referencia y cualquier fuente no autorizada.
- **Circularidad:** un caso cuya etiqueta solo se apoye en la fuente que se evalúa se marca
  `procedencia=dependiente_de_la_fuente` y se excluye de esa fuente en la métrica de coincidencias.

### 3.3 Etiqueta verificada y “no acreditada”

- `identidad_acreditada: true` solo si un humano verificó la etiqueta con evidencia de §3.2. La etiqueta
  incluye editorial/país/idioma/edición/número/formato **aunque ZascArr aún no modele la edición** (ADR
  0003): es dato de evaluación, no una entidad nueva.
- `identidad_acreditada: false` → el caso se ejecuta para el arnés, pero **nunca** suma a
  `coincidencia_verificada`; se cuenta como `no_acreditada` y se informa aparte (criterio 2).
- La etiqueta se escribe **antes** de ejecutar (patrón de `scripts/medicion/evaluar_real.py:1-30`), para no
  ajustarla al resultado. Una etiqueta no se edita en la misma versión del corpus.

### 3.4 Verificación y desacuerdos

- **Verificador editorial** (persona con criterio; PO o quien designe) etiqueta con evidencia; no usa la
  salida de la fuente para fijar la etiqueta.
- **Segundo verificador** revisa los casos `ambiguo` y los desacuerdos; si no hay segundo, el informe
  declara `revision_simple` y **no** usa la palabra «verificada por dos».
- Desacuerdo no resuelto: `identidad_acreditada=false`, `desacuerdo` con ambos veredictos y motivo; no se
  fuerza el éxito ni se descarta el caso en silencio. Se cuenta en `no_acreditada`.

---

## 4. Registro por ensayo (reconciliado con #133)

### 4.1 Esquema (JSONL, una línea por ensayo)

```json
{
  "ensayo_id": "ES-001__comic_vine__serie__1",
  "corpus_version": "v1",
  "caso_id": "ES-001",
  "fuente": "comic_vine|anilist|tebeosfera|gcd",
  "capacidad": "busqueda_serie|busqueda_publicacion|identidad_edicion|numero|formato|campo",
  "unidad": "serie|edicion|publicacion|numero|formato|campo",
  "metodo": "ComicVineClient.search_series",
  "sha_ejecutor": "721345a…",
  "modo": "seco|real",
  "autorizacion": {"id": "auth-2026-11-06-1", "ambito": ["comic_vine"], "presupuesto_peticiones": 80},
  "estado_tecnico": "ok|sin_resultados|fallo_transitorio|limite_de_cortesia|no_ejecutado",
  "estado_fuente_133": "ok|sin_resultados|fallo_transitorio|limite_de_cortesia|configuracion_incompleta|fuente_apagada|null",
  "motivo_no_ejecutado": "sin_autorizacion|modo_seco|fuente_apagada|configuracion_incompleta|presupuesto_agotado|sin_metodo_autorizado|fuera_de_alcance",
  "peticiones": 1, "reintentos": 0,
  "resultado_editorial": "coincidencia_verificada|ambiguo|incorrecto|null",
  "campos_evaluados": ["titulo", "editorial"],
  "campos_presentes": ["titulo"],
  "campos_ausentes": ["editorial"],
  "candidatos": [{"rank": 1, "id_externo": "…", "etiqueta_propuesta": "…", "veredicto": "…"}],
  "revision": {"verificador": "id", "fecha": "…", "veredicto": "…", "evidencia": "…"},
  "desacuerdo": null,
  "condiciones": {"fecha": "…", "red": "fixture|real", "fuentes_encendidas": ["…"], "presupuesto": 80,
                  "parada": "presupuesto|limite_de_cortesia|final"},
  "hash_respuesta": "sha256:…",
  "notas": ""
}
```

### 4.2 Separación obligatoria

- **Resultado técnico de la petición** (`estado_tecnico`): `ok`, `sin_resultados`, `fallo_transitorio`,
  `limite_de_cortesia` o `no_ejecutado`. Los cuatro primeros son los de #133; `no_ejecutado` es **solo del
  banco** (no se añade a `ESTADOS_DE_FUENTE` ni a la app) y exige `motivo_no_ejecutado`: sin autorización,
  modo seco, fuente apagada, configuración incompleta, presupuesto agotado, sin método autorizado o fuera de
  alcance.
- **Estado de fuente #133** (`estado_fuente_133`): se rellena cuando la fuente se ha evaluado o
  precomprobado; usa el conjunto cerrado de #133 (`ok`, `sin_resultados`, `fallo_transitorio`,
  `limite_de_cortesia`, `configuracion_incompleta`, `fuente_apagada`). Así una fuente apagada o incompleta
  queda como `no_ejecutado` **y** conserva la causa de #133, sin inventar un estado nuevo en #133 ni colapsar
  ambos conceptos. En una petición ejecutada, `estado_fuente_133` refleja el mismo resultado técnico.
- **Resultado editorial** = `coincidencia_verificada`, `ambiguo`, `incorrecto`, o `null` cuando no hay
  respuesta evaluable (`no_ejecutado`, `fallo_transitorio`, `limite_de_cortesia`, `configuracion_incompleta`,
  `fuente_apagada`, `sin_resultados`). Una `sin_resultados` es **ausencia**, no `incorrecto`.
- **`campo_ausente`** es una lista por campo, compatible con cualquier resultado editorial; no invalida la
  coincidencia de otros campos.
- **Un error técnico no es ausencia de cobertura:** no entra en el denominador editorial (§5), se informa
  como error/disponibilidad.

### 4.3 Evidencia y condiciones

Cada línea enlaza corpus (`caso_id`, versión), método, SHA del ejecutor, fecha/condiciones, autorización,
estado, revisión y `hash_respuesta` (hash del cuerpo saneado; no el cuerpo). Sin URL, query, API key,
cabeceras ni datos personales (§8). El registro es append-only; una corrección abre una nueva línea con
`motivo_correccion`, no edita la anterior.

---

## 5. Métricas con denominadores

Notación por **fuente × capacidad × unidad** (nunca una cifra única agregada):

| Métrica | Numerador / denominador | Qué mide | Regla |
|---|---|---|---|
| `planificados` | casos × celdas con método autorizado (`S`/`P`) | universo del ensayo | excluye `—` y `n/a`; separa acreditados/no acreditados |
| `ejecutados` | ensayos con petición | intentos reales | no incluye `no_ejecutado` |
| `no_ejecutados` | por motivo | ausencia de ejecución | **nunca** cuenta como falta de cobertura |
| `respuestas_ok` | `estado_tecnico=ok` | disponibilidad técnica | — |
| `sin_resultados` | `sin_resultados` | ausencias de candidato | no es `incorrecto` |
| `errores` | `fallo_transitorio` + `limite_de_cortesia` | fallos de una petición | los que no llegaron a pedir van en `no_ejecutados` |
| `evaluables` | `ok` o `sin_resultados`, con etiqueta acreditada y revisión | universo editorial | la precisión usa solo `ok` |
| `coincidencias_verificadas` | `coincidencia_verificada` | acierto editorial | solo etiqueta acreditada |
| `ambiguos` / `incorrectos` | sus resultados | precisión | ambos en el denominador |
| `ausencias` | `sin_resultados` con etiqueta acreditada | no encontró | no es error |
| `no_acreditadas` | casos con `identidad_acreditada=false` ejecutados | no suman a coincidencias | informa aparte |
| `campos_faltantes` | campos ausentes / campos evaluados | completitud | por campo y fuente |

**Fórmulas (solo si el denominador es válido):**

- `disponibilidad_tecnica = respuestas_ok / ejecutados` — **no** es cobertura.
- `precision_editorial = coincidencias / (coincidencias + ambiguos + incorrectos)` — sobre `ok` evaluables.
- `cobertura_editorial_verificada = coincidencias / (coincidencias + ambiguos + incorrectos + ausencias)`
  — sobre casos acreditados con respuesta válida (`ok` o `sin_resultados`); **excluye** `no_ejecutado`,
  errores técnicos y etiquetas no acreditadas (que se informan aparte).
- `tasa_campo = (campos_evaluados - campos_faltantes) / campos_evaluados`, por campo.
- `tasa_ausencia = ausencias / respuestas_ok`, por fuente/unidad.

**Reglas:** ningún porcentaje con denominador 0; con n < 10 se publican **cantidades**, no porcentajes;
no se agregan unidades distintas ni se llama «cobertura» a `disponibilidad_tecnica`; no se cuenta un
`NOT RUN` como ausencia. Toda tabla muestra numerador y denominador junto al porcentaje (criterio 6).

---

## 6. Arnés `scripts/medicion/banco_cobertura.py` (contrato)

### 6.1 Modos y autorización

| Modo | Qué hace | Red | Resultado de cobertura |
|---|---|---|---|
| `--seco` | Carga fixtures grabados/sintéticos versionados; ejecuta parser, registro y métricas | **cero** | `NOT RUN`/no acredita |
| `--real --autorizacion <id>` | Usa los clientes autorizados y `pedir_con_cortesia` (#134) | sí, solo con permiso | evaluable tras revisión humana |

- `--seco` y `--real` son **excluyentes y obligatorios**: sin modo, el arnés no arranca.
- `--real` exige un **registro de autorización** versionado en
  `docs/design/banco-cobertura/autorizacion-<id>.json` con: `id`, `ambito` (fuentes/capacidades),
  `presupuesto_peticiones`, `desde`, `hasta`, `concede` (persona), `condiciones` y `sha_corpus`. Sin
  registro válido, caducado o fuera de ámbito: **exit 2, cero peticiones**, y el informe nace con todas las
  filas `no_ejecutado: sin_autorizacion`. No se deduce permiso de que la fuente esté encendida.
- El arnés **no** enciende fuentes, no escribe `.env`, no cambia Ajustes, no toca base de datos ni corpus y
  no instala nada. Solo escribe su salida (`docs/design/medicion-cobertura-<fecha>/`).
- Flags: `--corpus`, `--fuentes`, `--unidades`, `--casos`, `--max-peticiones`, `--max-por-fuente`,
  `--salida`, `--seco|--real`, `--autorizacion`, `--revision <fichero>` (veredictos humanos).
- Presupuesto inicial propuesto para el piloto: **12 casos** (subconjunto estratificado de v1),
  **máx. 80 peticiones** y **máx. 20 por fuente**; secuencial, sin concurrencia propia (la cortesía de
  #134 ya coordina). El corpus completo de 30 casos es otra ejecución autorizada.

### 6.2 Flujo de un ensayo real

1. Comprobar autorización y ámbito; cargar corpus congelado y `sha_corpus`.
2. Para cada caso/fuente/unidad con método autorizado: comprobar fuente encendida y configuración completa
   **antes** de instanciar (sin tráfico si falta); si no, fila `no_ejecutado` con motivo `fuente_apagada` o
   `configuracion_incompleta` y `estado_fuente_133` correspondiente.
3. Llamar al método autorizado del cliente (nunca a la web, nunca a un cliente sin cortesía). Mapear
   excepción de #134/HTTP a estado de #133 según §1.3. No se añaden reintentos fuera de la política de
   #134; no se compensa con tráfico.
4. Guardar candidatos y campos presentes/ausentes; **no** emitir veredicto editorial automático. El
   resultado editorial se completa con la revisión humana (§9).
5. Parar por presupuesto, `limite_de_cortesia`, fuente apagada/configuración incompleta, autorización
   caducada o 3 fallos transitorios consecutivos de una fuente. Guardar informe parcial con `NOT RUN`.
6. Escribir JSONL, resumen JSON y Markdown; exit 0 si el ensayo terminó (aunque haya resultados negativos),
   1 si el arnés o el informe no validan, 2 si faltó permiso/configuración.

### 6.3 Modo `--seco` (validación del arnés)

- Fixtures en `docs/design/banco-cobertura/fixtures/v1/<fuente>/<metodo>/<caso>.json`: respuestas
  **saneadas** (sin claves, sin URL, sin datos privados), más fixtures sintéticos de error (red, 429,
  transitorio, apagada, configuración incompleta) para ejercitar todos los estados de #133.
- No construye clientes ni llama a `pedir_con_cortesia`: una prueba debe fallar si se intenta. No hay
  sockets, ni DNS, ni `.env`.
- Ejecuta parser, clasificación, registro y métricas; valida el esquema del corpus y del registro.
- Todo resultado de cobertura es **`NOT RUN`**: el informe `--seco` demuestra el arnés, no la cobertura
  (criterio 9). Un `--seco` con cobertura «PASS» es un fallo del banco.

### 6.4 Pruebas del arnés (en el PR que lo implemente)

`tests/test_banco_cobertura.py` (sin Postgres, sin red y **sin dependencias nuevas**: solo stdlib y `httpx`,
ya presente): corpus inválido rechazado; `--seco` no toca red;
fixtures de los 6 estados + `no_ejecutado`; `--real` sin autorización → exit 2 y cero peticiones; con
autorización caducada/fuera de ámbito → igual; mapeo de excepciones de #134 a #133; métricas con
denominadores (incluye n=0 y n<10); registro sin URL/query/clave; informe con cobertura `NOT RUN` en seco;
parada por presupuesto/límite; corpus y registro con `sha` correcto.

---

## 7. Informe

Salida: `docs/design/medicion-cobertura-<fecha>.md` + `.json` (mismos datos, legible y máquina). El formato de
PASS/FAIL/NOT RUN sigue el precedente de `docs/design/verificacion-cortesia-9-criterios.md` (matriz separada,
NOT RUN transversal, sin contar como PASS).

| Sección | Contenido |
|---|---|
| Cabecera | SHA ejecutor, versión del corpus y su `sha`, id/ámbito de autorización, modo, fecha, fuentes encendidas, presupuesto y condiciones |
| Alcance | qué se ejecutó y qué no; `NO EJECUTADO` por motivo |
| Matriz | fuente × unidad; estados técnicos y resultados editoriales por separado; campos faltantes |
| Métricas | tablas de §5 con numerador, denominador y porcentaje cuando proceda; **sin** cifra única de cobertura |
| PASS / FAIL / NOT RUN | por criterio del issue y por prueba; separados de los resultados editoriales |
| Demostrado / ambiguo / pendiente | qué se puede afirmar y con qué evidencia; qué queda abierto |
| Límites de generalización | corpus intencional (no aleatorio), 30 casos, una instalación, fecha, fuentes cambiantes, revisión simple si no hubo segunda |
| Evidencia | índice de casos, hashes, revisores; sin secretos |
| Cierre | **no** activa fuentes, **no** autoriza integración, **no** cambia reglas de producto |

Reglas: un `NOT RUN` no es `FAIL` ni ausencia; una métrica editorial no se mezcla con disponibilidad
técnica; el informe `--seco` declara cobertura `NOT RUN`; sin ejecución real + revisión humana no se dice
«cobertura verificada» (criterios 9 y 10).

---

## 8. Privacidad y legalidad

- **Sin secretos:** ni API keys, ni `.env`, ni cookies, ni cabeceras de autenticación en corpus, fixtures,
  registro, JSONL, informe ni logs.
- **Sin datos privados:** corpus con datos bibliográficos públicos/copia propia; sin nombres, direcciones,
  compras ni rutas del coleccionista; identificadores de caso, no títulos si el título es privado (se puede
  usar el título de la obra publicada).
- **Evidencia saneada:** solo `caso_id`, fuente, método, estados, códigos, hashes y referencias públicas;
  nunca URL completa, query, `Location` ni cuerpo de respuesta (los fixtures guardan solo lo necesario para
  el parser, con datos públicos).
- **Legal:** solo métodos autorizados y fuentes encendidas; sin scraping no autorizado; sin activar
  conectores; respeto de `LEGAL.md` y de las licencias de las fuentes; las portadas/sinopsis no se
  redistribuyen en el informe.
- **Derecho de revisión:** el PO puede retirar casos del corpus si su publicación compromete privacidad o
  legalidad; se registra la retirada y se recalcula.

---

## 9. Validación humana y criterio de parada

### 9.1 Roles

| Rol | Qué hace | Qué no hace |
|---|---|---|
| Ejecutor | lanza el arnés y produce registros; no decide identidad | no etiqueta coincidencias |
| Verificador editorial | etiqueta corpus con evidencia y evalúa candidatos | no usa la salida de la fuente como verdad |
| Segundo verificador | revisa ambiguos/desacuerdos; si no existe, se declara `revision_simple` | no fuerza el éxito |
| PO | aprueba corpus, autorización, presupuesto y cierre del informe | no convierte el banco en regla de producto |

### 9.2 Proceso

1. **Antes:** corpus congelado y etiquetado; matriz y métodos aceptados; autorización y presupuesto
   aprobados; revisores designados.
2. **Durante:** el ejecutor no ve la etiqueta al lanzar (para no sesgar el parser); los candidatos se
   revisan después por el verificador, con la etiqueta a la vista y evidencia documentada.
3. **Después:** cada candidato es `coincidencia_verificada`, `ambiguo` o `incorrecto`; los campos se marcan
   presentes/ausentes; los desacuerdos van al segundo verificador; los no resueltos quedan como
   `no_acreditada`. No se ajusta el corpus a posteriori.
4. **Cierre:** el informe solo usa resultados con revisión; lo pendiente es `NOT RUN`/`PENDIENTE`, no PASS.

### 9.3 Parada y presupuesto

- Parar **antes de cualquier petición** si no hay autorización válida o presupuesto > 0.
- Parar la ejecución al agotar `max_peticiones`/`max-por-fuente`, al recibir `limite_de_cortesia` de una
  fuente, si la fuente se apaga o queda incompleta, si la autorización caduca o si hay 3 fallos
  transitorios consecutivos de una fuente.
- **No compensar** el tiempo perdido con más tráfico ni saltarse #134; no reintentar fuera de su política.
- Guardar informe parcial con `NOT RUN` y motivo; reanudar exige nueva autorización, no reutilizar la
  agotada.
- El respeto de cortesía de #134 es condición de parada, no un detalle de implementación.

---

## 10. Criterios de aceptación (Given/When/Then)

**AC-01 (criterio 1) — unidades separadas.** Given la matriz, When se prepara, Then serie, edición,
publicación, número, formato y campo se miden e informan por separado; un acierto de serie no cuenta como
edición; no hay porcentaje agregado entre unidades. *Verificación: inspección de la matriz + prueba del
informe (tablas separadas).*

**AC-02 (criterio 2) — corpus con identidad.** Given el corpus, When se usa, Then constan tamaño, selección,
procedencia, unidad esperada y verificador; un caso `identidad_acreditada=false` se marca y **no** suma a
`coincidencia_verificada`; no se edita una etiqueta congelada. *Verificación: validación del esquema + caso
sintético de etiqueta no acreditada.*

**AC-03 (criterio 3) — capacidad y método.** Given una fuente, When se prepara un ensayo, Then se registra
la capacidad y el método autorizado; `—` produce `no_ejecutado: sin_metodo_autorizado` y una capacidad
desconocida **no** se presenta como disponible. *Verificación: matriz + prueba de `no_ejecutado`.*

**AC-04 (criterio 4) — la web no acredita.** Given un dato visible en la web, When se evalúa, Then solo
cuenta la respuesta real del método autorizado; ningún campo de la matriz se justifica por la interfaz web.
*Verificación: revisión de la matriz y de las citas de código.*

**AC-05 (criterio 5) — técnico ≠ editorial.** Given un ensayo, When se registra, Then `estado_tecnico` es
`ok`/`sin_resultados`/`fallo_transitorio`/`limite_de_cortesia` (de #133) o `no_ejecutado` con motivo (solo
banco), `estado_fuente_133` conserva la causa cuando aplica, y el editorial es
`coincidencia_verificada|ambiguo|incorrecto|null`; `campo_ausente` va por campo y puede coexistir con la
coincidencia; un fallo técnico no se cuenta como ausencia de cobertura. *Verificación: esquema + fixtures de
los estados + ejemplo de campo ausente con coincidencia.*

**AC-06 (criterio 6) — métricas con denominadores.** Given el informe, When calcula, Then muestra
planificados, ejecutados, evaluables, coincidencias, ambiguos, incorrectos, ausencias, campos faltantes,
errores y no ejecutados; cada porcentaje lleva su denominador; no mezcla precisión editorial con
disponibilidad técnica; no publica porcentaje con denominador 0 y usa cantidades si n<10. *Verificación:
prueba de métricas con n=0 y n<10.*

**AC-07 (criterio 7) — coincidencia verificada.** Given una candidata, When cuenta como coincidencia, Then
se contrasta con la etiqueta acreditada o con revisión humana documentada; la similitud textual o una
respuesta sintética **no** acreditan; los desacuerdos se registran sin forzar éxito. *Verificación: registro
de revisión + caso de desacuerdo.*

**AC-08 (criterio 8) — autorización, cortesía y estados.** Given un ensayo real, When se ejecuta, Then exige
autorización y aplica #134 y #133; sin permiso, fuente apagada o configuración incompleta queda
`no_ejecutado` con su motivo y `estado_fuente_133` **sin petición**; al alcanzar cortesía se detiene o
difiere, sin tráfico adicional. *Verificación: pruebas de fail-closed y de parada.*

**AC-09 (criterio 9) — evidencia.** Given una ejecución, When se documenta, Then enlaza corpus, método,
fecha, SHA, condiciones y evidencia saneada; un `--seco` con sintéticos valida el arnés pero declara
cobertura `NOT RUN`. *Verificación: dos informes (`seco` y `real`) con metadatos.*

**AC-10 (criterio 10) — informe honesto.** Given el banco terminado, When se revisa, Then separa
PASS/FAIL/NOT RUN de los resultados de cobertura, dice qué está demostrado, ambiguo o pendiente y sus
límites; no activa fuentes ni autoriza integración o despliegue; sin ejecución real no declara cobertura
verificada; cualquier recorte exige aprobación. *Verificación: inspección del informe + pruebas de que no
hay activación ni escritura fuera de la salida.*

**AC-11 — `--seco` sin red y sin cobertura.** Given el modo seco, When se ejecuta, Then no construye
clientes ni llama a `pedir_con_cortesia`, no hay sockets/DNS y toda celda de cobertura es `NOT RUN`.
*Verificación: prueba con un doble que falla si se toca la red.*

**AC-12 — fail-closed sin permiso.** Given `--real` sin autorización válida/caducada/fuera de ámbito, When
arranca, Then exit 2, cero peticiones y filas `no_ejecutado: sin_autorizacion`. *Verificación: pytest.*

**AC-13 — privacidad.** Given corpus, fixtures, registro e informe, When se inspeccionan, Then no hay API
keys, credenciales, URL completa, query ni datos personales; solo evidencia saneada. *Verificación: prueba
de centinelas.*

**AC-14 — parada.** Given presupuesto agotado, `limite_de_cortesia`, fuente apagada o 3 fallos
transitorios, When ocurre, Then la ejecución se detiene, se guarda informe parcial `NOT RUN` y no se
compensa con tráfico. *Verificación: pruebas de parada.*

---

## 11. Plan de PRs y corte preparación/ejecución

Se confirma el corte previsto en el issue: **no cabe en una sola entrega**.

| PR | Contenido | Depende de |
|---|---|---|
| **PR-1** | Esta spec + corpus `v1` (30 casos) + etiquetas + manifiesto `sha256` + plantilla de autorización + fixtures saneados + plantilla de informe | — |
| **PR-2** | `scripts/medicion/banco_cobertura.py` en modo `--seco` + `tests/test_banco_cobertura.py` + informe de validación del arnés (cobertura `NOT RUN`) | PR-1 |
| **PR-3** | **Ejecución real autorizada + revisión humana + informe de cobertura.** No se abre sin permiso separado, autorización con presupuesto y revisores designados. Sin permiso, PR-3 no existe y el resultado sigue `NOT RUN`. | PR-1/PR-2 + permiso del PO |

Reglas: PR-1 y PR-2 no hacen ninguna petición externa. PR-3 no activa fuentes ni convierte la evaluación
en regla de producto. Si la estimación de preparación no cabe, se puede partir PR-1 en (documento+esquema)
y (corpus+etiquetas+fixtures); la ejecución nunca se adelanta a la preparación.

---

## 12. Fuera de alcance (explícito)

- **Ejecución real en esta entrega**: no autorizada; cobertura `NOT RUN`.
- Activar fuentes o conectores; cambiar Ajustes o `.env`; scraping no autorizado.
- Añadir fuentes masivamente; evaluar foro o portadas como fuentes editoriales (no lo son: el foro es un
  plugin de descargas y las portadas son imágenes, no identidad).
- Reglas automáticas de identidad o de selección de fuente; cambios de producto.
- Migraciones, despliegue, cambios en #133/#134, UI nueva, coordinación entre instalaciones.
- Declarar cobertura a partir de respuestas sintéticas, de la web o de una sola fuente.
- Publicar datos privados o redistribuir contenido de las fuentes.

---

## 13. Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| R-01 | Corpus sesgado o circular (etiqueta tomada de la fuente evaluada) | procedencia obligatoria, `dependiente_de_la_fuente` excluido, etiqueta antes de ejecutar |
| R-02 | n pequeño produce porcentajes engañosos | cantidades si n<10; sin cifra única; límites de generalización en el informe |
| R-03 | Identidad editorial ambigua y «edición» sin entidad | vocabulario ADR 0003, marcar `ambiguo`, no inventar entidad |
| R-04 | Ejecución accidental sin permiso | modo obligatorio, autorización con ámbito/caducidad, fail-closed, prueba |
| R-05 | `--seco` toca red por error | prohibido instanciar clientes; prueba que falla si se intenta |
| R-06 | Privacidad/secretos en fixtures o informe | saneado, lista blanca de campos, centinelas, revisión |
| R-07 | Las fuentes cambian entre preparación y ejecución | fecha/SHA, corpus congelado, revalidar antes de PR-3 |
| R-08 | Coste/cortesía en la ejecución | presupuesto 80/20, secuencial, parada por límite, #134 |
| R-09 | Métricas mezcladas (técnico/editorial) | tablas separadas y fórmulas con denominador explícito |
| R-10 | Revisión humana insuficiente | dos revisores para desacuerdos; si no, `revision_simple` y no «verificada» |
| R-11 | Copyright de fixtures/sinopsis | fixtures mínimos y saneados; no se publica contenido de las fuentes |
| R-12 | La ejecución real no cabe en presupuesto | piloto 12 casos primero; corpus completo en otra autorización |

---

## 14. Trazabilidad criterio → AC → artefacto

| Criterio #135 | AC | Artefacto |
|---|---|---|
| 1. Serie/edición/publicación/número/formato/campo separados | AC-01 | §2.1-2.4; informe |
| 2. Corpus con identidad acreditada; sin identidad no cuenta | AC-02 | §3; corpus v1 |
| 3. Capacidad y método autorizados; desconocida no disponible | AC-03 | §2.2-2.3 |
| 4. La web no acredita campos | AC-04 | §2.2/2.4 |
| 5. Técnico ≠ editorial; `campo_ausente` | AC-05 | §4; esquema JSONL |
| 6. Métricas con denominadores; sin mezclar | AC-06 | §5 |
| 7. Coincidencia = etiqueta/revisión humana | AC-07 | §3.4, §9; registro de revisión |
| 8. Autorización, #134 y #133; sin permiso no hay petición | AC-08, AC-12, AC-14 | §1.2-1.3, §6, §9.3 |
| 9. Evidencia con fecha/SHA/condiciones; sintético no acredita | AC-09, AC-11 | §4.3, §6.3, §7 |
| 10. PASS/FAIL/NOT RUN; no activa ni integra | AC-10, AC-13 | §7, §12 |

---

## 15. Auto-revisión

- [x] **Los 10 criterios** tienen AC y artefacto (§14); el criterio 9 (evidencia) incluye la trampa del
      sintético; el 10 impide declarar cobertura sin ejecución autorizada.
- [x] **Diseño, no ejecución:** esta entrega no hace peticiones, no activa fuentes y no escribe en el árbol
      principal; cobertura `NOT RUN` declarada en §0, §6.3 y §7.
- [x] **Reutiliza contratos:** estados #133 (`services/discovery.py:60-66,87-105,200-260`), cortesía #134
      (`utils/peticiones.py:52-88,228`; `utils/cortesia.py:169,206,229,486`), vocabulario ADR 0003 y
      dimensiones #111; no duplica ni cambia #133/#134.
- [x] **Matriz separada** por unidad y con métodos autorizados citados; `—` no se disfraza de «no soportada».
- [x] **Métricas verificables:** cada una con numerador/denominador y reglas de n; no hay porcentaje sin
      base ni mezcla técnico/editorial.
- [x] **Privacidad:** sin secretos, URL, query ni datos personales; fixtures saneados y centinelas en pruebas.
- [x] **Corte de entrega:** preparación PR-1/PR-2, ejecución PR-3 con permiso separado (§11).
- [x] **Tebeosfera/foro/portadas:** no se evalúan como fuentes editoriales; Tebeosfera no se toca.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-06 | v1.0 | Preparación del banco de #135 sobre #111/#133/#134 y ADR 0003: matriz, corpus, registro, métricas, arnés `--seco`, informe, privacidad, validación humana, parada y PRs. Ejecución real: `NOT RUN`, pendiente de permiso separado. |
