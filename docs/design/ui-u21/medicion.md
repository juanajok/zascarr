# U21 — Presupuesto de texto: línea base y plan de medida (2026-10-21)

> **Estado: regla escrita y baseline histórico; la medida actual y las reescrituras siguen pendientes.**
> No se ha modificado ninguna plantilla de producto. #208 permanece en «En refinamiento».

## 1. Regla vigente

`CLAUDE.md` §6, «Presupuesto de texto» (decidido el 2026-10-15; umbrales provisionales hasta U10):

- Una frase de entrada por pantalla, **≤ 20 palabras**, que diga qué se hace.
- **≤ 50 palabras visibles antes de la primera acción**.
- La garantía («no se mueve ni se renombra nada») va **junto a la acción con efecto**, no en la cabecera de
  pantallas que no cambian nada.
- Resumen antes que listado. Mayúsculas solo en rótulos de ≤ 3 palabras.
- Los textos explican la tarea, no el contrato: sin «token», «lote» ni códigos internos.

La regla ya está en el repositorio. Lo que falta es **medirla de forma automática** y reescribir las dos pantallas
que no tienen otra historia: «Pendientes por carpeta» y la ficha de serie.

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

**No es el estado actual.** `main` ha cambiado desde entonces (U14, U16, U17, U19, U20). Hay que volver a medir.

## 3. Baseline actual por inspección de plantilla (no es una medida de navegador)

`sí` = el texto está antes de la primera acción visible; `detalle` = va dentro de `<details>` o después de la acción.

En `src/zascarr/web/templates/carpetas.html` (origin/main `8589b47`), el orden es:

1. `h1`: «Pendientes por carpeta» (3 palabras).
2. Subtítulo: «Lo que sigue pendiente, agrupado por la carpeta donde está. Esta pantalla es solo para mirar: no se
   crea ni se asigna nada. Desde cada carpeta puedes abrir el asistente para elegir su serie; abrirlo tampoco crea
   nada ni consulta ninguna fuente.» (**≈ 50 palabras**).
3. Aviso `info`: «Son registros pendientes de verificar, no archivos confirmados. Esta pantalla lee la base de datos
   y no comprueba el disco: un registro puede apuntar a un archivo que ya no esté donde se anotó. Una carpeta o un
   nombre son pistas, no decisiones.» (**≈ 49 palabras**).
4. Enlace «← Volver a Por revisar»: **primera acción**.
5. Después, resumen, tarjetas y, dentro de cada tarjeta, «Elegir la serie de esta carpeta».

**Estimación:** > 100 palabras antes de la primera acción, muy por encima de 50. La garantía y la explicación del
contrato están en la cabecera, no junto a la acción. Es el mismo patrón que midió la auditoría (415 palabras antes
de la primera acción en la pantalla completa, con datos reales).

En `series_detail.html` hay que medir lo mismo: la ficha tiene un solo control principal («Guardar») y la auditoría
midió 63 palabras antes de la acción y 52 en mayúsculas. No se ha vuelto a medir.

## 4. Cómo se medirá (método reproducible)

Se reutiliza el patrón de `docs/design/ui-u17/inventariar_u17.py` y `docs/design/ui-u16/medir_u16.py`:
Chrome contra el ensayo aislado, Postgres real, datos sintéticos, escritorio 1280×900 y estrecha 390×844, claro y
oscuro.

Para cada pantalla:

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

La comprobación automática debe ser una prueba de contrato, no solo un script de evidencia: un test que falle si
una plantilla de las pantallas adaptadas supera el umbral. Para las rutas que necesitan BD, se usa el patrón de
Postgres real de `tests/*_pg.py`; para las que no, `TestClient` + `FakeSession`.

## 5. Reescritura propuesta de «Pendientes por carpeta»

Objetivo: mantener la confianza sin gastar 100 palabras antes de la primera acción.

**Antes (estimado >100 palabras):** subtítulo + aviso + enlace.

**Después (propuesta):**

```text
Pendientes por carpeta
Elige una carpeta para revisar sus archivos.            ← 8 palabras

[1.308 en 108 carpetas] [14 sueltos]                    ← resumen

← Volver a «Por revisar»                                ← primera acción

...
```

En cada tarjeta:

```text
Flash (1987)
155 registros · Sin serie
Serie sugerida: Flash (1987) · 94 %
[Elegir la serie de esta carpeta]                       ← acción con efecto
No se crea ni se asigna nada hasta que confirmes.       ← garantía junto a la acción
▸ ¿De dónde salen estos datos?                          ← detalles plegados
```

El texto técnico («lee la base de datos y no comprueba el disco», «un registro puede apuntar a un archivo que ya no
esté») pasa a `¿De dónde salen estos datos?`, junto al resumen o a la tarjeta, no a la cabecera.

**Riesgo:** quitar la tranquilidad de la cabecera puede aumentar la desconfianza. Por eso se mueve junto a la
acción con efecto y se valida con el test de 5 segundos de U10 («¿qué puedes hacer aquí?»), antes y después.

## 6. Reescritura propuesta de la ficha de serie

- Frase de entrada ≤ 20 palabras: «Esta es la ficha de **{título}**. Revisa los datos y guarda si algo cambia.»
- ≤ 50 palabras antes de «Guardar».
- La retirada y sus consecuencias, **junto a «Guardar»** y en la confirmación, no en un párrafo en mayúsculas al
  principio.
- Las fuentes y la atribución, en un `<details>`.
- Nada de mayúsculas en párrafos; solo rótulos de ≤ 3 palabras.

## 7. Criterios de U21

| Criterio | Estado | Evidencia |
|---|---|---|
| 1. Regla en `CLAUDE.md` §6 | **PASS** | Texto vigente, umbrales provisionales |
| 2. ≤ 50 palabras antes de la primera acción, con comprobación automática | **NOT RUN** | No hay script ni test ejecutado; baseline actual estimado >100 en Carpetas |
| 3. «Pendientes por carpeta» reescrita (415 → ≤ 50) | **PENDIENTE** | Propuesta en §5; no se ha tocado la plantilla |
| 4. Ficha de serie reescrita | **PENDIENTE** | Propuesta en §6; no se ha tocado la plantilla |
| 5. Garantías junto a la acción con efecto | **PENDIENTE** | Hoy están en la cabecera de Carpetas |
| 6. Test de 5 segundos en U10 | **PARCIAL** | Simulación con agentes hecha; no es una prueba con personas reales |

## 8. Decisión necesaria

- ¿Se acepta el método de recuento (nodos de texto visibles, sin nav/footer/details/controles) y el umbral de 50?
- ¿Se prioriza la reescritura de Carpetas antes que la ficha de serie, o al revés?
- ¿La comprobación automática se limita a las pantallas adaptadas o se aplica a todas? La regla dice «pantallas
  adaptadas»; Ajustes, Duplicados y Estado tienen sus propias historias.

## 9. Lo que NO está acreditado

- No se ha ejecutado la medida actual en navegador.
- No se ha modificado ninguna plantilla.
- No hay prueba automática nueva.
- No se ha validado el umbral con personas reales; U10 es una simulación.
- No se ha tocado la Pi.
