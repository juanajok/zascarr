# U21 — Presupuesto de texto: método, reescritura de Carpetas y límites (2026-10-21)

> **Estado: método y umbral aceptados por el responsable; «Pendientes por carpeta» reescrita y con prueba
> automática. La ficha de serie sigue pendiente. No hay medida en navegador real ni prueba de 5 segundos con
> personas: quedan NOT RUN / PARCIAL. #208 no se cierra.**

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

### 3.2 Después de la reescritura (HTML renderizado, 2026-10-21)

Fixture usado: 1.308 pendientes en 108 carpetas + 14 con serie sugerida, dos tarjetas visibles. Renderizado con la
plantilla real y una respuesta enlatada del servicio, sin tocar la base de datos ni la Pi.

| Medida | Resultado |
|---|---:|
| Palabras de la frase de entrada (`p.subtitle`) | **8** |
| Palabras antes de «Elegir la serie de esta carpeta» | **39** (38 sin el marcador decorativo `i` de los chips) |
| Palabras totales de `main` (incluye datos, detalles y listado) | 440 |
| Umbral de entrada / intro | ≤ 20 / ≤ 50 |

La medida de 39 es **conservadora** y se obtiene quitando los `<details>` cerrados antes de contar, como pide el
método. La prueba `tests/test_web_carpetas_pg.py::TestPresupuestoTexto` falla si la entrada o la intro superan el
umbral, si falta la garantía junto a la acción o si el subtítulo pasa de 20 palabras.

**Límite:** es una medida sobre HTML renderizado, no sobre píxeles de un navegador. No se ha comprobado con CSS
real, tema oscuro, 360 px ni lector de pantalla.

## 4. Método aceptado

Se reutiliza el patrón de `docs/design/ui-u17/inventariar_u17.py` y `docs/design/ui-u16/medir_u16.py` para la
medida en navegador. Para cada pantalla:

1. Cargar la ruta y esperar a que termine la carga.
2. Recorrer `main` en orden de documento.
3. Contar palabras de los nodos de texto **visibles**, excluyendo:
   - `nav`, `header`, `footer`, aviso legal;
   - `<details>` cerrados;
   - controles (`input`, `select`, `button`, `textarea`) y sus valores;
   - texto oculto (`display:none`, `visibility:hidden`, `[hidden]`).
4. Detener el contador en la **primera acción**: primer `a[href]`, `button`, `input[type=submit]`, `select` o
   `form` visible dentro de `main`. Se registra el selector y el texto de la acción.
5. Guardar `{pantalla, ruta, vista, tema, palabras_totales, palabras_antes_de_la_accion, accion, palabras_despues}`.

Umbral: **PASS** si `palabras_antes_de_la_accion <= 50` y la frase de entrada (`p.subtitle` o equivalente) tiene
≤ 20 palabras. **FAIL** si no. **NOT RUN** si no se pudo cargar.

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

## 6. Reescritura pendiente de la ficha de serie

- Frase de entrada ≤ 20 palabras: «Esta es la ficha de **{título}**. Revisa los datos y guarda si algo cambia.»
- ≤ 50 palabras antes de «Guardar».
- La retirada y sus consecuencias, **junto a «Guardar»** y en la confirmación, no en un párrafo en mayúsculas al
  principio.
- Las fuentes y la atribución, en un `<details>`.
- Nada de mayúsculas en párrafos; solo rótulos de ≤ 3 palabras.

**Estado: pendiente.** No se ha modificado `series_detail.html`.

## 7. Criterios de U21

| Criterio | Estado | Evidencia |
|---|---|---|
| 1. Regla en `CLAUDE.md` §6 | **PASS** | Texto vigente, umbrales provisionales |
| 2. Suite con recuento y umbral por pantalla adaptada | **PASS (contrato HTML)** | `TestPresupuestoTexto`: 8 y 39 palabras; falla si supera 20/50. Navegador real: NOT RUN. |
| 3. Carpetas ≤ 20 de entrada y ≤ 50 antes de la acción | **PASS (HTML)** | Subtítulo 8; 39 antes de «Elegir la serie de esta carpeta» |
| 4. Tarjeta con nombre, archivos, sugerencia/ausencia y estado | **PASS** | `h2`, chips, línea «N registros · Serie sugerida/Sin serie sugerida» antes de la acción |
| 5. Garantías junto a la acción con efecto | **PASS** | «No se crea ni se asigna nada hasta que confirmes.» junto al enlace |
| 6. Ficha de serie sin párrafos en mayúsculas | **PENDIENTE** | `series_detail.html` sin tocar |
| 7. Test de 5 segundos de #197 | **PARCIAL** | Simulación con agentes; no es una prueba con personas reales |
| 8. Regresiones de teclado, detalles, temas y 360 px | **NOT RUN** | Solo pruebas HTML; sin navegador real |

## 8. Decisiones adoptadas (2026-10-21)

1. **Se acepta el método de recuento** de nodos de texto visibles, sin nav/footer/details/controles, y el umbral
   de **50 palabras antes de la primera acción**.
2. **Carpetas va primero.** La ficha de serie queda para después.
3. **La comprobación automática se limita a las pantallas adaptadas**; Ajustes, Duplicados y Estado conservan sus
   historias y no se convierten en un falso PASS.
4. **No se toca la Pi.** No hay despliegue ni validación en producción.

## 9. Lo que NO está acreditado

- No hay medida en navegador real de la pantalla reescrita: solo HTML renderizado y una prueba de contrato.
- No se ha medido el tema oscuro, 360 px, teclado ni lector de pantalla.
- La ficha de serie sigue pendiente.
- El test de 5 segundos de U10 es una simulación con agentes, no una prueba con personas.
- No se ha tocado la Pi ni se ha desplegado nada.
- La comparación 415 → 39 no es homogénea: la baseline histórica usó otra definición y otros datos.

## 10. Reproducir

Prueba de contrato (requiere `TEST_DATABASE_URL` para el fixture de Postgres real):

```bash
python -m pytest tests/test_web_carpetas_pg.py::TestPresupuestoTexto -q
```

La prueba usa la plantilla real, una respuesta enlatada del servicio y el mismo recuento conservador que este
documento. Para una medida en navegador falta el ensayo aislado con Chrome, Postgres real y los datos sintéticos;
queda **NOT RUN**.
