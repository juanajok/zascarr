# U15 — ¿La sugerencia de tradición sale de la fuente o de la obra? (2026-10-21)

> **Estado: modelo reproducible + 20 búsquedas reales en GCD y Tebeosfera (2026-10-21); Comic Vine y AniList
> siguen NOT RUN. Cambio de texto aplicado y probado. #202 queda en revisión, no cerrada.**
> `titulos.json` sigue siendo un modelo determinista; la medición real está en `resultados-reales.json` y
> `resultados-reales.md`. No se ha usado la app ni la base de datos. La Pi no se ha tocado.

## 1. Pregunta

La auditoría de 2026-10-15 observó que, al buscar *Mortadelo*, la fuente sugería **«Grapa americana»**. La hipótesis
de U15 es que la sugerencia se deriva de la **fuente** que devuelve el resultado, no de la **obra**. Si es así, la
sugerencia no es fiable para títulos españoles buscados en Comic Vine y no debe preseleccionarse.

## 2. Lo que dice el código (hecho verificable)

En `src/zascarr/services/discovery.py` (origin/main `8589b47`):

| Fuente | `tradition_guess` | ¿Mira la obra? |
|---|---|---|
| Comic Vine | `ComicTradition.AMERICAN` | No |
| AniList | `ComicTradition.MANGA` | No |
| Tebeosfera | `ComicTradition.TEBEO` | No |
| GCD | `ComicTradition(h.tradition_guess)` | Solo lo que devuelve GCD |

**Conclusión de código:** la sugerencia es un atributo de la fuente, no una inferencia sobre el título. Cualquier
resultado de Comic Vine se sugiere como americano, incluido *Mortadelo*. Esto confirma la hipótesis a nivel de
implementación y explica el hallazgo de la auditoría.

## 3. Modelo con 20 títulos

`titulos.json` contiene 20 títulos con una tradición de referencia provisional y la fuente que, en el modelo, los
devuelve. `medir_u15.py` aplica el mapeo actual y cuenta coincidencias.

| Grupo | Títulos | Fuente simulada | Coincidencias |
|---|---|---|---|
| Tebeo español | Mortadelo, Zipi y Zape, Capitán Trueno, El Jabato, Superlópez, Anacleto, 13 Rue del Percebe, Carpanta | Comic Vine | **0/8** |
| Franco-belga | Astérix, Tintín, Lucky Luke, Thorgal | Comic Vine | **0/4** |
| Americano | Batman, Spider-Man, Watchmen, Sandman | Comic Vine | **4/4** |
| Manga | Dragon Ball, One Piece, Naruto, Akira | AniList | **4/4** |
| **Total** | | | **8/20** |

**Lectura:** en el modelo, **12 de 20** sugerencias discrepan; **8 de 8** títulos de tebeo español salen como
«Grapa americana» porque los devuelve Comic Vine. El patrón no es aleatorio: la fuente acierta cuando su dominio
coincide con la tradición (americano en Comic Vine, manga en AniList) y falla cuando no.

**Límite:** esto no mide cuántos resultados reales devuelve cada fuente para esos títulos, ni si el título aparece
primero en Comic Vine o en Tebeosfera. Es un modelo determinista del mapeo, no una tasa de acierto en producción.

## 3.b Medición real de las 20 búsquedas (2026-10-21)

Se ejecutaron **20 búsquedas reales** con `buscar_20.py` contra las dos fuentes públicas que respondieron, con
3 resultados por fuente y sus límites de cortesía: GCD (2 s) y Tebeosfera (2,5 s). Quedan guardados la consulta, el
resultado, el identificador, la fecha y la sugerencia en `resultados-reales.json`; el resumen legible está en
`resultados-reales.md`. No se usó la app ni la base de datos.

| Fuente | Consultas | Con resultados | Sugerencia del primer resultado | Coincidencias con la referencia | Lectura |
|---|---:|---:|---|---:|---|
| GCD | 20 | 16 | según idioma/país de la edición | **10/16** | 6 discrepancias, todas por la edición devuelta: Tintín español → `tebeo`; Spider-Man francés → `franco_belgian`; Dragon Ball francés → `franco_belgian`; One Piece y Naruto → `other`; Akira → `american`. |
| Tebeosfera | 20 | 20 | **20/20 `tebeo`** | 8/20 | No mide acierto: asigna `tebeo` a todo. El primer resultado a veces es otra obra (p. ej. *Mortadelo* → *ALEGRES HISTORIETAS*). Las 8 «coincidencias» son exactamente los 8 títulos cuya referencia es `tebeo`. |
| Comic Vine | 0 | **NOT RUN** | — | — | Sin `COMICVINE_API_KEY` en el entorno. Es la fuente del caso *Mortadelo*. |
| AniList | 0 | **NOT RUN** | — | — | 403: «The AniList API has been temporarily disabled due to severe stability issues.» |

**Lo que prueba:** en las dos fuentes medidas, la sugerencia se deriva de la **fuente/edición**, no de la obra.
GCD etiqueta Tintín como tebeo por una edición española y Dragon Ball como franco-belga por una edición francesa;
Tebeosfera etiqueta todo como tebeo. Es el mismo patrón que el código muestra para Comic Vine y AniList.

**Lo que no prueba:** no reproduce las 9 respuestas de Comic Vine para *Mortadelo* (la fuente del hallazgo original)
ni mide AniList. Esas dos fuentes quedan **NOT RUN**, no PASS. La conclusión sobre Comic Vine se apoya en el código
(`ComicTradition.AMERICAN` para cualquier resultado), no en esta muestra.

**Límite de la muestra:** 20 títulos elegidos a mano, no representativos; la referencia de tradición de
`titulos.json` es provisional y no está verificada contra un catálogo externo. Los recuentos son descriptivos.

## 4. Lo que ya hace la UI

En `_resultados_descubrir.html` (origin/main `8589b47`):

```html
<select name="tradition" required aria-label="Tradición">
  <option value="" selected disabled>Elige la tradición…</option>
  ...
</select>
<small>La fuente lo clasifica como {{ ... }}. Es solo una pista de la fuente, no de la obra: elige tú.</small>
```

- **No hay preselección:** el marcador vacío es el único `selected`; la sugerencia es texto, no un valor aplicado.
  `tests/test_web_discovery.py` comprueba el caso `MANGA`; `tests/test_asistente_carpetas_pg.py` comprueba el mismo
  contrato en el asistente de carpetas.
- **La persona elige:** el `select` es `required` y no tiene valor por defecto.
- **El texto ya explica el porqué:** dice que la clasificación es de la fuente, que no es de la obra y que la
  elección es de la persona. Se aplicó en `_resultados_descubrir.html` y en `_asistente_macros.html`.

## 5. Criterios de U15

| Criterio | Resultado | Evidencia |
|---|---|---|
| 1. Medir si la sugerencia sale de la fuente o de la obra | **PASS (código)** | `discovery.py`: mapeo fuente → tradición; auditoría Mortadelo |
| 2. Medición con ≥20 títulos reales | **PASS con límites** | 20 títulos, 40 consultas reales a GCD y Tebeosfera; Comic Vine y AniList NOT RUN, con motivo. |
| 3. No preseleccionar tradición | **PASS** | `option value="" selected disabled`; pruebas de Descubrir y del asistente de carpetas. |
| 4. Explicar en español por qué la persona debe elegirla | **PASS** | Texto aplicado en `_resultados_descubrir.html` y `_asistente_macros.html`; pruebas actualizadas. |
| 5. Decisión registrada | **PASS** | No preseleccionar, explicar el origen y mantener la elección humana; sin auto-aplicar. |

## 6. Decisión adoptada (2026-10-21)

1. **Mantener la no preselección** en todos los casos, aunque la fuente sea «fiable»: la evidencia de código y la
   medición real muestran que la sugerencia no mira la obra.
2. **Texto aplicado** en Descubrir y en el asistente de carpetas:
   > «La fuente lo clasifica como **Grapa americana**. Es solo una pista de la fuente, no de la obra: elige tú.»
   No toca lógica de negocio ni esquema.
3. **Medición real ejecutada parcialmente:** GCD y Tebeosfera respondieron; Comic Vine no tiene clave en este
   entorno y AniList devolvió 403. Las dos fuentes que faltan quedan **NOT RUN**, no PASS. No se inventan resultados.
4. **#202 no se cierra** hasta que la PR pase CI y se acepte la evidencia; el tablero no la marca «Hecha» sin
   despliegue o aceptación explícita de NOT RUN.
5. **No se toca la Pi.**

## 7. Reproducir

Modelo determinista (sin red):

```bash
python3 docs/design/ui-u15/medir_u15.py
```

Medición real (red; GCD y Tebeosfera; respeta sus límites):

```bash
PYTHONPATH=src python3 docs/design/ui-u15/buscar_20.py
```

Salida: `resultados-reales.json` y `resultados-reales.md`. Comic Vine requiere `COMICVINE_API_KEY` y AniList
depende de que su API vuelva a estar disponible; si no, el script los registra como no disponibles.

## 8. Archivos

- `titulos.json` — 20 fixtures y tradición de referencia.
- `medir_u15.py` — modelo determinista del mapeo actual.
- `buscar_20.py` — 20 búsquedas reales en GCD y Tebeosfera.
- `resultados-reales.json` / `resultados-reales.md` — respuestas, IDs, fecha y sugerencias.
- `docs/design/auditoria-ui-2026-10-15.md` §M3 y §8 — evidencia original de Mortadelo.
- `tests/test_web_discovery.py` y `tests/test_asistente_carpetas_pg.py` — contrato de no preselección y texto.
