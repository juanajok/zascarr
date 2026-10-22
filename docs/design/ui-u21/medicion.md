# U21 — Presupuesto de texto: método, reescritura de Carpetas y límites (2026-10-21)

> **Estado: método y umbral aceptados por el responsable; «Pendientes por carpeta» y la ficha de serie están
> reescritas y con prueba automática. La ficha se verificó en Chrome real (claro/oscuro, 360 px, teclado y árbol
> de accesibilidad); Carpetas sigue sin medida en navegador. La prueba de 5 segundos con personas y el lector de
> pantalla real siguen NOT RUN. #208 no se cierra.**

## 1. Regla vigente

`CLAUDE.md` §6, «Presupuesto de texto» (decidido el 2026-10-15; umbrales provisionales hasta U10):

- Una frase de entrada por pantalla, **≤ 20 palabras**, que diga qué se hace.
- **≤ 50 palabras visibles antes de la primera acción**.
- La garantía («no se mueve ni se renombra nada») va **junto a la acción con efecto**, no en la cabecera de
  pantallas que no cambian nada.
- Resumen antes que listado. Mayúsculas solo en rótulos de ≤ 3 palabras.
- Los textos explican la tarea, no el contrato: sin «token», «lote» ni códigos internos.

## 2. Baseline histórico (auditoría 2026-10-15, `a5369ef`)

Palabras visibles en `main`, sin pie legal, controles ni contenido plegado:

| Pantalla | Palabras | Antes de la 1.ª acción | Párrafos ≥ 35 p. | En mayúsculas |
|---|---:|---:|---:|---:|
| Pendientes por carpeta | 1.261 | **415** | 2 | 0 |
| Ajustes | 472 | 84 | 7 | 41 |
| Duplicados | 9.522 | 37 | 2 | 0 |
| Ficha de serie | 146 | 63 | 0 | 52 |
| Deseados | 76 | 51 | 0 | 33 |
| Inicio *(referencia)* | 174 | 49 | 0 | 12 |
| Descubrir *(referencia)* | 29 | 29 | 0 | 0 |

**No es el estado actual.** `main` ha cambiado desde entonces (U14, U16, U17, U19, U20). La comparación con la
medida nueva **no es homogénea**: la auditoría contaba la pantalla completa con datos y otra definición de «primera
acción». No se presenta como un antes/después validado.

## 3. Medida actual

### 3.1 Antes de la reescritura (inspección de plantilla, no navegador)

En `carpetas.html` (`origin/main` `8589b47`) había, antes de la primera acción:

1. `h1`: «Pendientes por carpeta» (3 palabras).
2. Subtítulo de **≈ 50 palabras** sobre lo que se crea o no se crea.
3. Aviso `info` de **≈ 49 palabras** sobre registros, disco y pistas.
4. Enlace «← Volver a Por revisar», la primera acción.

**Estimación:** > 100 palabras antes de la primera acción. La garantía y la explicación del contrato estaban en la
cabecera, no junto a la acción.

### 3.2 Después de la reescritura de #208 (HTML renderizado, 2026-10-21; histórico)

Fixture usado: 1.308 pendientes en 108 carpetas + 14 con serie sugerida, dos tarjetas visibles. Renderizado con la
plantilla real y una respuesta enlatada del servicio, sin tocar la base de datos ni la Pi. Esta es la composición
de #208; U13a la sustituye sin borrar la cifra histórica (ver §3.2.1).

| Medida | Resultado |
|---|---:|
| Palabras de la frase de entrada (`p.subtitle`) | **8** |
| Palabras antes de «Elegir la serie de esta carpeta» | **44** (43 sin el marcador decorativo `i` de los chips) |
| Palabras totales de `main` (incluye datos, detalles y listado) | 440 |
| Umbral de entrada / intro | ≤ 20 / ≤ 50 |

La medida de **44** es **conservadora** y se obtiene quitando el contenido de los `<details>` cerrados pero
conservando el texto visible de su `<summary>`, como pide el método. Las 39 de #273 no contaban el resumen; el
resumen «¿De dónde salen estos datos?» añade 5 palabras. La prueba histórica enlataba la respuesta 1.308/108/14 y
dos tarjetas y exigía **exactamente 44** (43 sin el icono `i` del chip informativo); U13a la sustituyó por
`test_la_cifra_de_46_es_reproducible_con_el_fixture_de_referencia` (§3.2.1). La prueba general de umbral siembra
un solo registro y comprueba ≤ 50; no pretende reproducir la cifra.
La suite `TestPresupuestoTexto` falla si la entrada o la intro superan el umbral, si falta la garantía junto a la
acción o si el subtítulo pasa de 20 palabras.

### 3.2.1 U13a sustituye los chips por la frase de resumen (2026-10-22)

U13a cambia la entrada de Carpetas: la frase de 18 palabras sustituye el subtítulo de 8 y los chips de resumen,
y el contador de sueltos es un enlace a la vista individual. El orden se explica dentro de «¿De dónde salen estos
datos?», por lo que sigue fuera de la medida conservadora. La cifra vigente es **46**; 44 queda como histórico de
#208 y no se presenta como una regresión.

| Medida U13a | Resultado |
|---|---:|
| Palabras de la frase de entrada (`p.subtitle`) | **18** |
| Palabras antes de «Elegir la serie de esta carpeta» | **46** |
| Fixture | 1.322 A (1.308/108 + 14) + 17 B; dos tarjetas |
| Umbral de entrada / intro | ≤ 20 / ≤ 50 |

Se reproduce con
`tests/test_web_carpetas_pg.py::TestPresupuestoTexto::test_la_cifra_de_46_es_reproducible_con_el_fixture_de_referencia`,
que enlata la respuesta U13a y exige exactamente **46**. La prueba general de umbral y la de subtítulo exacto de 18
siguen en la misma suite. No hay medición de navegador nuevo para esta composición: **NOT RUN**.

**Límite:** es una medida sobre HTML renderizado, no sobre píxeles de un navegador. No se ha comprobado con CSS
real, tema oscuro, 360 px ni lector de pantalla.

### 3.3 Ficha de serie después de la reescritura (Chrome real, 2026-10-21)

Fixture local de 10 números (3 presentes, 7 ausentes), acción principal `select#wishlist_policy` («Qué buscar»).
Medición en Chrome 154 con la app servida desde el árbol de la rama, no desde HTML estático.

| Medida | Resultado |
|---|---:|
| Frase de entrada | **8** |
| Antes del selector, con datos variables y resumen visible | **48** (45 sin el resumen) |
| Texto introductorio sin datos variables | **29** |
| Palabras totales de `main` | 190 |
| Párrafos con `text-transform: uppercase` | **0** |

La sección «Búsqueda automática» queda antes de los listados; el efecto de guardado y la nota de futuros están
junto al selector; «Fuentes y atribución» es un `<details>` cerrado que conserva el aviso legal. A 360 px,
`scrollWidth = clientWidth = 360` en claro y oscuro. El foco por teclado llega al selector con anillo visible y el
desplegable se abre y se cierra con Enter. Evidencia completa, con capturas y SHA, en
`docs/design/ui-u21/verificacion-ficha-2026-10-21.md`.

**Límite:** el árbol de accesibilidad de Chrome no sustituye a un lector de pantalla real. La prueba de cinco
segundos con personas sigue **NOT RUN**.

## 4. Método aceptado

Se reutiliza el patrón de `docs/design/ui-u17/inventariar_u17.py` y `docs/design/ui-u16/medir_u16.py` para la
medida en navegador. Para cada pantalla:

1. Cargar la ruta y esperar a que termine la carga.
2. Recorrer `main` en orden de documento.
3. Contar palabras de los nodos de texto **visibles**, excluyendo:
   - `nav`, `header`, `footer`, aviso legal;
   - el **contenido** de `<details>` cerrados, pero conservando el texto visible de su `<summary>`;
   - controles (`input`, `select`, `button`, `textarea`) y sus valores;
   - texto oculto (`display:none`, `visibility:hidden`, `[hidden]`).
4. Detener el contador en la **primera acción**: control principal habilitado que inicia la tarea de esa pantalla.
   Se excluyen la navegación global, la ayuda y los desplegables informativos. Cada fixture identifica expresamente
   el control. En Carpetas es «Elegir la serie de esta carpeta»; en la ficha, `select#wishlist_policy`.
5. Guardar `{pantalla, ruta, vista, tema, palabras_totales, palabras_antes_de_la_accion, palabras_intro, accion,
   palabras_despues}`. `palabras_intro` excluye los datos variables del catálogo (título, editorial, recuento,
   listado); `palabras_antes_de_la_accion` es la medida conservadora con esos datos.

Umbral: **PASS** si `palabras_intro <= 50`, la frase de entrada tiene ≤ 20 palabras y la medida conservadora con
datos tampoco supera 50 en el fixture de referencia. **FAIL** si no. **NOT RUN** si no se pudo cargar. El total
visible se publica aparte para no ocultar el coste de lectura.

La comprobación automática es una prueba de contrato: falla si una plantilla adaptada supera el umbral. Las rutas
que necesitan BD usan el patrón de Postgres real de `tests/*_pg.py`; las que no, `TestClient` + `FakeSession`.

## 5. Reescritura aplicada de «Pendientes por carpeta»

Archivos: `src/zascarr/web/templates/carpetas.html` y `src/zascarr/static/web.css`.

**Antes (estimado >100 palabras):** subtítulo largo + aviso largo + enlace.

**Ahora:**

```text
Pendientes por carpeta
Elige una carpeta para revisar sus archivos.            ← 8 palabras

← Volver a «Por revisar»                                ← navegación

▸ ¿De dónde salen estos datos?                          ← detalle plegado
   [1.308 sin serie] [14 con serie sugerida] [108 carpetas]

Comics/Flash (1987)
[Sin serie] [por confirmar]
155 registros · Sin serie sugerida
[Elegir la serie de esta carpeta]                       ← acción principal
No se crea ni se asigna nada hasta que confirmes.       ← garantía junto a la acción
▸ Ver datos y observaciones                             ← plegado
▸ Ver registros (20 de 155)                             ← plegado
```

Decisiones concretas:

- El texto técnico («lee la base de datos y no comprueba el disco», «un registro puede apuntar a un archivo que ya
  no esté») pasa a `¿De dónde salen estos datos?`.
- El aviso de series borradas se resume en un chip «con serie borrada» y se explica dentro del mismo detalle; no
  desaparece.
- La acción se adelanta antes de la ficha larga y de las señales. La tarjeta muestra nombre, recuento, estado y
  serie sugerida o ausencia explícita **antes** de la acción.
- Los detalles y las observaciones quedan plegados; la garantía de no mover ni renombrar queda junto al enlace.
- No se añadió JavaScript, formulario, migración ni lógica de negocio.

## 6. Reescritura aplicada de la ficha de serie

La ficha actual **no tiene formulario de metadatos ni botón «Guardar»**: la acción principal es el selector de
política, que guarda al cambiar. La reescritura se adapta a esa realidad; no se inventa un formulario.

- Frase de entrada: «Consulta tus números y ajusta la búsqueda automática.» (**8 palabras**).
- ≤ 50 antes de la acción: **48** con datos variables y resumen visible; **29** introductorias sin datos.
- «Búsqueda automática» sube **antes** de «Te faltan» y «En tu biblioteca»; el resumen va antes del listado.
- El efecto de guardado y la nota de futuros van **junto al selector**, en una frase cada uno. Se elimina la
  frase de «Guardar» del final porque el selector guarda al momento.
- «Fuentes y atribución» pasa a un `<details>` cerrado; conserva el aviso de metadatos y el enlace «Aviso legal».
- Nada de mayúsculas en párrafos; los rótulos de la política son de ≤ 3 palabras.

Archivos: `series_detail.html`, `_politica_serie.html`, `_legal_disclaimer.html`, `web.css` y
`tests/test_web_series.py` (`TestPresupuestoTextoU21`, 6 casos). Medición y capturas:
`docs/design/ui-u21/verificacion-ficha-2026-10-21.md`.

**Estado: PASS de presentación en Chrome real; 5 segundos y lector real NOT RUN.**

## 7. Criterios de U21

| Criterio | Estado | Evidencia |
|---|---|---|
| 1. Regla en `CLAUDE.md` §6 | **PASS** | Texto vigente, umbrales provisionales |
| 2. Suite con recuento y umbral por pantalla adaptada | **PASS** | `TestPresupuestoTexto` de Carpetas (44 en #208; 18/46 con U13a) y `TestPresupuestoTextoU21` de la ficha (8/29 intro; 48 con datos); la ficha se midió además en navegador |
| 3. Carpetas ≤ 20 de entrada y ≤ 50 antes de la acción | **PASS (HTML)** | U13a: frase de 18; 46 antes de «Elegir la serie de esta carpeta». Navegador: NOT RUN |
| 4. Tarjeta con nombre, archivos, sugerencia/ausencia y estado | **PASS** | `h2`, chips, línea «N registros · Serie sugerida/Sin serie sugerida» antes de la acción |
| 5. Garantías junto a la acción con efecto | **PASS** | «No se crea ni se asigna nada hasta que confirmes.» junto al enlace; en la ficha, el efecto de guardado junto al selector |
| 6. Ficha de serie sin párrafos en mayúsculas | **PASS** | 0 párrafos con `text-transform: uppercase`; notas junto al selector |
| 7. Test de 5 segundos de #197 | **NOT RUN** | No se ha hecho con personas; la simulación con agentes no cuenta como validación |
| 8. Regresiones de teclado, detalles, temas y 360 px | **PARCIAL** | Ficha: PASS en Chrome real (claro/oscuro, 360, teclado, detalles y árbol de accesibilidad). Carpetas: solo HTML; navegador NOT RUN |

## 8. Decisiones adoptadas (2026-10-21)

1. **Se acepta el método de recuento** de nodos de texto visibles, sin nav/footer, sin el contenido de detalles
   cerrados (el resumen visible sí cuenta) y sin controles; el umbral es de **50 palabras antes de la primera
   acción**.
2. **Carpetas fue primero; la ficha de serie va después**, ya adaptada a su acción real.
3. **La comprobación automática se limita a las pantallas adaptadas**; Ajustes, Duplicados y Estado conservan sus
   historias y no se convierten en un falso PASS.
4. **No se toca la Pi.** No hay despliegue ni validación en producción.
5. **La ficha se adapta a su acción real:** no hay formulario de metadatos ni botón «Guardar»; se mide el selector
   de política, que guarda al cambiar. No se inventa una pantalla nueva para cumplir el método.

## 9. Lo que NO está acreditado

- Carpetas no tiene medida en navegador real; su evidencia sigue siendo HTML renderizado y la prueba de contrato
  de #273.
- La ficha sí se midió en navegador (claro/oscuro, 360, teclado y detalles), pero **no con un lector de pantalla
  real**: solo el árbol de accesibilidad de Chrome.
- La prueba de cinco segundos con personas sigue **NOT RUN**; la simulación con agentes no es una prueba con
  personas.
- No se ha tocado la Pi ni se ha desplegado nada.
- La comparación 415 → 44 no es homogénea: la baseline histórica usó otra definición y otros datos. U13a deja la
  cifra vigente en 46; 44 es la composición de #208. Tampoco se compara 146 → 190 en la ficha: el fixture y la
  definición no son los mismos.
- La cifra de 44 (y la vigente de 46) incluye el resumen visible del `<details>` de Carpetas; las 39 de #273 no lo
  incluían. En la ficha también se incluyó el resumen («Fuentes y atribución») en la medida conservadora de 48.

## 10. Reproducir

Prueba de contrato (requiere `TEST_DATABASE_URL` para el fixture de Postgres real):

```bash
python -m pytest tests/test_web_carpetas_pg.py::TestPresupuestoTexto -q
python -m pytest tests/test_web_series.py::TestPresupuestoTextoU21 -q
```

La cifra vigente de 46 de Carpetas (U13a) se reproduce con
`tests/test_web_carpetas_pg.py::TestPresupuestoTexto::test_la_cifra_de_46_es_reproducible_con_el_fixture_de_referencia`.
La prueba usa la plantilla real, una respuesta enlatada del servicio y el mismo recuento conservador que este
documento; la cifra histórica de 44 de #208 queda documentada en §3.2. La ficha se mide en Chrome con
`docs/design/ui-u21/medir_ficha.py`; el comando, el fixture y el SHA están en
`docs/design/ui-u21/verificacion-ficha-2026-10-21.md`. Carpetas sigue sin ensayo en navegador: **NOT RUN**.
