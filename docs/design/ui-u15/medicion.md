# U15 — ¿La sugerencia de tradición sale de la fuente o de la obra? (2026-10-21)

> **Estado: modelo reproducible y contrato de UI; la medición contra fuentes reales sigue en NOT RUN.**
> No se han consultado Comic Vine, AniList, Tebeosfera ni GCD. Los 20 títulos de `titulos.json` son fixtures
> sintéticos y la fuente asignada es parte del modelo, no un resultado observado. **#202 no se cierra con esto.**

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

## 4. Lo que ya hace la UI

En `_resultados_descubrir.html` (origin/main `8589b47`):

```html
<select name="tradition" required aria-label="Tradición">
  <option value="" selected disabled>Elige la tradición…</option>
  ...
</select>
<small>La fuente sugiere: {{ ... }}. Tú decides.</small>
```

- **No hay preselección:** el marcador vacío es el único `selected`; la sugerencia es texto, no un valor aplicado.
  La prueba existente `tests/test_web_discovery.py::test_la_tradicion_no_viene_preseleccionada_y_la_sugerencia_es_solo_un_texto`
  lo comprueba para una sugerencia `MANGA`.
- **La persona elige:** el `select` es `required` y no tiene valor por defecto.
- **Lo que falta:** el texto dice «Tú decides», pero **no dice por qué** la sugerencia puede ser errónea. No explica
  que es una pista de la fuente y no de la obra. El criterio de U15 pide «se dice por qué».

## 5. Criterios de U15

| Criterio | Resultado | Evidencia |
|---|---|---|
| 1. Medir si la sugerencia sale de la fuente o de la obra | **PASS (código)** | `discovery.py`: mapeo fuente → tradición; auditoría Mortadelo |
| 2. Medición con ≥20 títulos reales | **NOT RUN** | No se consultaron fuentes; `titulos.json` es un modelo, no una muestra real |
| 3. No preseleccionar tradición | **PASS (código/prueba existente)** | `option value="" selected disabled`; test de #U14 |
| 4. Explicar en español por qué la persona debe elegirla | **PARCIAL** | «Tú decides» no explica que la sugerencia es de la fuente y puede no ser de la obra |
| 5. Decisión registrada | **PENDIENTE** | Propuesta: no preseleccionar nunca; cambiar el texto; no auto-aplicar |

## 6. Decisión propuesta

1. **Mantener la no preselección** en todos los casos, aunque la fuente sea «fiable»: la evidencia de código muestra
   que la sugerencia no mira la obra.
2. **Cambiar el texto** a algo equivalente a:
   > «La fuente lo clasifica como **Grapa americana**. Es solo una pista de la fuente, no de la obra: elige tú.»
   El cambio es de una línea de plantilla y su prueba; no toca lógica de negocio ni esquema.
3. **No cerrar #202** hasta que exista la prueba del texto y una decisión escrita sobre la medición real:
   - opción A: ejecutar 20 búsquedas reales con sus respuestas guardadas (fuente, id, fecha, sugerencia) y anexarlas;
   - opción B: aceptar el modelo de código + la no preselección como evidencia suficiente, con la limitación visible.
4. **No se toca la Pi.**

## 7. Reproducir

```bash
python3 docs/design/ui-u15/medir_u15.py
```

Salida: tabla de 20 títulos, coincidencias por fuente y total. Sin red, sin claves, sin base de datos.

## 8. Archivos

- `titulos.json` — 20 fixtures y tradición de referencia.
- `medir_u15.py` — modelo determinista del mapeo actual.
- `docs/design/auditoria-ui-2026-10-15.md` §M3 y §8 — evidencia original de Mortadelo.
- `tests/test_web_discovery.py` — contrato de no preselección.
