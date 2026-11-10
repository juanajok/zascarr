# Especificación — MIT-M7: Contexto declarado y reutilizable (#110, #130, #131, #132)

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migraciones, no
> ejecuta pruebas y no toca fuentes ni archivos.** Las citas de código se han contrastado en
> `origin/main` **`3a8b506`** (2026-11-10; worktree `.squad/wt-110-spec`). El encargo citaba
> `e1b4f30`; `origin/main` había avanzado: donde cambie una línea, manda `3a8b506`.
> **Alcance documental:** #130 (US01, declarar significado de carpeta), #131 (US02, correspondencia
> local versionada) y #132 (US03, inventario y administración). **No se implementa ninguna.**
> **Decide el PO.** Lo que es decisión de modelo se marca **PO**; lo demás es contrato.

---

## 0. Resumen para el PO

Hoy la carpeta **solo se interpreta al vuelo**: `core/carpetas.py` separa título/año/volumen de su
nombre; `RevisionCarpetas` agrupa los pendientes por ruta y `DescubrimientoDeGrupo` (M3) reutiliza ese
grupo para proponer una búsqueda. **No hay modelo, tabla, servicio, ruta ni pantalla que guarde qué
significa una carpeta, con qué alcance, ni qué destino se le asocia.** El único aprendizaje persistente
es `LocalAlias` (B13): `pattern_norm → series_id`, global, automático, sin ámbito, estado ni versión.

**Se propone:**

1. **Dos tablas nuevas**, no una: `declaraciones_carpeta` (#130) y `correspondencias_contexto` (#131).
   La primera dice qué significa una carpeta y hasta dónde alcanza; la segunda ata **una versión
   concreta** de esa declaración a un destino existente. Una correspondencia sin declaración no existe;
   una declaración sin correspondencia sí (solo orienta).
2. **Versionado por filas temporales**: cada cambio semántico o de ciclo de vida inserta una versión
   nueva (`version` monótona) y cierra la anterior (`vigente_hasta`). No se hace `UPDATE` destructivo ni
   se borra historial. La propuesta lleva `correspondencia_id` y `version_de_regla`.
3. **Alcance explícito**: `contexto_raiz` (ruta relativa normalizada), `incluir_descendientes` (bool) y
   `tipo_de_registro` (opcional) se guardan en la declaración/correspondencia y se muestran siempre.
   Una ampliación de alcance exige versión nueva y confirmación; nunca se hereda por parecido de nombre.
4. **Función de evaluación de solo lectura** que devuelve exactamente uno de los seis estados de #131
   AC6, con IDs y versiones de las reglas, o `propuesta_disponible` con la propuesta trazable.
5. **Precedencia explícita**: local confirmada > alias de importación > alias aprendido B13; las
   correspondencias entre sí no tienen precedencia: si dos reglas activas aplican con destinos
   distintos, `conflicto_de_correspondencias`. B13 no se toca; no se convierte en declaración.
6. **Cero efectos laterales**: crear, cambiar, desactivar o retirar una regla no vincula, no crea
   series, no enriquece, no mueve/renombra/borra archivos y no reescribe decisiones ya confirmadas.

**Decisión de escala:** #130 M (5), #131 L (8, partido en dos PR revisables), #132 M (5). Orden
obligatorio #130 → #131 → #132 (§7). La migración es aditiva y no rellena datos.

---

## 1. Contraste real: qué hay de «contexto de carpeta» hoy

### 1.1 Lo que existe, y dónde se consume

| Pieza | Qué hace | Dónde | Qué **no** hace |
|---|---|---|---|
| **Heurística de nombre de carpeta** | Separa título, año, volumen y calificadores; lista fija de contenedores (`_*`, «varios», «omnibus»…) | `core/carpetas.py:18-40` (`CONTENEDORES`, `es_contenedor`), `:59-113` (`CarpetaLimpia`, `analizar_carpeta`), `:116-138` (`RutaDividida`, `dividir_ruta`) | No guarda nada, no conoce la intención de la persona, no distingue autor/publicación por declaración |
| **Agrupación por carpeta** | Agrupa los pendientes por ruta y calcula el «contexto» = primera carpeta no contenedora; propone serie con `metadata.candidates` y señales de conflicto | `services/revision_carpetas.py:306-315` (`_carpetas_de`), `:449-458` (`archivos_del_grupo`), `:573-610` (`_grupo`), `:645-728` (`_senales`), `:776+` (`senales_contra_serie`) | Es **solo lectura**; se recalcula en cada petición; no persiste significado, alcance ni versión; no conoce correspondencia con destino |
| **Pantalla de carpetas** | Lista y filtra grupos; no ofrece acciones | `web/pendientes.py:382-439`; contrato de «solo lectura» en el docstring | No crea series, no vincula, no mueve; no hay declaración ni destino |
| **Asistente M3 (#106/#118)** | Abre un grupo, propone una consulta y busca candidatas; usa el mismo grupo y `analizar_carpeta` | `services/descubrimiento_grupo.py:298-360` (`_contexto`, `_consulta_propuesta`), `web/asistente_carpetas.py:1-15` | No persiste contexto; no asocia un destino; no recuerda entre sesiones |
| **Matcher de nombres** | Decide serie/número por ComicInfo o nombre; consulta el alias B13 antes del fuzzy | `core/matcher.py:131`, `:286-320`, `:216-235` | **No ve la carpeta** (`triage.path.name` es lo único que recibe); no usa declaración ni correspondencia |
| **Alias aprendido B13** | `pattern_norm → series_id`, único global, aprendido al asignar a mano; lo leen matcher e orquestador | Modelo `models/__init__.py:912-928`; aprendizaje `services/review.py:327-349`, `services/asignacion.py:590-591`; lectura `core/matcher.py:216-235,313-318`; orquestador `services/orchestrator.py:323-334,585-637` | Sin ámbito de carpeta, sin estado, sin versión, sin origen, sin UI de gestión; la última corrección sustituye la anterior |
| **Importador / adoptador** | Registran archivos y usan la ruta para destino o deducción de nombre | `services/importer.py:378-440`; `services/library_adopter.py:1-13` | La carpeta no es una declaración semántica: es ubicación o pista de nombre |
| **Contexto de navegación #286** | URL de vuelta a Biblioteca/ficha | `docs/design/contexto-286.md` | Es contexto de **navegación**, no una regla de interpretación; no se mezcla con M7 |
| **Asociación de fuentes #129** | Asocia una segunda fuente externa a una serie | `docs/design/especificacion-M6-US03-asociar-fuente.md` | Es identidad externa, no una regla local carpeta → destino |

### 1.2 Lo que **no** existe (verificado por búsqueda)

- **No hay** `declaraciones_carpeta`, `correspondencias_contexto` ni equivalentes: `grep -RIn
  'declaracion|declaración|correspondencia' src/zascarr` solo devuelve comentarios de
  `services/borrado_serie.py` y `services/runtime_settings.py`, ajenos a esta feature.
- **No hay** tabla, columna, enum, servicio, ruta ni plantilla de declaración o correspondencia.
- **No hay** «alias de importación» como entidad: el único alias persistente es `local_aliases`
  (B13), aprendido de asignaciones manuales, no importado.
- **No hay** gestión de alias: ni listado, ni desactivación, ni retirada, ni activación con
  consentimiento; la ficha de #132 describe exactamente ese hueco.

### 1.3 Por qué no basta con lo que hay

1. **La interpretación es efímera y heurística.** `analizar_carpeta` y `_grupo` vuelven a deducir el
   significado en cada consulta; no hay una decisión de la persona que sobreviva. Un cambio de nombre
   de carpeta cambia el grupo y la sugerencia sin que nadie lo haya decidido.
2. **No hay alcance declarado.** «La carpeta A es por autor» o «por publicación», y «esto incluye /
   no incluye subcarpetas y archivos futuros» no se puede expresar: `dividir_ruta` elige la primera
   carpeta no contenedora y nada más. El asistente M3 tampoco lo recuerda.
3. **No hay correspondencia con destino.** `revision_carpetas` propone a partir de candidatas guardadas
   en `metadata.candidates`; no existe una regla «esta carpeta corresponde a esta serie» con identidad,
   versión y alcance. El matcher no la consultaría.
4. **No hay versión ni ciclo de vida.** B13 se sobrescribe; una propuesta no puede quedar
   `regla_desactualizada` porque no hay `version_de_regla`. Tampoco hay desactivar/retirar.
5. **No hay conflicto visible ni precedencia contractual.** `_senales` detecta señales de conflicto de
   nombre, pero no hay reglas declaradas que compitan; el alias B13 simplemente «manda» en el matcher
   (comentario `core/matcher.py:313-318`) sin que la persona vea la decisión ni pueda desactivarla.
6. **El alias B13 no es una declaración.** Es un patrón global de título, no un contexto de carpeta; no
   tiene ámbito, estado ni versión, y su lectura está cableada en el matcher/orquestador. Usarlo como
   base de #130/#131 confundiría dos cosas: una corrección de nombre y una regla de interpretación de
   carpeta.

**Conclusión:** #130 y #131 no son un delta de B13/B14; son **modelo nuevo**. B13/B14 se reutilizan
como señales y como caso de precedencia, no como almacén de declaraciones.

---

## 2. Modelo propuesto

### 2.1 Decisión: dos tablas, no una

| Opción | Ventaja | Problema | Veredicto |
|---|---|---|---|
| **Una tabla con `tipo`** (`declaracion`/`correspondencia`) | Una migración, un ciclo de vida | Columnas nulas y estados imposibles (correspondencia sin destino, declaración con destino); mezcla dos cardinalidades; consultas y validaciones condicionales | **Descartar** |
| **Dos tablas** | Cada pieza tiene columnas obligatorias, unicidad y ciclo propios; la correspondencia referencia una versión de declaración; consultas claras | Dos migraciones/entidades y una FK | **Recomendar** |
| Tabla + JSONB | Menos esquema | Pierde FK, unicidad, índices y validación; ya hay JSONB para metadata suelta, no para reglas consultables | Descartar |

**Dos tablas**, ambas con **filas de versión** (historial en la misma tabla, no una tabla de historial
aparte). La declaración es la unidad semántica; la correspondencia es la unidad accionable.

### 2.2 Enums de Postgres (nombres y valores explícitos)

Siguiendo la regla del proyecto: `postgresql.ENUM` explícito, `values_callable` en minúsculas, nunca
`.name`.

```text
tipo_significado_carpeta: autor | publicacion
tipo_registro:            archivo | serie | publicacion
tipo_destino:             serie | publicacion
origen_regla:             local | importacion
estado_regla:             activa | desactivada | retirada
```

- **`tipo_significado_carpeta`** (PO): `autor` y `publicacion` son los dos tipos que pide #130. ¿Se
  admite `coleccion`/`otro`? Recomendación: **no en v1**; un valor comodín no aporta semántica y
  amplía la superficie de conflicto. Añadir otro tipo es una decisión explícita y una migración de
  enum (aditiva).
- **`tipo_registro`** (PO): filtro opcional del **registro local** al que la regla aplica (`archivo`,
  `serie`, `publicacion`); `NULL` = cualquiera. No es el tipo del destino; el destino tiene su propio
  `tipo_destino`.
- **`tipo_destino`** (PO): destinos existentes admitidos. Recomendación: `serie` y `publicacion`
  (existen `Series` e `Issue`); **nunca** `edicion`/`obra` (no existen como entidad, ADR 0003) ni
  creación de destino.
- **`origen_regla`**: `local` (decisión de la persona), `importacion` (regla importada/sugerida). B13
  no usa esta tabla.
- **`estado_regla`**: `activa` genera propuestas; `desactivada` no genera pero se puede reactivar;
  `retirada` es terminal y no se reactiva (una reanudación crea una identidad nueva).

### 2.3 `declaraciones_carpeta` (#130)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `uuid` PK | Identidad de **esta versión** |
| `declaracion_id` | `uuid NOT NULL` | Identidad **estable** de la declaración (todas sus versiones) |
| `version` | `integer NOT NULL` | 1..n; monótona por `declaracion_id` |
| `contexto_raiz` | `text NOT NULL` | Ruta relativa normalizada a la biblioteca; sin `/` inicial, sin `.`/`..`, sin barra final; no vacía; no la raíz de la biblioteca (PO). NFC; **distingue mayúsculas** |
| `incluir_descendientes` | `boolean NOT NULL` | Si la regla alcanza subcarpetas; por defecto `false` |
| `tipo_de_significado` | `tipo_significado_carpeta NOT NULL` | `autor` o `publicacion` |
| `origen` | `origen_regla NOT NULL` | `local` (persona); `importacion` (regla importada) |
| `estado` | `estado_regla NOT NULL` | Estado de la versión vigente |
| `vigente_desde` | `timestamptz NOT NULL` | Inicio de vigencia de esta versión |
| `vigente_hasta` | `timestamptz NULL` | `NULL` = versión vigente; se cierra al crear la siguiente |
| `procedencia` | `jsonb NOT NULL DEFAULT '{}'` | `operacion_id`, `fecha`, `origen`, evidencia saneada; sin usuario/sesión/IP |
| `creado_en` | `timestamptz NOT NULL` | Solo metadato |

**Unicidad e índices:**

```sql
UNIQUE (declaracion_id, version)
UNIQUE (declaracion_id) WHERE vigente_hasta IS NULL              -- una versión vigente
UNIQUE (contexto_raiz)  WHERE vigente_hasta IS NULL
                          AND origen = 'local' AND estado = 'activa'  -- una local activa por raíz
INDEX (contexto_raiz)
INDEX (vigente_hasta)
```

- La unicidad parcial de `contexto_raiz` evita dos declaraciones **locales activas** con significados
  distintos en la misma carpeta. Una local y una importada pueden coexistir: el conflicto es visible y
  la precedencia de §4 decide, sin que la importada sobrescriba.
- `contexto_raiz` es **inmutable por `declaracion_id`**: cambiar de carpeta es crear otra declaración y
  retirar la anterior, no una versión nueva. La aplicación lo exige; no se puede expresar como `UNIQUE`.
- **Raíz de biblioteca:** recomendación **prohibida** (una declaración de raíz con descendientes
  abarcaría todo y ampliaría el alcance de golpe). Si el PO la quiere, exige confirmación y queda
  marcada como global.
- `nombre_visible`: **no se guarda**; la UI usa la ruta. Así no hay un campo cosmético que fuerce una
  versión nueva ni una etiqueta que se confunda con identidad.

### 2.4 `correspondencias_contexto` (#131)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `uuid` PK | Identidad de **esta versión** |
| `correspondencia_id` | `uuid NOT NULL` | Identidad **estable** de la correspondencia |
| `version` | `integer NOT NULL` | 1..n; **`version_de_regla`** que viaja en la propuesta |
| `declaracion_version_id` | `uuid NOT NULL REFERENCES declaraciones_carpeta(id) ON DELETE RESTRICT` | Versión **exacta** de la declaración sobre la que se construyó (`declaraciones_carpeta.id`); la identidad estable se obtiene de esa fila |
| `contexto_raiz` | `text NOT NULL` | Copia del alcance de esa versión; validada contra la declaración |
| `incluir_descendientes` | `boolean NOT NULL` | Copia del alcance; validada |
| `tipo_de_registro` | `tipo_registro NULL` | Filtro local opcional; `NULL` = cualquiera |
| `destino_tipo` | `tipo_destino NOT NULL` | `serie` o `publicacion` |
| `destino_id` | `uuid NOT NULL` | Debe existir la fila del tipo indicado; sin FK polimórfica |
| `origen` | `origen_regla NOT NULL` | `local` / `importacion` |
| `estado` | `estado_regla NOT NULL` | Ciclo de vida |
| `vigente_desde` / `vigente_hasta` | `timestamptz` | Igual que en la declaración |
| `procedencia` | `jsonb NOT NULL DEFAULT '{}'` | Evidencia y `operacion_id`; sin datos personales |
| `creado_en` | `timestamptz NOT NULL` | — |

**Unicidad e índices:**

```sql
UNIQUE (correspondencia_id, version)
UNIQUE (correspondencia_id) WHERE vigente_hasta IS NULL
INDEX (declaracion_version_id)
INDEX (contexto_raiz)
INDEX (destino_tipo, destino_id)
INDEX (vigente_hasta)
```

- **Sin FK polimórfica al destino.** `destino_tipo` + `destino_id` permiten que el destino desaparezca
  sin romper la regla; la evaluación devuelve `destino_no_disponible`. En creación se valida que la
  fila exista y sea del tipo correcto; no se crea nada.
- **La correspondencia referencia una versión concreta** de la declaración. Si la declaración cambia
  de versión, se desactiva o se retira, la correspondencia no se reescribe: la evaluación devuelve
  `regla_desactualizada` hasta que se cree una versión nueva de la correspondencia. Esto es lo que
  permite que `version_de_regla` sea comprobable.
- **Compatibilidad de significado:** una correspondencia exige una declaración
  `tipo_de_significado='publicacion'` (o el tipo que el PO admita como mapeable a un destino único);
  `autor` no puede tener correspondencia a un destino único (P8). Se rechaza al crear y, si existiera
  por datos corruptos, la evaluación devuelve `evidencia_incompatible`.
- `contexto_raiz`/`incluir_descendientes` se copian para que la regla sea autocontenida; al crear se
  valida que son iguales a la versión de declaración referenciada. Si dejan de coincidir por una
  escritura corrupta, `evidencia_incompatible` (§3.5).
- **`tipo_de_registro`** no restringe el destino: una regla `archivo → serie` o `serie → publicacion`
  son combinaciones válidas; una combinación que el contrato no admita se rechaza en creación.

### 2.5 Versionado y ciclo de vida

**Regla general:** cada cambio **semántico** (significado, alcance, destino, tipo) o de **ciclo**
(activar, desactivar, retirar) inserta una fila nueva con `version = anterior + 1`; la anterior recibe
`vigente_hasta`. No se actualizan columnas semánticas de una fila cerrada; no se borra. El historial se
lee por `declaracion_id`/`correspondencia_id` ordenado por `version`.

| Operación | Declaración (#130) | Correspondencia (#131) |
|---|---|---|
| Crear | v1 `activa` | v1 `activa`, referencia a una versión de declaración |
| Cambiar significado/alcance | v+1; confirmación si amplía alcance | v+1; cambia destino/tipo/alcance; confirmación |
| Desactivar | v+1 `desactivada` (deja de aplicar) | v+1 `desactivada` |
| Reactivar | v+1 `activa` | v+1 `activa` **solo si** la declaración referenciada sigue siendo la vigente; si no, hay que actualizar |
| Retirar | v+1 `retirada`; terminal | v+1 `retirada`; terminal; reanudar = nueva `correspondencia_id` |
| Borrar | **no existe** | **no existe** |

- **Retirada ≠ desactivación:** desactivar es reversible y conserva identidad; retirar es terminal y
  conserva historial. Ninguna de las dos toca archivos, series, vínculos ni decisiones confirmadas.
- **Ampliación de alcance:** `incluir_descendientes` de `false` a `true`, o mover `contexto_raiz`, es una
  ampliación y exige confirmación explícita y versión nueva. No se deduce del nombre ni se hereda.
- **Propuestas:** no se persisten como entidades. Una propuesta es un resultado de evaluación con
  `correspondencia_id` + `version_de_regla`; si la regla cambia, la siguiente evaluación devuelve
  `regla_desactualizada` o la versión nueva. No hay «propuesta congelada» que se aplique sin revalidar.
- **Crecimiento:** el historial es acotado por el uso (una fila por cambio); se puede consultar por
  versión. No se compacta ni se borra; no hay purga porque no es una operación con comprobante.

### 2.6 Declaración local frente a alias de importación (#130 AC6)

Hay **tres cosas distintas** y no se mezclan:

| Concepto | Dónde vive | Identidad | Estado/versión | Uso |
|---|---|---|---|---|
| **Declaración local** | `declaraciones_carpeta`, `origen='local'` | `declaracion_id` + versión | Sí | Significado y alcance de una carpeta |
| **Correspondencia local** | `correspondencias_contexto`, `origen='local'` | `correspondencia_id` + versión | Sí | Propuesta carpeta → destino |
| **Alias aprendido B13** | `local_aliases` (sin cambios) | `pattern_norm` único global | **No** | `SeriesMatcher` / orquestador; no es una declaración |
| **Alias de importación** | No existe hoy; decisión de #132 | `alias_id` (propuesto) | Sí, si se modela | Sugerencia importada; nunca es declaración local |

- **B13 no se reutiliza como declaración.** Su ámbito es el título normalizado del nombre de archivo,
  no la carpeta; no tiene `contexto_raiz`, ni `incluir_descendientes`, ni estado, ni versión. Insertarlo
  en las tablas nuevas falsearía esos campos.
- **B13 tampoco tiene hoy ciclo de vida para #132.** Para listar/desactivar/retirar alias aprendidos,
  #132 necesita añadir estado (y, si se quiere trazabilidad, versión) a `local_aliases` o envolverla en
  un modelo de alias nuevo, actualizando **los dos consumidores** (`SeriesMatcher` y orquestador) para
  filtrar `activa`; es una migración y un cambio de comportamiento que no se hace en #130/#131. P9 lo
  deja como decisión explícita.
- **Un alias importado no se presenta como decisión confirmada.** Debe llevar `origen='importacion'` y
  un estado propio (`propuesta`/`activa`, a decidir en #132); no se escribe en
  `declaraciones_carpeta`/`correspondencias_contexto` como si fuera local.
- **Recomendación de modelo (PO):** #132 añade una tabla `alias_importado` (o una tabla de alias
  unificada nueva) con `patron_norm`, destino, `origen/estado/version`; **no** se modifica la tabla
  `local_aliases` de B13, porque cambiarla afecta al matcher y al orquestador y mezclaría aprendizaje
  automático con alias importado. Si el PO prefiere extender B13, será una migración aparte con
  pruebas de regresión de esos dos consumidores. Forma mínima propuesta para esa tabla de #132:
  `id`, `alias_id` estable, `version`, `patron_norm`, `destino_tipo`, `destino_id`, `origen='importacion'`,
  `estado`, `vigente_desde/hasta`, `procedencia`; sin datos personales.
- **#130/#131 no crean alias importados.** Solo guardan `origen='local'` en sus tablas y, si en el
  futuro se importan reglas, usan `origen='importacion'` con la misma forma (sin convertirlas en
  locales).

---

## 3. Contrato de lectura y evaluación

### 3.1 Función canónica

Nueva capa de servicio (nombre propuesto `services/contexto_declarado.py`), **solo lectura** en la
evaluación:

```text
evaluar_contexto(db, registro: RegistroContextual, *, ahora=None) -> ResultadoEvaluacion
```

`RegistroContextual`:

| Campo | Tipo | Uso |
|---|---|---|
| `tipo` | `archivo \| serie \| publicacion` | Compara con `tipo_de_registro` (si la regla lo restringe) |
| `carpeta` | `str` | **Carpeta relativa normalizada que contiene el registro**; es la que se compara con `contexto_raiz`. Para un archivo, el llamador pasa su carpeta padre; no se lee el disco |
| `ruta` | `str \| None` | Ruta del registro, solo para evidencia/mensaje; no decide el alcance |
| `patron_nombre` | `str \| None` | Opcional; solo para mostrar conflicto con B13, **no** para crear propuestas |

`ResultadoEvaluacion`:

| Campo | Contenido |
|---|---|
| `estado` | Uno de los seis de §3.2 |
| `propuesta` | `Propuesta` o `None` |
| `correspondencia_id` | `uuid` de la regla aplicable, si la hay |
| `version_de_regla` | Versión de esa correspondencia |
| `declaracion_id` / `version_declaracion` | Versión exacta de la declaración usada como evidencia |
| `destino_tipo` / `destino_id` | Destino propuesto (o el que falta, en `destino_no_disponible`) |
| `alcance` | `{contexto_raiz, incluir_descendientes, tipo_de_registro}` efectivo |
| `reglas_involucradas` | Lista de `{correspondencia_id, version, origen, destino}` en conflictos/desactualizadas |
| `precedencia_aplicada` | `local`, `importacion`, `aprendido` o `None` (solo si resolvió una capa) |
| `conflicto_visible` | Alternativas de alias/B13 o de otra capa que no ganan, para no ocultarlas |
| `motivo` | Texto en español llano, sin códigos internos en superficie |

`Propuesta` (solo si `propuesta_disponible`): `correspondencia_id`, `version_de_regla`,
`declaracion_id`, `version_declaracion`, `destino_tipo`, `destino_id`, `alcance`, `origen`,
`precedencia_aplicada`, `evidencia` (IDs/versiones, sin datos personales).

### 3.2 Los seis estados (#131 AC6)

| Estado | Cuándo | Qué devuelve | Qué **no** hace |
|---|---|---|---|
| `propuesta_disponible` | Hay **una** regla vigente aplicable (tras precedencia) y el destino existe | Propuesta con IDs/versiones | No crea, vincula, mueve ni confirma |
| `fuera_de_alcance` | Ninguna declaración/regla vigente cubre la carpeta/tipo | Motivo; sin propuesta | No usa parecido de nombre ni una regla vecina |
| `destino_no_disponible` | Hay regla vigente aplicable, pero el destino no existe o no es del tipo | IDs/versión y destino ausente | No crea el destino ni elige otro |
| `conflicto_de_correspondencias` | Varias reglas **vigentes** aplicables con destinos distintos (misma capa) | Lista de reglas/versiones/destinos | No elige, no ordena por origen ni por fecha |
| `evidencia_incompatible` | La regla no es coherente con su declaración (snapshot/versión), el tipo no es admisible o la evidencia de alias se contradice sin precedencia aplicable | Reglas/evidencia y motivo | No repara, no reinterpreta, no ignora el conflicto |
| `regla_desactualizada` | Había regla aplicable, pero su correspondencia o su declaración ya no es la vigente (cambió/desactivó/retiró) | IDs y versiones antigua/vigente | No aplica la versión vieja ni la actualiza sola |

**Regla de exclusividad:** exactamente uno de los seis. `propuesta_disponible` nunca convive con un
estado de no aplicación. La lista de reglas desactualizadas puede acompañar a un estado vigente como
advertencia, pero no lo cambia.

### 3.3 Algoritmo (orden obligatorio)

1. Normalizar `registro.carpeta` (POSIX relativo, sin `/` inicial, sin `.`/`..`, NFC) y validar el tipo.
2. Cargar declaraciones **vigentes** (`vigente_hasta IS NULL`, `estado='activa'`) cuya raíz cubra esa
   carpeta y cuyo `tipo_de_significado` no sea incompatible con el registro.
3. Si no hay ninguna: si existía alguna regla aplicable pero desactualizada, `regla_desactualizada`;
   si no, `fuera_de_alcance`.
4. Cargar correspondencias **vigentes** (`vigente_hasta IS NULL`, `estado='activa'`) cuya copia de
   alcance cubra esa carpeta y cuyo `tipo_de_registro` sea `NULL` o el del registro. Una correspondencia
   cuyo tipo no coincide **no aplica**: no se convierte en conflicto ni en propuesta.
5. Para cada correspondencia, comprobar:
   - que `declaracion_version_id` sigue siendo la versión vigente de su `declaracion_id` estable y que
     está `activa`;
   - que su copia de alcance coincide con la de esa versión de declaración;
   - que el destino existe y es del tipo.
6. Aplicar **precedencia entre capas** (§4): local > importación > aprendido. Si dos reglas locales
   vigentes aplican con destinos distintos → `conflicto_de_correspondencias`; si son de la misma capa
   local y **el mismo destino**, se decide en §4 (recomendación: conflicto explícito, no fusión).
7. Si hay una ganadora y el destino existe → `propuesta_disponible`; si el destino no existe →
   `destino_no_disponible`.
8. Si la ganadora no es coherente con la declaración (snapshot/versión/tipo) → `evidencia_incompatible`.
9. La función **no escribe**; no consulta fuentes, no mira el disco y no crea series/issues.

### 3.4 Evaluación de alcance

- `incluir_descendientes = false`: aplica solo a los registros cuya `carpeta` es **exactamente**
  `contexto_raiz` (los archivos de esa carpeta, no los de subcarpetas).
- `incluir_descendientes = true`: aplica si `carpeta == raiz` o `carpeta` está bajo `raiz + "/"`.
  Comparación de segmentos, nunca `startswith` de cadena cruda (`A` no cubre `AB`).
- **Archivos futuros:** se evalúan por su `carpeta` cuando se registran; no se enumeran ni se guardan.
- **Renombrar/mover:** la carpeta es la identidad. Una carpeta movida o renombrada **no** hereda la
  declaración por parecido; la ruta antigua deja de cubrir los registros nuevos y la nueva queda fuera
  de alcance hasta que la persona cree/edite una declaración. No se sigue el inodo ni el nombre.
- **Raíz de biblioteca:** si el PO la permite, `contexto_raiz` raíz con descendientes cubre todo; se
  marca como global y exige confirmación; por defecto se rechaza.

### 3.5 `evidencia_incompatible`: casos cerrados

Para que sea verificable, no una bolsa de «algo falla»:

1. La copia de `contexto_raiz`/`incluir_descendientes` de la correspondencia no coincide con la versión
   de declaración referenciada (escritura corrupta o migración manual).
2. El destino existe, pero su tipo real no corresponde a `destino_tipo` (ID cambiado/corrupto).
3. La declaración es `autor` y la correspondencia pretende un destino único (`serie`/`publicacion`):
   un autor no identifica una serie; #130 AC4 prohíbe convertir el autor en serie. (PO puede admitir
   una excepción explícita; por defecto no.)
4. Hay un alias importado con evidencia inválida (sin `origen`/estado) que la capa de precedencia no
   puede resolver.
5. La regla referencia una versión de declaración **vigente** pero el snapshot no cuadra; si la versión
   no es la vigente, el estado es `regla_desactualizada`, no este.

### 3.6 `regla_desactualizada`: cuándo

- La correspondencia vigente referencia una `declaracion_version_id` que ya no es la versión vigente
  (la declaración cambió de significado/alcance).
- La declaración referenciada está `desactivada`/`retirada`.
- La propia correspondencia fue desactivada/retirada después de generar la propuesta.
- En todos: se devuelven `correspondencia_id`, `version_de_regla` antigua, versión vigente (si existe)
  y motivo. **No** se aplica la versión antigua; la persona debe reevaluar.
- Si conviven reglas vigentes y desactualizadas, la evaluación puede devolver la propuesta vigente y
  listar las desactualizadas como advertencia; nunca usar la desactualizada para el destino.

---

## 4. Precedencia y conflictos (AC9 de #130 y AC7 de #131)

### 4.1 Tabla de precedencia explícita

| Orden | Capa | Qué es | Cómo gana | Límite |
|---:|---|---|---|---|
| 1 | **Decisión local confirmada** | `declaraciones_carpeta`/`correspondencias_contexto` con `origen='local'` y `estado='activa'` | Es la única capa que puede producir `propuesta_disponible` local | No puede ampliar alcance ni sobrescribir un vínculo ya confirmado; solo prepara propuestas |
| 2 | **Alias de importación** | Sugerencia importada, `origen='importacion'` | Si no hay local aplicable, puede proponer (si el modelo de #132 lo permite) | Nunca sobrescribe una local; si difiere, el conflicto se muestra y la local gana |
| 3 | **Alias aprendido B13** | `local_aliases` patrón→serie aprendido en asignaciones | Es la capa de menor autoridad; no produce propuesta de contexto | Nunca sobrescribe local/importada; se muestra como alternativa/conflicto si coincide en el patrón |

**La precedencia no es implícita:** está en esta tabla, en los `origen` de las reglas y en
`precedencia_aplicada` del resultado. La interfaz no la recalcula ni decide por su cuenta; pinta la que
devuelve el servicio.

**Ámbito de esta precedencia:** rige la **propuesta de contexto y la revisión** (#130/#131/#132). No
cambia el comportamiento actual del `SeriesMatcher`, que para material entrante sigue consultando el
alias B13 antes del fuzzy (`core/matcher.py:313-318`); convertirlo en propuesta es una decisión de
#132 y no se hace desde una declaración. Que B13 sea la capa de menor autoridad aquí no lo borra ni lo
desactiva.

**Conflictos entre declaraciones:** una local activa y una importada del mismo `contexto_raiz` pueden
coexistir; la local gana y la importada queda en `conflicto_visible`. Dos importadas con significados
distintos para la misma raíz también se muestran como conflicto visible; no producen propuesta por sí
solas y no se elige una. Las declaraciones locales activas duplicadas las impide el índice único
parcial (§2.3).

### 4.2 Conflictos dentro de la misma capa

- **Dos o más correspondencias locales vigentes aplicables con destinos distintos** →
  `conflicto_de_correspondencias`; se listan todas con `correspondencia_id`, `version_de_regla`,
  destino y alcance. **No se elige** por fecha, orden de creación ni por «la más específica».
- **Dos locales con el mismo destino** (duplicado semántico): **decisión PO**. Recomendación:
  `conflicto_de_correspondencias` también, para no inventar una regla de desempate; el PO puede
  permitir coalescerlas en una sola propuesta con las dos evidencias. Si se permite, debe ser una
  regla explícita y probada, no un «la primera gana».
- **Dos importadas** aplicables: misma regla; conflicto si destinos distintos; si el PO permite
  prioridad por antigüedad, debe estar escrita y probada (no se asume).
- **Una local y una importada**: gana la local por la tabla; la importada se muestra en
  `conflicto_visible`/alternativas. No es `conflicto_de_correspondencias` porque la precedencia sí
  resuelve; se prueba que la alternativa no se aplica.

### 4.3 Alias y propuesta: qué se muestra y qué nunca se hace

- B13 **no** se convierte en correspondencia ni se escribe en las tablas nuevas. Se lee para
  **alternativas/conflicto** si el registro trae `patron_nombre`; no crea propuestas de contexto.
- Una declaración `autor` **no** produce propuestas de destino único (AC4 de #130); sirve como contexto
  de filtrado/orientación. Si la persona quiere atar una carpeta de autor a una serie, no es una
  correspondencia válida; el sistema no la inventa.
- Un alias de importación **no** activa nada por sí solo: #132 exige consentimiento independiente
  (AC6 de #132). Aceptar/guardar una declaración o correspondencia no activa el alias.
- Ninguna capa puede «extender» una regla a una subcarpeta o a un título parecido: solo la ruta y el
  alcance explícito deciden.

---

## 5. Efectos y no-efectos

### 5.1 Qué escribe cada operación

| Operación | Escribe | No escribe |
|---|---|---|
| Crear declaración | Nueva fila/versión en `declaraciones_carpeta`; `procedencia` | `Series`, `Issue`, `File`, `LocalAlias`, `metadata_source`, `locked_fields`, archivos |
| Cambiar/desactivar/reactivar/retirar declaración | Nueva versión y cierre de la anterior | Nada de lo anterior; no reejecuta propuestas |
| Crear correspondencia | Nueva fila/versión en `correspondencias_contexto` | Destino (solo referencia), series/issues, archivos |
| Cambiar/desactivar/reactivar/retirar correspondencia | Nueva versión y cierre | Destino, vínculos, archivos, B13 |
| Evaluar | **Nada** (solo lectura) | Nada; no crea, no vincula, no mueve |
| #132 listar/gestionar | Según esta tabla; consentimiento de alias en su propio modelo | Nada de archivos/series/vínculos |

### 5.2 No-efectos explícitos (AC7/AC10, AC8/AC10, AC11)

- **No se mueve, renombra, copia ni borra** ningún archivo, CBZ ni carpeta.
- **No se crea** ninguna serie, publicación, edición, obra ni destino; el destino debe existir antes.
- **No se vincula** ningún archivo ni se asigna `issue_id`; una propuesta no es una vinculación.
- **No se enriquece** ni se aplican metadatos; no se toca `metadata_source`/`locked_fields`.
- **No se revierten** vinculaciones, asignaciones ni decisiones ya confirmadas; desactivar/retirar solo
  afecta a evaluaciones nuevas.
- **No se toca B13**: no se aprende, no se reactiva, no se borra desde declaraciones/correspondencias.
- **No se consultan fuentes** ni red; no se lee el disco en evaluación (la carpeta la aporta la consulta).
- **No se aprende por similitud**: ni por nombre de carpeta, ni por título, ni por proximidad.

---

## 6. AC ↔ contrato

### 6.1 #130 (9 criterios)

| # | Criterio | Contrato | AC propuesta | PO |
|---|---|---|---|---|
| 1 | Significado declarado; sin inferencia | §2.3 `tipo_de_significado`; creación explícita; no se deriva del nombre | AC-130-1 | Enum de tipos |
| 2 | Alcance visible (carpeta, subcarpetas, futuros, herencia) | §2.3/§3.4; se muestran `contexto_raiz`, `incluir_descendientes`, `tipo_de_registro`; herencia solo la declarada | AC-130-2 | Raíz de biblioteca |
| 3 | Cambio de alcance explícito | §2.5 nueva versión + confirmación; nunca silencioso | AC-130-3 | — |
| 4 | Carpeta por autor no crea/selecciona serie | §3.5.3/§4.3: `autor` no tiene correspondencia a destino único; solo contexto | AC-130-4 | ¿Excepción? |
| 5 | Carpeta por publicación puede proponer, no convertir | §2.4/§3; destino existente + propuesta, sin escribir | AC-130-5 | — |
| 6 | Distinguir local de alias de importación | §2.6: tipos distintos, B13 fuera; `origen`; sin sobrescritura | AC-130-6 | Modelo de alias de #132 |
| 7 | Retirada sin efectos destructivos | §2.5/§5: versión `retirada`, historial, cero archivos | AC-130-7 | — |
| 8 | Desactivación temporal ≠ borrado | §2.5: estado `desactivada`, reactivable; no aplica a nuevas | AC-130-8 | — |
| 9 | Conflictos visibles y precedencia | §4: tabla + `conflicto_de_correspondencias`/`conflicto_visible`; no elige sin contrato | AC-130-9 | Mismo destino local |

### 6.2 #131 (11 criterios)

| # | Criterio | Contrato | AC propuesta | PO |
|---|---|---|---|---|
| 1 | Destino cerrado; no crea series/publicaciones/ediciones | §2.4 `tipo_destino`; validación de existencia; §5 | AC-131-1 | Tipos de destino |
| 2 | Alcance explícito y procedencia como evidencia | §2.4/§3.4; `contexto_raiz`, `incluir_descendientes`, `tipo_de_registro`; `procedencia` no amplía | AC-131-2 | Semántica de `tipo_de_registro` |
| 3 | Identidad y versión en la propuesta | §3.1 `correspondencia_id` + `version_de_regla`; `declaracion_id`/versión | AC-131-3 | — |
| 4 | Solo propuesta, sin efectos | §3/§5: `propuesta_disponible` no crea/vincula/mueve | AC-131-4 | — |
| 5 | Confirmación separada; versión solo trazabilidad | §3.1/§5; no autoriza pasos posteriores | AC-131-5 | — |
| 6 | Seis estados de no aplicación exactos | §3.2/§3.3: exactamente uno | AC-131-6 | — |
| 7 | Conflicto sin precedencia implícita | §4.2: `conflicto_de_correspondencias` con reglas; no elige | AC-131-7 | Mismo destino |
| 8 | Regla desactualizada al cambiar/desactivar/retirar | §3.6: `regla_desactualizada`, reevaluar | AC-131-8 | — |
| 9 | Desactivar ≠ retirar; retirar no reactiva | §2.5: estados y nueva identidad al reanudar | AC-131-9 | — |
| 10 | Sin efectos retrospectivos | §5.2: no reasigna/revierte/mueve/borra | AC-131-10 | — |
| 11 | Evidencia verificable | §7 pruebas: destino ausente, incluido/excluido, propuesta, cada estado, conflicto, desactualizada, desactivar/retirar, sin efectos; PASS/FAIL/NOT RUN | AC-131-11 | — |

### 6.3 #132 (base, 9 criterios — no se implementa aquí)

| # | Criterio | Depende de |
|---|---|---|
| 1 | Inventario comprensible (tipo, origen, estado, alcance, efectos) | Listado de ambos modelos + B13 + alias importado si existe |
| 2 | Alcance futuro explícito, no retroactivo | §2.5/§5 |
| 3 | Desactivación reversible | §2.5 |
| 4 | Retirada sin efectos destructivos | §2.5/§5 |
| 5 | Efectos previos preservados | §5.2 |
| 6 | Alias automático con consentimiento propio | Modelo de alias de #132; no se activa desde #130/#131 |
| 7 | Conflicto con declaración local y precedencia | §4; UI pinta la precedencia |
| 8 | Activación sin inferencia | Estado `activa` explícito; no por coincidencia |
| 9 | Evidencia verificable del ciclo | Pruebas de #132 |

---

## 7. Cortes, estimación y orden

| Corte | Contenido | Talla | Migración | Depende |
|---|---|---|---|---|
| **130-a** | `declaraciones_carpeta` (enum, tabla, índices, versionado, servicio crear/leer/cambiar/desactivar/retirar) + pruebas | **M** | 0024 aditiva | — |
| **130-b** | UI/API de declaración (alcance visible, confirmación de ampliación, estados) + pruebas de 9 AC | **M** | — | 130-a |
| **131-a** | `correspondencias_contexto` (tabla, índice, versión, referencia a versión de declaración) + evaluación `evaluar_contexto` y sus 6 estados + pruebas | **M** | 0025 aditiva | 130-a |
| **131-b** | Ciclo de vida de correspondencia, API/UI, conflictos/precedencia visibles, evidencia y pruebas de 11 AC | **M** | — | 131-a |
| **132-a** | Inventario de solo lectura y administración reutilizando servicios de #130/#131; B13 y alias importado | **M** | 0026 si hay modelo de alias | 130/131 |
| **132-b** | Consentimiento de alias automático, activación/desactivación y conflictos con local | **S/M** | — | 132-a + PO |

- **Orden obligatorio:** #130 (130-a, 130-b) → #131 (131-a, 131-b) → #132. #132 puede preparar el
  inventario de lectura cuando exista el contrato de evaluación de 131-a, pero **no** implementar
  escrituras antes de que #130/#131 estén fusionados.
- **#131 no cabe en una sola PR revisable** con 11 AC: se parte en 131-a/131-b (dos M). El total sigue
  siendo L/8; no se cambia la estimación aquí, se propone el corte.
- **Migraciones aditivas**, una por entrega; sin backfill: las declaraciones empiezan vacías y nada
  reinterpreta B14/B13 automáticamente. `0024`/`0025`/`0026` son números propuestos; quien implemente
  toma el siguiente libre.
- **Sin cambios en `local_aliases`** en #130/#131. Si #132 crea `alias_importado`, su migración va en
  #132 y no toca los datos de B13.

---

## 8. Decisiones de modelo que necesita el PO

| ID | Decisión | Recomendación | Efecto si se elige otra |
|---|---|---|---|
| **P1** | ¿Una tabla o dos? | **Dos**: declaración y correspondencia | Una tabla obliga a columnas nulas/estados imposibles y mezcla dos ciclos |
| **P2** | Valores de `tipo_significado_carpeta` | **`autor` y `publicacion`**; no `otro` en v1 | Añadir tipos exige migración de enum y reglas de compatibilidad |
| **P3** | ¿Se permite declarar la raíz de la biblioteca? | **No** por defecto | Permitirla exige confirmación y marca «global»; el alcance puede abarcar todo |
| **P4** | ¿La identidad de carpeta es la ruta y no sigue renombrados? | **Sí**: ruta relativa normalizada; mover/renombrar no hereda | Seguir por inodo/nombre sería inferencia y extendería alcance sin querer |
| **P5** | Tipos de destino | **`serie` y `publicacion` existentes**; nunca edición/obra ni creación | Restringir a serie simplifica; permitir publicación exige validar `Issue` |
| **P6** | Semántica de `tipo_de_registro` | **Tipo del registro local** (`archivo`/`serie`/`publicacion`), `NULL` = cualquiera | Usarlo como tipo de destino duplicaría `tipo_destino` y confundiría |
| **P7** | Varias correspondencias locales con **el mismo destino** | **Conflicto explícito**; no fusionar sin regla | Coalescer exige una regla de desempate escrita y probada |
| **P8** | ¿Carpeta `autor` puede tener correspondencia a un destino único? | **No** (solo contexto); #130 AC4 | Permitirlo contradice «el autor no crea/selecciona serie» |
| **P9** | Alias de importación y ciclo de B13 en #132: ¿tabla nueva o extender B13? | **Tabla nueva `alias_importado`** para importados y **extender B13 con estado** (no borrar datos) para que #132 pueda desactivar/retirar aprendidos; actualizar matcher/orquestador para filtrar activos | Extender B13 afecta a dos consumidores y mezcla aprendizaje con importación; nueva tabla sola no da ciclo a B13 |
| **P10** | ¿Retirar una declaración permite reactivarla? | **No**: retirar es terminal; reanudar = nueva declaración | Reactivar una retirada borraría la diferencia con desactivar |

Las decisiones P1/P2/P3/P5/P6/P7/P8/P9 condicionan el modelo; P4/P10 condicionan el contrato de
evaluación. **Sin P1-P9 resueltas, #130/#131 no están Ready**; pueden implementarse 130-a/131-a con
las recomendaciones, pero el PO debe ratificarlas antes de fusionar el modelo.

---

## 9. Riesgos, privacidad y NOT RUN

### 9.1 Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| R-01 | La ruta como identidad no sigue renombrados y la persona cree que sí | Mostrar siempre `contexto_raiz`; no heredar por nombre; documentar; evaluación fuera de alcance |
| R-02 | Confundir heurística B14 con declaración | Declaración explícita y versionada; B14 sigue siendo pista; no se importa automáticamente |
| R-03 | B13 pisa una decisión local por su precedencia cableada en el matcher | Precedencia contractual §4; B13 no se toca; conflicto visible; #132 lo gestiona |
| R-04 | Alias importado se presenta como local | `origen`, tabla/tipo distinto, consentimiento #132, pruebas de no sobrescritura |
| R-05 | Historial crece sin límite | Una fila por cambio; no hay purga porque no es comprobante; consultas por versión e índices |
| R-06 | Conflicto de correspondencias resuelto por la UI por accidente | Estado `conflicto_de_correspondencias`; el servicio no elige; pruebas |
| R-07 | Destino borrado deja regla rota | `destino_no_disponible`; sin FK polimórfica; no se crea ni sustituye |
| R-08 | Ampliar `incluir_descendientes` en silencio | Nueva versión + confirmación; prueba de que no se hereda |
| R-09 | Declaración de raíz abarca todo | P3: prohibida por defecto; confirmación si se permite |
| R-10 | Privacidad: rutas de la biblioteca | Rutas relativas normalizadas; no se registran en logs ni se publican; sin datos personales |
| R-11 | Rendimiento: evaluar muchos registros | Índices por raíz/estado; evaluación determinista por registro; sin N+1 evitable |

### 9.2 Privacidad

- Se guardan rutas **relativas** a la biblioteca, no absolutas; no se guardan nombres de archivo,
  usuarios, IP ni sesión.
- `procedencia` solo lleva `operacion_id`, fechas y origen; no auditoría de personas.
- Los logs no incluyen la ruta ni el nombre (misma política que el resto de la app: §5 del CLAUDE).
- El informe de evaluación puede mostrar la ruta al usuario que la consulta; no se envía a fuentes.

### 9.3 NOT RUN

- **Código:** no se ha implementado nada de #130/#131/#132; esta spec no crea tablas ni migraciones.
- **Pruebas:** no ejecutadas; las pruebas de §6/§7 están definidas, no escritas.
- **Base de datos:** no se ha medido el tamaño de historial ni consultas reales; solo índices propuestos.
- **Navegador/UX:** no se ha abierto una pantalla de declaración/correspondencia (no existe).
- **Benchmark:** no se ha hecho una ficha §13 específica de declaraciones/correspondencias; la ficha
  existente (`ficha-propuestas-desde-carpetas.md`) cubre propuestas desde carpetas, no este modelo. Es
  un DoR pendiente si el PO lo exige.
- **PO:** P1-P10 pendientes; #132 no se declara Ready.
- **SHA:** `3a8b506`; si `main` avanza, re-ejecutar las citas.

---

## 10. Trazabilidad de documentos

| Documento | Uso |
|---|---|
| `docs/design/auditoria-b14-carpetas.md` | La carpeta sugiere y agrupa, no asigna; evidencia del riesgo de regla por carpeta |
| `docs/design/ficha-propuestas-desde-carpetas.md` | Contrato M3 existente; propuestas desde contexto, sin automatismo |
| `docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md` | B13: alcance real del alias, productores/lectores, ausencia de gestión |
| `docs/design/contexto-286.md` | Contexto de navegación; no se mezcla con M7 |
| `docs/design/especificacion-M6-US03-asociar-fuente.md` | Asociación de fuente externa; no es correspondencia local |
| `docs/adr/0003-identidad-editorial.md` | Serie/edición/obra; no crear edición/obra |
| `docs/adr/0008-catalogacion-explicita-y-propuestas-sin-ejecucion-silenciosa.md` | Propuestas sin ejecución; no automatismos |
| `docs/design/ui-migracion.md` | Inventario de rutas/plantillas al implementar la UI |

---

## 11. Auto-revisión

- [x] Contraste real con `fichero:línea` de B14, revisión por contexto, M3, matcher e B13.
- [x] Confirmado que **no existe** modelo, tabla, servicio, ruta ni pantalla de declaración/correspondencia.
- [x] Dos tablas justificadas; columnas, tipos, enums, índices, unicidad, migración aditiva y versionado.
- [x] `contexto_raiz`, `incluir_descendientes` y `tipo_de_registro` definidos y representados.
- [x] Versionado sin pérdida de historial: filas temporales, `version`, `vigente_hasta`; propuestas
      llevan `correspondencia_id`/`version_de_regla`.
- [x] Distinción local / alias de importación / B13; B13 intacto; decisión P9.
- [x] Evaluación con los seis estados, orden, alcance, `destino_no_disponible`, conflictos y
      `regla_desactualizada`.
- [x] Precedencia explícita y conflictos dentro de la misma capa; sin elección implícita.
- [x] Efectos y no-efectos; nada de archivos/series/vínculos/retrospectivo.
- [x] AC de #130 (9) y #131 (11) mapeados; #132 como base; PO marcado.
- [x] Cortes S/M/L y orden #130 → #131 → #132; NOT RUN y riesgos.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-10 | v1.0 | Primera especificación de M7 (#130/#131, base #132): contraste real, dos tablas versionadas, contrato de evaluación, precedencia, efectos, AC y cortes. Sin código, sin migraciones, sin pruebas. |
