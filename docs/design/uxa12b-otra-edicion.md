# UXA-12b · Otra edición de un número ocupado (refinamiento)

**Historia:** [#1250](https://github.com/juanajok/zascarr/issues/1250) · **Origen:** UXA-12
([#1129](https://github.com/juanajok/zascarr/issues/1129), PR [#1252](https://github.com/juanajok/zascarr/pull/1252))
· **Fecha:** 2026-11-24 · **Estado:** **B/C decidido por el PO**; el panel de número ocupado ya lo implementa (PR #1285).

## 1. Qué pasa hoy

- `Issue` tiene `UNIQUE(series_id, issue_number, volume)`; `format` (`IssueFormat`) es una columna
  pero **no** forma parte de la clave. `File` cuelga de un `Issue` y un `Issue` puede tener varios
  archivos.
- En la vista de vinculación (`services/vinculacion_previa.py`):
  - **un** `Issue` con ese número y **mismo** formato, con archivos → `numero_ya_existe`;
  - **un** `Issue` con ese número y **otro** formato → `colision_de_edicion` (texto: «ya existe
    como otra edición (formato)»);
  - **varios** `Issue` con ese número (volúmenes distintos) → `numero_ambiguo`, con candidatas H1
    para que la persona elija; eso **ya** permite dos #12 de distinta edición/volumen.
- UXA-12 (PR #1252) muestra el número ocupado, sus archivos y las salidas actuales (corregir el
  número, dejarlo pendiente, abrir el número), y decía que **registrarlo como otra edición todavía
  no se podía desde aquí**. La decisión B/C del 2026-11-24 sustituye ese aviso. Es solo lectura: no
  mueve ni borra nada.

**Datos reales** (ADR 0020, censo de la Pi del 2026-11-17): 228 series / 4.229 números; **0**
números repetidos con formatos distintos en la misma serie; **0** series con `Issue.volume`
distinto. No hay un caso real medido de esta historia; es una decisión de modelo, no una urgencia.

## 2. La definición de «edición» no es única en el proyecto

| Fuente | Qué dice | Consecuencia |
|---|---|---|
| **[ADR 0020](../adr/0020-edicion-y-colecciones-ccm.md)** (2026-11-17, aceptada) | No se crea entidad `Edition`; `Series` es la unidad de catálogo y **cada edición/línea es una `Series` distinta** | Otra edición = otra serie |
| **[Glosario U7](ui-u7/glosario-u7.md)** (2026-11-14) | «Edición: formato, editorial, idioma, calidad (`IssueFormat` y filas de `Issue` distintas)» | Otra edición = otro `Issue` |
| **D3/Mejoras** | Una edición mejor (digital frente a escaneo, más resolución) se importa **como otro archivo del número** | La calidad/origen es `File`, no otra edición |

Las tres dimensiones deben separarse:

1. **Línea/edición editorial** (editorial, idioma, línea de numeración): `Series` (ADR 0020).
2. **Formato de publicación** (grapa, TPB, ómnibus, tomo): `IssueFormat`. Hoy cabe **un** `Issue`
   por `(serie, número, volumen)`; un formato distinto en el mismo volumen choca.
3. **Copia/origen/calidad** (escaneo, digital, CBZ/CBR): `File`; un número puede tener varios.

La conversación pendiente es si el formato 2 puede convivir con el mismo número **en la misma
serie** o si, como en las referencias, es otra línea (serie) o un volumen distinto.

## 3. Benchmark (ya cerrado; no se repite la lectura)

Ficha de referencia: [`benchmark-identidad-editorial.md`](benchmark-identidad-editorial.md)
(2026-10-01) y [`benchmark-BL-D3-mejoras.md`](benchmark-BL-D3-mejoras.md). Versiones fijadas:

- **Kapowarr** `c191dda` (v1.3.2, 2026-09-14), GPL-3.0. La unidad es el **volumen de Comic Vine**;
  un TPB/ómnibus es **otro volumen** con su(s) número(s), no un issue del mismo volumen; los
  archivos se asocian a issues con `issues_files` N:M para packs. **No hay entidad «edición»**.
- **Mylar3** `cdc94a4` (v0.8.3, 2025-08-17), GPL-3.0. **1 archivo ↔ 1 fila** (`issues.Location`);
  no hay N:M; **no hay entidad «edición»**; una colisión del mismo número se desambigua por **año**,
  no por edición. No se adopta.

**Hallazgo:** ninguna de las dos modela «mismo volumen, mismo número, otro formato» como dos
ediciones del mismo `Issue`/volumen: el formato/volumen distinto es **otra línea**. El patrón que
ZascArr ya copió de Kapowarr (ADR 0020) es «otra edición = otra serie/volumen»; el `IssueFormat` de
ZascArr es más fino que el de las referencias y es justo el punto a decidir.

**Barrera legal:** solo se han leído esquemas y comportamiento; no se copia código de Kapowarr ni de
Mylar3 (GPL-3.0 ambas; ZascArr también, pero la regla de §13 es no reutilizar implementaciones sin
revisar el fichero y sus avisos).

## 4. Opciones

| | Qué sería | Coste/riesgo | ¿Referencia? | ¿Datos? |
|---|---|---|---|---|
| **A. Otro `Issue` en la misma serie** | Añadir `format` a la clave única `(series, number, volume, format)`; migración; el panel ofrece «registrar otra edición» con formato/volumen; se crea otro `Issue` y el archivo se vincula a él | Migración + cambiar `existentes`, `numero_ambiguo`, ficha, Mejoras y pruebas; dos `Issue` con el mismo número/volumen y distinto formato; el «número» deja de ser único por serie | **No**: las referencias hacen otra línea/volumen | 0 casos medidos |
| **B. Otra edición = otra `Series`** (recomendada) | No se toca el modelo. El panel del número ocupado dice que, si es otra línea/edición, se cree o elija **su serie**; el archivo sigue pendiente hasta vincularlo a esa serie. Enlace al alta de serie y a la serie si ya existe | Sin migración; cambio de texto/enlace y pruebas; la persona hace dos pasos (crear/elegir serie y vincular) | **Sí**: Kapowarr (volumen = unidad) y ADR 0020 | 0 casos, coherente con la decisión vigente |
| **C. Varios `File` bajo el mismo `Issue`** | El formato distinto no crea `Issue`: se trata como otra copia/calidad del mismo número, con `File` y la calidad/origen | Sin migración para el modelo, pero **no representa** un TPB frente a una grapa: el `Issue.format` es uno; Mejoras ya usa `File` para calidad | **Sí** para copias/calidad (D3), **no** para formato editorial | 0 casos |
| **D. No hacer nada** | Se mantienen las salidas actuales; el panel sigue diciendo que no se puede | 0 | — | — |

## 5. Recomendación

**B para «otra edición» y C para «otra copia/calidad».** **Aceptada por el PO el 2026-11-24: B y
C.** Es lo que ya decidió el ADR 0020, lo que hacen las referencias y lo que no exige migración ni
inventar una entidad. El caso «mismo número, mismo volumen, distinto formato» se trata como **otra
línea/edición**: se crea o elige su serie. La calidad/origen de un archivo (digital, escaneo,
CBZ/CBR) sigue siendo un `File` del mismo `Issue` (Mejoras/D3), no una edición nueva.

**No recomiendo A en este ciclo:** no hay ningún caso medido, las referencias no lo hacen, y cambiar
la clave única toca ficha, Mejoras, huecos y la noción de «número» de toda la app. Si el PO quiere
formatos conviviendo en la misma serie, A exige un ADR nuevo y una migración; se puede hacer, pero
con esas condiciones y no como efecto colateral de UXA-12b.

**El glosario queda actualizado** a B/C: «edición» es la serie/línea (ADR 0020), el `IssueFormat`
es el formato de publicación y la copia/calidad es el `File` (`CLAUDE.md` §14.1 y §14.2). Los
rótulos históricos se cambian en la PR de etiquetas: «Otros volúmenes de este número» (ficha) y
«Mejores copias» (Mejoras).

## 6. Decisiones del PO (resueltas)

**Decidido el 2026-11-24: 1 B; 2 C; 3 C (otro archivo); 4 la persona; 5 sí; 6 no A ahora.**

1. **¿Qué es «otra edición»?** ¿Otra `Series`/línea (B) o otro `Issue` en la misma serie (A)?
   *Recomendación: B.*
2. **¿Una calidad/origen distinto** (digital frente a escaneo, CBZ frente a CBR) es otra edición o
   otro `File` del mismo número? *Recomendación: otro `File` (C), como en D3/Mejoras.*
3. **¿Un archivo con el mismo formato y número** (copia) es otro `File` del `Issue` existente o un
   nuevo `Issue`? *Recomendación: otro `File`; el flujo de Duplicados/Mejoras ya lo trata.*
4. **¿Quién decide?** La persona, en la confirmación de vinculación; nunca una regla automática.
5. **Si B:** ¿el panel del número ocupado debe ofrecer un enlace a «crear la serie de esa edición» y
   a «elegir otra serie», dejando el archivo pendiente? *Recomendación: sí; sin botón de «otra
   edición» dentro de la misma serie.*
6. **Si A:** ¿se acepta un ADR nuevo y una migración de la clave única, con el coste de ficha,
   Mejoras y huecos? *Recomendación: no ahora.*

## 7. Implementación de B (hecha en esta rama)

- Bloque `a.ocupante` de [`_vinculacion_revision.html`](../../src/zascarr/web/templates/_vinculacion_revision.html)
  actualizado: si el formato es distinto (`colision_de_edicion`), dice que otra edición es otra línea
  y enlaza a **elegir o crear la serie de esa edición**; si el formato es el mismo
  (`numero_ya_existe`), dice que una copia o calidad distinta **no es una edición nueva**. Conserva
  corregir el número, dejar pendiente, abrir el número y la garantía de que no se mueve nada.
- Sin cambios en `Issue`, la clave única, `vinculacion_previa.py` ni la base de datos.
- `tests/test_vinculacion_ocupado_uxa12_pg.py` actualizado: copia ≠ edición y enlace a la serie en
  la colisión; el CI lo ejecuta con Postgres real.
- Glosario actualizado (B/C); los rótulos de ficha/Mejoras se cambian en la PR de etiquetas. No se
  cierra #1250 hasta el despliegue.

## 8. Si el PO elige A: lo que habría que hacer (no ahora)

- ADR nuevo (reabre la parte de formato de ADR 0020), migración aditiva de la clave única
  `(series_id, issue_number, volume, format)`; revisar `existentes`/`numero_ambiguo`/`_ocupantes`,
  ficha, Mejoras, huecos, `find_issue`, importador y pruebas; formulario de formato/volumen en la
  confirmación; concurrencia por la clave única; dos `Issue` con el mismo número/volumen y formatos
  distintos. Coste M; datos 0. **No se hace sin el ADR y sin el PO.**

## 9. Límites de esta ficha

- Implementa B/C en el panel; no migra ni cambia el modelo. La tarjeta pasa a «En revisión».
- Los rótulos se cambian en la PR de etiquetas: «Otros volúmenes de este número» (ficha) y «Mejores
  copias» (Mejoras).
- El benchmark es lectura estática de las fichas ya cerradas (Kapowarr/Mylar3); no se ejecutaron
  ni se abrió su UI. No hay caso real en la biblioteca de la Pi (0 medidos).
- No hay navegador, lector de pantalla ni prueba con personas: la decisión es de producto y de
  modelo.
