# U13a — Entrada por carpetas (solo lectura)

> **Implementación local (2026-10-22):** rama `sprint1/u13a-carpetas`, base
> `0fb10f095b16a0b220b150d95127b4ae36c1cdd8` (el contrato se contrastó en
> `245402e78a6357cfc79e726a4484662ba9ef8151`; #291 no cambió `src/`). La regla de sueltos,
> el orden y la página **50** están aprobados en #200, comentario `6340045935`, y en
> `docs/design/ui-u13/dor-287-288-2026-10-22.md`. `carpetas_utiles_sin_serie = 108` en el
> fixture; `carpetas_utiles` se calcula sobre A+B y no se fija a 108. Evidencia local en §11:
> navegador real, Pi, lector de pantalla y prueba de cinco segundos siguen **NOT RUN**.
>
> **Código de referencia del contrato:** `origin/main` `245402e78a6357cfc79e726a4484662ba9ef8151`.
>
> **Dependencia:** ninguna. Es la primera historia del troceo y la base de U13b/U13c.

## 1. Historia

**Como** coleccionista con una biblioteca organizada en carpetas,
**quiero** entrar en «Por revisar» por carpetas y ver un desglose exacto de cuántos pendientes hay
en carpetas útiles y cuántos son sueltos,
**para** decidir por dónde empezar sin crear, vincular ni mover nada.

## 2. Alcance

**Dentro**

- La vista HTML `GET /ui/pendientes/carpetas`, de solo lectura.
- El resumen con el desglose H2: total, carpetas útiles, sueltos y serie sugerida.
- La lista de carpetas útiles con sus estados, señales y muestras actuales.
- La ordenación y la paginación actuales, reutilizadas.
- Un enlace GET a la vista individual existente para los sueltos (la cola nueva es U13b) y el
  enlace GET existente al asistente (U13c).

**Fuera**

- Crear series, asignar, vincular, mover, ignorar o borrar.
- La cola individual de sueltos (U13b).
- Cambiar el asistente, la vista previa o la confirmación (U13c y rebanada 2).
- Resolver las 14 referencias obsoletas o los duplicados.
- Cambiar el contador del menú (D2).
- Tocar la biblioteca real, la Pi o staging.

## 3. Contrato de datos

### 3.1 Conjuntos (vigente)

La lectura es la de `RevisionCarpetas.carpetas()`:

- **A — «Sin serie»:** exactamente `ReviewService._condiciones_pendientes()`:
  `issue_id IS NULL`, `review_dismissed = false`, `metadata->match_status = 'unsorted'`.
- **B — «Serie sugerida, falta confirmar número y edición»:** `issue_id IS NULL`,
  `review_dismissed = false`, `match_status <> 'unsorted'` y al menos un candidato.
- A y B son disjuntos. `candidata_inexistente` cuenta los archivos con candidata cuya serie ya no
  existe o cuyo `metadata.candidates` no es legible; **no** se muestran como grupo y **no** se
  suman a A ni a B.

### 3.2 Carpeta útil y suelto (vigente)

Sea `div = dividir_ruta(partes)` para un archivo:

| Concepto | Regla exacta | Consecuencia |
|---|---|---|
| **Carpeta útil** | Grupo cuya `div.contextual is not None`. | Se lista como carpeta, aunque tenga **un solo archivo**. |
| **Suelto** | Archivo cuya `div.contextual is None`. | No se lista como carpeta; se cuenta y enlaza a la vista individual. U13b traerá su cola propia. |
| **Grupo sin contexto** | Grupo cuya `div.contextual is None`. | No suma a `carpetas_utiles`; sus archivos suman a `sueltos`. |
| **Carpeta mixta** | Grupo con archivos A y B. | Sigue siendo útil; `estado = "mixto"` y se muestran las dos poblaciones. |

`div.contextual` es la primera carpeta, subiendo desde el archivo, que no es la tradición ni un
contenedor. Una carpeta que empieza por `_` o cuya forma sin acentos coincide con `varios`,
`revisar`, `otros`, `specials` u `omnibus` es contenedor. Si todo son contenedores, no hay contexto.

**No se redefine** el grupo: la clave sigue siendo la ruta de la carpeta inmediata relativa. Esto
significa que `Comics/Flash (1987)` y `Comics/Flash (1987)/_Extras` pueden ser dos grupos útiles con
el mismo `carpeta_contextual`; es el contrato vigente y no se cambia en U13a.

### 3.3 Ejemplos de entrada/salida

| `file_path` (relativo a la biblioteca) | `clave` | `carpeta_contextual` | ¿Carpeta útil? | ¿Suelto? |
|---|---|---|---|---|
| `Comics/Flash (1987)/Flash 01.cbz` | `Comics/Flash (1987)` | `Flash (1987)` | Sí | No |
| `Comics/Flash (1987)/_Extras/Flash 02.cbz` | `Comics/Flash (1987)/_Extras` | `Flash (1987)` | Sí | No |
| `Comics/_Omnibus/Dinastia de X/01.cbz` | `Comics/_Omnibus/Dinastia de X` | `Dinastia de X` | Sí | No |
| `Comics/_Omnibus/01.cbz` | `Comics/_Omnibus` | `None` | No | Sí |
| `Comics/01.cbz` | `Comics` | `None` | No | Sí |
| `01.cbz` (raíz) | `.` | `None` | No | Sí |
| `Comics/Autor/Crossover/01.cbz` | `Comics/Autor/Crossover` | `Crossover` | Sí (con aviso si ≥ 20 títulos) | No |
| `Comics/Mixta/01.cbz` + `Comics/Mixta/02.cbz` (A y B) | `Comics/Mixta` | `Mixta` | Sí, `estado="mixto"` | No |
| Fuera de `library_path` | ruta completa sin la raíz | según `dividir_ruta` | Se conserva la regla actual; se marca «fuera de la biblioteca» | No se reclasifica en silencio |

**Error de ruta:** una ruta vacía o un `file_path` que no es una ruta utilizable se trata según
`_carpetas_de()`; si no se puede agrupar, no se inventa una carpeta. No se añade una excepción
nueva en U13a ni se reclasifica como candidata inexistente, que es un contador distinto.

## 4. Contrato de recuentos

### 4.1 Campos

Se conservan los campos actuales de `Totales`:
`sin_serie`, `serie_sugerida`, `grupos`, `candidata_inexistente`.

Se **añaden** (aditivo, sin cambiar el significado de los existentes):

| Campo | Significado |
|---|---|
| `carpetas_utiles` | Número de grupos con `carpeta_contextual is not None` (A+B válidos). |
| `carpetas_utiles_sin_serie` | Carpetas útiles que contienen al menos un archivo A. |
| `carpetas_utiles_serie_sugerida` | Carpetas útiles que contienen al menos un archivo B. |
| `sin_serie_en_carpetas` | Archivos A en grupos con contexto. |
| `sin_serie_sueltos` | Archivos A con `carpeta_contextual is None`. |
| `serie_sugerida_en_carpetas` | Archivos B en grupos con contexto. |
| `serie_sugerida_sueltos` | Archivos B con `carpeta_contextual is None`. |
| `sueltos` | `sin_serie_sueltos + serie_sugerida_sueltos`. |

`grupos` sigue siendo el número de grupos devueltos por la agrupación actual, incluidos los grupos
sin contexto. La vista **no** usa `grupos` para decir «108 carpetas»: usa `carpetas_utiles`. Esto
evita romper el contrato del JSON y, a la vez, corrige H2.

### 4.2 Invariantes

Para cualquier conjunto:

```
sin_serie = sin_serie_en_carpetas + sin_serie_sueltos
serie_sugerida = serie_sugerida_en_carpetas + serie_sugerida_sueltos
sueltos = sin_serie_sueltos + serie_sugerida_sueltos
carpetas_utiles <= grupos
carpetas_utiles_sin_serie <= carpetas_utiles
carpetas_utiles_serie_sugerida <= carpetas_utiles
```

`candidata_inexistente` queda fuera de las sumas; se muestra como contador separado.

### 4.3 Caso de referencia (1.322)

Con el conjunto real de la auditoría:

| Concepto | Valor |
|---|---:|
| A — «Por revisar» | **1.322** |
| A en carpetas útiles | **1.308** |
| A sueltos | **14** |
| Carpetas útiles | **108** |
| B — serie sugerida, aparte | **17** |
| B en carpetas / sueltos | 17 / 0 (se calcula, no se fija) |
| Total visible A+B | **1.339** |

Texto de la vista (los números se calculan; aquí se muestran como ejemplo):

> **1.322 por revisar: 1.308 en 108 carpetas + 14 sueltos.**
> **17 con serie sugerida, aparte. 1.339 registros visibles.**

Reglas del texto:

- Los 14 sueltos están **dentro** de los 1.322; nunca se dice «1.322 + 14» ni «1.336».
- Los 17 no se suman dentro de los 1.322 sin decir «aparte».
- Si B tiene sueltos, se cuenta en `serie_sugerida_sueltos` y se avisa en el desplegable; no se
  oculta.
- Si no hay sueltos, la frase muestra «0 sueltos»; no se pinta un bloque aparte.
- Si no hay carpetas útiles pero sí sueltos, se pinta «0 en 0 carpetas + N sueltos» y el enlace a
  la vista individual; no un vacío que oculte los sueltos.

## 5. Orden, paginación y errores

### 5.1 Orden (vigente)

- Grupos: `(not en_conflicto, -n_archivos, clave)`. Determinista; los conflictos primero.
- Archivos dentro de un grupo: `(nombre, id)`. Se muestran todos los B y hasta 20 de los A.
- La consulta SQL no lleva `ORDER BY`; el orden lo fija el servicio. Una prueba entrega las filas
  barajadas y exige el mismo resultado.

No se añade un control de orden en U13a. Si se pide «ordenar por nombre» o «por tamaño», es una
historia aparte; H8 sigue abierto en la parte de búsqueda/filtro.

### 5.2 Paginación (vigente en la vista)

- `limite` por defecto **50** grupos en la vista; el servicio admite 1–1000.
- `desplazamiento` ≥ 0.
- Parámetros fuera de rango: **422**.
- Texto «Carpetas X–Y de N»; `N = carpetas_utiles`, no `grupos`.
- Anteriores/Siguientes con enlaces GET; sin JavaScript nuevo.
- Si el desplazamiento cae fuera del conjunto actual, se muestra «Esta página ya no existe» con
  enlaces a la primera página y a la última válida; no se presenta como una lista vacía normal.

### 5.3 Errores

| Caso | Respuesta |
|---|---|
| `limite` fuera de 1–1000 o `desplazamiento < 0` | 422 (validación existente). |
| Fallo de base de datos | 503 con mensaje recuperable y enlace de reintento; **no** se muestran recuentos parciales. |
| Candidata ilegible o serie borrada | Se cuenta en `candidata_inexistente`; no se pinta como grupo. |
| Ruta fuera de la biblioteca | Se conserva la agrupación actual y se marca; no se trata como suelto silenciosamente. |
| Sin pendientes | Estado vacío «Nada pendiente»; sin enlaces de acción. |

`Cache-Control: no-store`. Cero disco, cero red y cero escrituras.

## 6. Solo lectura y accesibilidad

- No hay `<form>`, `<button>`, `hx-post`, `hx-delete`, `hx-put`, ni `type="submit"` en la vista.
- Se conserva **un** enlace GET al asistente por grupo
  (`/ui/pendientes/carpetas/asistente?clave=…`) y **un** enlace GET a la vista individual existente
  (`/ui/pendientes`) para los sueltos. La cola nueva es U13b y no se adelanta.
- Una prueba con oyente de SQL comprueba que solo se ejecutan `SELECT`; las filas de `files` y
  `series` quedan idénticas.
- Una prueba con `os.stat`, `Path.exists`, `open` y cliente HTTP parcheados comprueba que no hay
  disco ni red.
- Accesibilidad: `h1`, `aria-labelledby` por grupo, chips con texto e icono (no solo color), enlaces
  reales, foco visible, etiquetas largas que se parten a 360 px sin desbordamiento horizontal.
- No se declara prueba de cinco segundos ni lector de pantalla real: **NOT RUN**.

## 7. Flujos Dado/Cuando/Entonces

### Feliz — desglose H2

**Dado** un conjunto de 1.322 pendientes A con 1.308 en 108 carpetas útiles y 14 sueltos, y 17 B,
**cuando** abro «Pendientes por carpeta»,
**entonces** veo «1.322 por revisar: 1.308 en 108 carpetas + 14 sueltos», veo «17 con serie sugerida,
aparte» y el total visible 1.339, sin que ninguna cifra se sume dos veces.

### Feliz — carpeta con un solo archivo

**Dado** un grupo con `carpeta_contextual = "Flash (1987)"` y un solo archivo,
**cuando** se pinta la lista,
**entonces** aparece como carpeta útil con «1 archivo», no se oculta y no se cuenta como suelto.

### Límite — raíz, tradición y contenedor

**Dado** un archivo en la raíz, otro directamente en `Comics` y otro en `Comics/_Omnibus`,
**cuando** se agrupan,
**entonces** los tres tienen `carpeta_contextual = None`, no aparecen como carpetas útiles y suman
al contador de sueltos; el de `Comics/_Omnibus/Dinastia de X` sí es una carpeta útil.

### Límite — carpeta mixta

**Dado** un grupo con 3 archivos A y 2 B,
**cuando** se pinta,
**entonces** `estado = "mixto"`, la etiqueta lo dice, se ven las dos poblaciones y no se preselecciona
ninguna serie.

### Error — parámetro inválido

**Dado** `limite=0` o `desplazamiento=-1`,
**cuando** pido la vista,
**entonces** recibo 422 y no se pinta un recuento inventado.

### Error — base de datos

**Dado** un fallo de lectura,
**cuando** pido la vista,
**entonces** recibo el error global, no una página con cifras parciales y no se escribe nada.

### Solo lectura

**Dado** la vista cargada,
**cuando** inspecciono el HTML y ejecuto la petición,
**entonces** no hay formularios ni botones de escritura, solo enlaces GET; el oyente SQL solo ve
`SELECT`; `files` y `series` no cambian.

### Accesibilidad

**Dado** una ventana de 360 px y un lector de pantalla,
**cuando** recorro la página,
**entonces** hay un `h1`, cada grupo tiene nombre accesible, los chips no dependen del color y no
hay desbordamiento horizontal. (La prueba con personas/lector real sigue NOT RUN.)

## 8. Criterios de aceptación

1. La vista muestra el desglose H2 exacto y los 14 sueltos están dentro de los 1.322.
2. `carpetas_utiles` es 108 y no incluye grupos sin contexto; una carpeta de un solo archivo cuenta.
3. Los 17 B se muestran aparte; no se suman silenciosamente.
4. `sin_serie` y `serie_sugerida` cumplen las invariantes de suma.
5. El orden y la paginación actuales se conservan; los parámetros inválidos dan 422.
6. La vista no tiene acciones de escritura; solo enlaces GET.
7. El enlace al asistente existente sigue funcionando y no crea nada por sí solo.
8. Sin disco, sin red, sin caché; una prueba de SQL comprueba solo `SELECT`.
9. A 360 px no hay desbordamiento; los chips tienen texto e icono.
10. La medición P1/P3 está registrada o la DoR queda incompleta.

## 9. Referencias de código

- `src/zascarr/core/carpetas.py::dividir_ruta`, `es_contenedor`, `analizar_carpeta`.
- `src/zascarr/services/revision_carpetas.py::RevisionCarpetas.carpetas`,
  `RevisionCarpetas._grupo`, `Totales`, `ETIQUETAS`.
- `src/zascarr/web/pendientes.py::carpetas`, `_vista_carpetas`, `GRUPOS_POR_PAGINA`.
- `src/zascarr/web/templates/carpetas.html`.
- `tests/test_web_carpetas_pg.py`, `tests/test_revision_carpetas_pg.py`,
  `tests/test_tokens_limites_pg.py`.

## 10. DoR de esta historia

- [x] Historia vertical y pequeña.
- [x] Contrato vigente reutilizado y ejemplos.
- [x] Flujos feliz, error y límite.
- [x] Referencia a SHA concreto.
- [x] Regla «carpeta útil/suelto» aprobada en la re-revisión de 2026-10-22.
- [x] Campos aditivos de recuento aprobados en #287.
- [ ] Presupuesto P1/P1b medido en Pi 4/5 (local ASGI en §11; Pi **NOT RUN**).
- [ ] Estimación calibrada (propuesta: 3; confirmación final en la PR).
- [ ] Prueba de 5 s/lector real: **NOT RUN**; no se declara PASS.
- [x] Revisión INVEST y re-revisión (DoR aprobada el 2026-10-22).

La DoR está aprobada. La implementación local no acredita Pi, navegador real, lector de pantalla ni
cinco segundos; esas comprobaciones siguen **NOT RUN** y la fusión/despliegue se aprueban aparte.

## 11. Implementación y evidencia local (2026-10-22)

- **Entorno local:** Intel Core i5-8365U, 8 hilos, 30 GiB RAM, Linux 7.0.0-38, Python 3.14.4,
  PostgreSQL 15-alpine en `127.0.0.1:15450` (contenedor local), `/tmp` sobre tmpfs de 16 GiB
  (8,9 GiB libres durante la prueba), cliente de pruebas HTTPX/ASGI. Sin Chrome real, sin red
  externa y sin Pi. La medición es de esta máquina y de este árbol de trabajo; el SHA exacto de
  la PR y la CI se registran en la PR.
- **Cambios:** `src/zascarr/services/revision_carpetas.py` (campos aditivos, `solo_utiles`,
  recuentos desde los acumulados completos y paginación después de filtrar),
  `src/zascarr/web/pendientes.py` (`contar_carpetas` usa `carpetas_utiles`, vista con
  `solo_utiles=True`, página inválida y error 503) y
  `src/zascarr/web/templates/carpetas.html` (frase de 18 palabras, enlace a sueltos, orden en el
  desplegable y estados vacío/error). La API conserva su respuesta por defecto con todos los
  grupos.
- **Pruebas locales:** 120 `passed` en
  `tests/test_web_carpetas_pg.py tests/test_revision_carpetas_pg.py tests/test_pendientes_navegacion_pg.py`
  más `tests/test_web_componentes.py::TestCompatibilidad`, con PostgreSQL real local. Incluyen
  partición A/B/sueltos, `solo_utiles` antes de paginar, página 50, página invalidada, fallo sin
  recuentos parciales, enlace a sueltos y `contar_carpetas`.
- **Medición A∪B:** fixture sintético local de **1.322 A** (1.308 en 108 carpetas + 14 sueltos) y
  **17 B**; `carpetas()` ejecuta **2 consultas** (A∪B y series candidatas). p95 local del servicio
  con página 50: **124 ms**; HTML ASGI local: primera carga **143 ms** y cambio de página
  **121 ms** (20 mediciones en caliente, una preparación previa). Son cifras de esta máquina y
  de ASGI, **no** de un navegador real ni de la Pi; P1/P1b/P4 siguen **NOT RUN**.
- **Texto:** `TestPresupuestoTexto` de Carpetas queda en **46** palabras antes de la acción y
  **18** en la frase de entrada; 44 era la composición de #208 y se conserva como histórico.
- **Sin tocar:** biblioteca real, staging, Pi, disco bibliotecario y red externa. Sin migraciones,
  sin escrituras y sin despliegue.
- **Pendiente antes de fusionar:** CI sobre el SHA exacto, revisión y decisión de #196. Navegador
  real, lector de pantalla y cinco segundos: **NOT RUN**.
