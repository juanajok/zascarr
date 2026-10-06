# Ficha técnica — Rebanada 1: superficie de revisión de solo lectura

> Desarrolla la **rebanada 1** de `docs/design/ficha-propuestas-desde-carpetas.md` (priorizada tras el primer registro real).
> **Esta ficha no implementa nada**: fija contratos de entrada y salida y las pruebas de aceptación **antes** de escribir código.
> Alcance de la rebanada: **solo lectura**. No crea series, no asigna, no mueve ni copia, no resuelve duplicados ni referencias obsoletas.

## Objetivo

Que la persona vea, para lo que hoy está pendiente, **qué hay agrupado por su contexto de carpeta, qué serie se sugiere (si hay) y qué
señales la contradicen**, para poder decidir con información D1-D5 y la segunda rebanada. Y que los **17 «serie sugerida, falta confirmar
número y edición»** dejen de ser invisibles.

## Qué debe mostrar (criterios de la revisión)

1. Archivos pendientes **agrupados por carpeta contextual** (no necesariamente `parent.name`).
2. **Estados visibles:** «**Sin serie**» (hoy 1.308 + las 14 filas previas) y «**Serie sugerida, falta confirmar número y edición**» (los 17).
3. **Explicación del contexto** por grupo: carpetas ascendentes, patrón de nombres detectado y señales conflictivas si las hay.
4. **Evidencia de conflicto:** si el nombre coincide exactamente con una serie pero la carpeta, el año o la edición discrepan ⇒ **«por confirmar»**
   (invariante de la ficha anterior; **nunca** asignación directa, enlace a `Issue` ni serie preseleccionada).

## Entrada (todo sale de la BD; cero disco, cero red, cero hash)

| Fuente | Qué se lee |
|---|---|
| `files` | `id`, `file_path`, `file_name`, `issue_id`, `review_dismissed`, `metadata->match_status`, `metadata->candidates` (lista de `{series_id, title, start_year, score}`), `metadata->cohorte` |
| `Settings.library_path` | solo para hacer relativas las rutas |
| `series` | `id`, `title`, `start_year`, `tradition` (para confirmar que la candidata existe y completar datos) |

Dos conjuntos, **disjuntos**:

- **A — «Sin serie»:** exactamente el filtro de «Por revisar» (`ReviewService._condiciones_pendientes()`: `issue_id IS NULL`, no descartado,
  `match_status = unsorted`). **Se reutiliza ese método, no se copia**, para que el recuento coincida con el del menú.
- **B — «Serie sugerida, falta confirmar número y edición»:** `issue_id IS NULL`, no descartado, `match_status <> 'unsorted'` y con al menos
  un candidato. (Es el caso de los 17: hoy ni enlazados ni en la bandeja.)

Fuera: archivos con `issue_id`, descartados, y los repetidos no registrados (no hay fila).

## Agrupación: «carpeta contextual»

1. Ruta relativa a la biblioteca → **componentes** `[tradición, c1, c2, …, archivo]`. El primer nivel (`Comics`, `BD`, `Tebeos`…) es la **tradición**, no una serie.
2. **Clave del grupo = ruta de la carpeta inmediata (relativa)**, no solo su nombre: `Graphic Novels/Carlos Gimenez` y `Tebeos/Carlos Giménez` son **dos grupos**.
3. **`carpeta_contextual`** = la primera carpeta, **subiendo desde el archivo**, que **no** sea la tradición ni un **contenedor**. Un contenedor es una carpeta cuyo
   nombre empieza por `_` o coincide con una lista corta y explícita (`varios`, `revisar`, `otros`, `specials`, `omnibus`; lista fija, ver «Decisiones adoptadas», comparada sin acentos ni mayúsculas). Si todo son
   contenedores, no hay contexto («sin carpeta de serie»).
4. **Archivos directamente en la tradición** → un grupo «sin carpeta de serie».
5. Los **ascendentes** (`c1 … cn-1`) se devuelven siempre, para que `Patrulla-X (Panini)` se vea sobre `Inferno (Panini)(2022)`.
6. **Limpieza del nombre de carpeta** (`limpiar_carpeta`, hoy en `scripts/medicion/medir_carpetas.py`): separa **título**, **año** (`(1987)`, `(1987-96)`), **volumen** (`Vol2`),
   **editorial/edición** (`(Panini)`, `(Ed.Zinco)`, `Omnigold`) y **calificador de saga** (`- Saga de Scott Snyder`). *Se mueve a `src/zascarr/core/carpetas.py` (puro, sin E/S)
   y el script lo importa;* la prueba existente `tests/test_medir_carpetas.py` pasa a cubrir el módulo.

## Señales (por grupo; solo las calculables desde la BD)

| Código | Cuándo se emite | Severidad |
|---|---|---|
| `anio_discrepa` | **por archivo, contra SU propia candidata**: el año de la **carpeta** o el año **del propio archivo** difiere en más de 1 del `start_year` de la serie que ese archivo sugiere. Se conservan las dos evidencias: si discrepan la carpeta y algún archivo, ambas quedan en el texto | **conflicto** |
| `calificador_de_carpeta` | la carpeta limpia añade un calificador (`Saga de …`, `Vol N`, edición) que la serie sugerida **por ese archivo** no lleva en su título | **conflicto** |
| `candidatas_distintas` | los archivos de un mismo grupo sugieren series **distintas** (se muestra la que más archivos sugieren) | **conflicto** |
| `titulo_distinto` | el título del nombre de un archivo no es el de su serie sugerida (se tolera el calificador de saga de la carpeta cuando la serie sugerida lo lleva) | **conflicto** |
| `titulo_exacto_sin_corroboracion` | el título de un archivo coincide con su serie sugerida y **ni su año, ni el de la carpeta, ni un volumen** lo corroboran (y su año no discrepa: eso ya lo explica `anio_discrepa`) | **conflicto** |
| `carpeta_de_autor_o_contenedor` | la carpeta reúne muchos títulos distintos (≥ 20 títulos distintos como valor inicial, ver «Decisiones adoptadas») | aviso |
| `coincide_y_corrobora` | **todos** los archivos con serie sugerida tienen el título de su serie y un año (±1) o un volumen que lo corrobora, **y no hay ninguna señal de conflicto** | informativa |
| `sin_contexto_de_carpeta` | no hay `carpeta_contextual` | informativa |

**Ninguna mayoría tapa a una minoría.** Las comprobaciones no usan «el título/año dominante» ni «la serie más sugerida»: se hacen archivo a archivo y se agregan sin votar. Un solo archivo que discrepe (2011 entre dos de 1987) basta para que el grupo esté `en_conflicto` y para que `coincide_y_corrobora` no aparezca.

**Regla:** cualquier señal de severidad **conflicto** ⇒ `en_conflicto = true` ⇒ «por confirmar». El conjunto B es **siempre** `por_confirmar = true` (le falta el número), tenga o no conflicto:
son dos banderas distintas (`por_confirmar` ≠ `en_conflicto`). **No existe un estado «lista»** en esta rebanada.

## Salida — contrato (servicio y JSON)

`GET /api/revision/carpetas` (solo lectura; exige sesión o autenticación Basic como el resto de `/api/*` (solo `/api/health`, `/login`, `/legal`, `/favicon.ico` y `/static/` están exentos, comprobado en `services/auth.py`); `Cache-Control: no-store`; sin dependencia legal, CLAUDE.md §5.2).

```jsonc
{
  "generado": "2026-10-06T10:00:00Z",
  "totales": { "sin_serie": 1322, "serie_sugerida": 17, "grupos": 0 },
  "grupos": [
    {
      "clave": "Comics/Batman - Saga de Scott Snyder (2019)",          // ruta relativa de la carpeta inmediata
      "carpeta_contextual": "Batman - Saga de Scott Snyder (2019)",
      "ascendentes": ["Comics"],
      "carpeta_limpia": { "titulo": "Batman", "anio": 2019, "volumen": null, "calificadores": ["Saga de Scott Snyder"] },
      "estado": "serie_sugerida",                                      // "sin_serie" | "serie_sugerida" | "mixto"
      "etiqueta": "Serie sugerida, falta confirmar número y edición",  // texto fijo, ver abajo
      "n_archivos": 9,
      "patron_de_nombres": { "titulo_dominante": "Batman", "proporcion": 1.0, "titulos_distintos": 1 },
      "serie_sugerida": { "series_id": "…", "titulo": "BATMAN", "anio": 2025, "puntuacion": 1.0 },   // null si no hay
      "por_confirmar": true,
      "en_conflicto": true,
      "senales": [
        { "codigo": "anio_discrepa", "severidad": "conflicto", "texto": "La carpeta dice 2019; la serie sugerida empieza en 2025.", "archivos": ["…", "…"] },
        { "codigo": "calificador_de_carpeta", "severidad": "conflicto", "texto": "La carpeta añade «Saga de Scott Snyder».", "archivos": ["…", "…"] }
      ],
      "archivos": [ { "id": "…", "nombre": "Batman - Saga Scott Snyder 01 - El Tribunal de los Buhos [SC][CRG].cbr" } ]
    }
  ]
}
```

- **Etiquetas fijas** (una sola fuente, `ETIQUETAS`): «Sin serie» · «Serie sugerida, falta confirmar número y edición» · «por confirmar» · «en conflicto». Nunca «reconocido», «clasificado» ni «lista».
- **`senales[].archivos`** (campo añadido en la revisión de #89): lista de **ids de archivo afectados** por esa señal, **ordenados por id (texto, ascendente)**.
  Es la **lista completa** de los afectados, **no** la muestra de `grupos[].archivos`. Como las señales por archivo solo se refieren a archivos con
  serie sugerida, y de esos `grupos[].archivos` devuelve **todos**, cada id de `senales[].archivos` aparece siempre en `grupos[].archivos` (hay una
  prueba). Vacía en las señales del grupo entero (`candidatas_distintas`, `carpeta_de_autor_o_contenedor`, `coincide_y_corrobora`, `sin_contexto_de_carpeta`).
- **Orden determinista:** primero los `en_conflicto`, luego por `n_archivos` descendente, luego por `clave`. **Paginación de grupos** (`limite`, `desplazamiento`; por defecto 200) y **muestra de archivos** (20 por grupo; **todos** en los de estado `serie_sugerida`, que son pocos).
- **Coste:** **una consulta** para A∪B (columnas mínimas), una para las series candidatas y el cálculo en memoria: el número de consultas **no crece** con el de archivos.
- **Nada se escribe, nada se lee del disco, ninguna petición de red.**

## Implementación 1a: lo que se añadió o precisó respecto a esta ficha

Se deja escrito para que la ficha y el código sean un solo artefacto. **Nada de esto relaja un invariante**; son precisiones o campos nuevos.

| Cambio | Por qué |
|---|---|
| **Señal `candidatas_distintas`** (conflicto) | Si los archivos de una carpeta sugieren series distintas, mostrar solo la mayoritaria ocultaría el desacuerdo. |
| **Etiqueta de `mixto`**: «Mezcla: archivos sin serie y con serie sugerida (falta confirmar número y edición)» | El contrato nombraba el estado `mixto` pero no su texto; sin etiqueta propia habría que mentir con una de las otras dos. Sigue sin decir «reconocido», «clasificado» ni «lista». |
| **`archivos[].estado`** (`sin_serie` / `serie_sugerida`) | En un grupo `mixto` hay que saber cuál es cuál; sin ello se perdería el recuento por tipo. |
| **`totales.candidata_inexistente`** | Archivos con serie sugerida cuya serie ya no existe, o con una lista de candidatas ilegible: no se pueden mostrar como «serie sugerida», pero **se cuentan, no se esconden**. (`metadata.candidates` que no es una lista no entra en ningún conjunto: ni A ni B.) |
| **`pagina`** (`limite`, `desplazamiento`) en la respuesta | El cliente necesita saber qué página recibe. Parámetros validados: `limite` 1-1000 (por defecto 200), `desplazamiento` ≥ 0; fuera de rango, 422. |
| **`serie_sugerida.puntuacion` = el mínimo de las puntuaciones de los archivos que sugieren ESA serie** (la elegida; lo que sugieren las otras candidatas no cuenta, ya lo señala `candidatas_distintas`) | No se exagera la confianza de la sugerencia elegida. |
| **`coincide_y_corrobora` solo si TODOS los archivos corroboran y no hay ninguna señal de conflicto** | Que «coincide» conviva con «en conflicto» confundiría; el conflicto manda. |
| **Señales por archivo contra su propia candidata** (año del archivo, año de la carpeta, título, calificadores) y **señal nueva `titulo_distinto`** (conflicto) | Una mayoría no puede ocultar a un archivo minoritario (revisión de #89). `titulo_distinto` marca como conflicto un título que no es el de la serie sugerida; **si se prefiere que sea solo un aviso, es un cambio de severidad de una línea**. |
| **`senales[].archivos`** | Señalar QUÉ archivos discrepan, no solo que el grupo discrepa. |
| **Un calificador de la carpeta (`Vol 2`, `Saga de …`, `(Ed.…)`, `Omnigold`/`Integral`/`Deluxe`) es conflicto si el título de la serie sugerida no lo lleva** | Es la regla `calificador_de_carpeta`; una editorial entre paréntesis (`(Panini)`) y las etiquetas de release **no** son calificadores. |
| **Fuera de la biblioteca configurada** | Una ruta que no cuelga de `library_path` se agrupa por su ruta completa (sin error). Archivos en la raíz: clave `.`. |
| **Sin `ORDER BY` en SQL** | El orden lo fija el servicio (grupos: conflicto, tamaño, clave; archivos: nombre, id). Una prueba entrega las filas al revés y barajadas y exige el mismo resultado. |

**Medido, no supuesto:** cada defensa se probó rompiéndola (mutaciones, ver el PR), y la suite completa se ejecutó también con `--basetemp` en el dispositivo raíz. Un test de propiedades (400 grupos aleatorios) compara el servicio con un oráculo independiente archivo a archivo.

## Qué NO hace (y por qué)

No crea series, no asigna, no mueve, no copia, no resuelve duplicados (D5) ni las 14 referencias obsoletas (esas 14 **aparecen** agrupadas por su carpeta antigua como «Sin serie»; la rebanada **no afirma que el archivo exista**, porque no mira el disco). No cambia el contador del menú (**D2** sigue abierta).

## Pruebas de aceptación (Postgres real; nombres de la biblioteca real como forma, ningún dato personal)

**Agrupación y alcance**
1. Dos carpetas con el mismo título limpio en tradiciones distintas (`Graphic Novels/Carlos Gimenez`, `Tebeos/Carlos Giménez`) → **dos grupos**.
2. **Contenedor:** `Comics/_Omnibus/Dinastia y Potencias de X/…` → `carpeta_contextual = Dinastia y Potencias de X`, `ascendentes = [Comics, _Omnibus]`; si todo son contenedores → «sin carpeta de serie».
3. Archivos directamente en la tradición → grupo «sin carpeta de serie».
4. **Invariante de recuento:** la suma de archivos de los grupos `sin_serie` **es igual** a `ReviewService.count_pending()` (el número del menú); los de `serie_sugerida` **no** están en ese recuento.
5. Descartados y archivos con `issue_id` **no aparecen**.

**Los 17 y el conflicto (los casos reales)**
6. **`Batman - Saga Scott Snyder 01…09`** en `Comics/Batman - Saga de Scott Snyder (2019)` con candidata `BATMAN (2025)` a 1,0 → `serie_sugerida`, `por_confirmar`, **`en_conflicto`**, señales `anio_discrepa` y `calificador_de_carpeta`; **no** hay serie preseleccionada ni estado «lista».
7. **`Absolute Batman 01…09`** en `Comics/Absolute Batman (2024)` con candidata `Absolute Batman (2024)` → `por_confirmar` **sí** (falta el número), **`en_conflicto` no**, señal `coincide_y_corrobora`.
8. Título exacto y **sin año ni volumen** en la carpeta → `titulo_exacto_sin_corroboracion` ⇒ `en_conflicto` (nunca se da por bueno solo por el título).
9. **Carpeta de autor** (≥ 20 títulos distintos) → `carpeta_de_autor_o_contenedor`; no se propone la carpeta como serie.

**Garantías de solo lectura y coste**
10. **Cero escrituras:** un oyente de sentencias comprueba que solo se ejecutan `SELECT`; las filas de `files`/`series`/`import_runs` son idénticas antes y después.
11. **Cero disco y cero red:** con `os.stat`, `Path.exists`, `open` y el cliente HTTP parcheados para fallar, el endpoint responde igual.
12. **Número de consultas constante** (≤ 3) con 20 y con 2.000 filas, y respuesta en menos de 1 s con 2.000 filas (guardarraíl de la Pi).
13. **Idempotencia y determinismo:** dos llamadas seguidas devuelven el mismo orden y los mismos grupos.

**Contrato y seguridad**
14. **Esquema estable:** claves y tipos de la respuesta fijados (una prueba falla si se renombra una clave); etiquetas **exactas** y ausencia de «reconocido»/«clasificado»/«lista».
15. **Autenticación:** con contraseña activada, una petición sin sesión no obtiene datos (mismo comportamiento que el resto de `/api`).
16. **Sin datos sensibles en logs:** el endpoint no registra rutas ni nombres.

## Medición con la biblioteca real (informe, **no** puerta en esta rebanada)

`scripts/medicion/medir_carpetas.py` pasa a usar `core/carpetas.py` y se amplía para **informar** de cuántos de los 16 grupos etiquetados «incorrectos» en la auditoría salen con alguna señal
de aviso o conflicto, y cuántos **sin ninguna** (los previsibles: `Flash (1987)`, `20th Century Boys`, con acuerdo del 89-92 %). Se **publica la cifra, no se afirma cero**.
Como esta rebanada no ofrece ninguna acción, un grupo sin señal no causa daño; el criterio **«falsos lista = 0»** pasa a ser **puerta de la rebanada 2** (crear serie), donde sí importa.

## Entrega en dos PR

- **1a — servicio + endpoint JSON** (`core/carpetas.py`, `services/revision_carpetas.py`, `api/revision.py`) y las pruebas 1-16. Sin plantilla.
- **1b — vista HTML de solo lectura** sobre el mismo servicio (`/ui/pendientes/carpetas`), con las mismas etiquetas, **verificada en navegador real** (grupos, los 17 visibles, el conflicto explicado) y accesible
  (`aria`, contraste, sin JS nuevo). Su prueba de plantilla repite el 14 (etiquetas) y el 6 (conflicto visible).

## Decisiones adoptadas (revisión, 2026-10-06)

1. **Rutas:** `GET /api/revision/carpetas` y `/ui/pendientes/carpetas`.
2. **Lista de contenedores, fija** (en `core/carpetas.py`, con prueba): `_*` (cualquier nombre que empiece por `_`), `varios`, `revisar`, `otros`, `specials`, `omnibus`; comparada sin acentos ni mayúsculas. No es configurable en esta rebanada.
3. **Umbral de «autor o contenedor»:** **≥ 20 títulos distintos**, como **valor inicial** que se ajustará con la medición (no es una verdad fijada).
4. **Las 14 filas obsoletas** aparecen como «Sin serie», **agrupadas por su carpeta antigua**, sin afirmar que el archivo exista (la rebanada no mira el disco). El texto de la interfaz dice explícitamente: **«registros pendientes de verificar, no archivos confirmados»**. La prueba de plantilla de 1b comprueba esa frase. D5 las trata después.

## Invariantes (se repiten porque son la razón de la rebanada)

No mentir: «Serie sugerida, falta confirmar número y edición», nunca «reconocida» ni «clasificada». No escribir. No mirar el disco. Ninguna señal de conflicto se oculta ni se degrada a informativa. Un título exacto **no** es una clasificación.
