# U15 — ¿La sugerencia de tradición sale de la fuente o de la obra? (2026-10-21)

> **Estado: modelo reproducible + 20 búsquedas reales en GCD y Tebeosfera + verificación en Chrome real
> (2026-10-21); Comic Vine y AniList siguen NOT RUN. #276 (U15b) implementado en rama con ausencia de sugerencia y
> procedencia; PR pendiente de revisión. #202 sigue abierta, no cerrada: el código no sustituye la evidencia que
> falta ni el despliegue.**
> `titulos.json` sigue siendo un modelo determinista; la medición real está en `resultados-reales.json` y
> `resultados-reales.md`; la verificación de navegador está en `verificacion-navegador-2026-10-21.md`; el contrato
> de #276 está en `u15b-ausencia-procedencia.md`. La app se usó solo contra una base desechable y una biblioteca
> temporal. La Pi no se ha tocado.

## 1. Pregunta

La auditoría de 2026-10-15 observó que, al buscar *Mortadelo*, la fuente sugería **«Grapa americana»**. La hipótesis
de U15 es que la sugerencia se deriva de la **fuente** que devuelve el resultado, no de la **obra**. Si es así, la
sugerencia no es fiable para títulos españoles buscados en Comic Vine y no debe preseleccionarse.

## 2. Lo que dice el código (hecho verificable)

En `src/zascarr/services/discovery.py` (origin/main `8589b47`; la procedencia es de #276, en esta rama):

| Fuente | `tradition_guess` | Procedencia (#276) | ¿Mira la obra? |
|---|---|---|---|
| Comic Vine | `ComicTradition.AMERICAN` | `por_defecto` | No |
| AniList | `ComicTradition.MANGA` | `explicita` | No |
| Tebeosfera | `ComicTradition.TEBEO` | `por_defecto` | No |
| GCD | `ComicTradition(h.tradition_guess)`; `None` si no reconoce idioma/país | `transformada`; `None` en la ausencia | Solo lo que devuelve GCD |

**Conclusión de código:** la sugerencia es un atributo de la fuente, no una inferencia sobre el título. Cualquier
resultado de Comic Vine se sugiere como americano, incluido *Mortadelo*. Esto confirma la hipótesis a nivel de
implementación y explica el hallazgo de la auditoría. GCD ya no convierte su `other` en una sugerencia: #276 lo
trata como ausencia.

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
(`ComicTradition.AMERICAN` para cualquier resultado), no en esta muestra. La medición se hizo con el contrato
anterior a #276: los `other` de GCD (One Piece, Naruto) se conservan como dato histórico, pero la presentación
actual los trata como **ausencia de sugerencia**, no como una tradición sugerida.

**Límite de la muestra:** 20 títulos elegidos a mano, no representativos; la referencia de tradición de
`titulos.json` es provisional y no está verificada contra un catálogo externo. Los recuentos son descriptivos.

## 4. Lo que ya hace la UI

En `_resultados_descubrir.html` y `_asistente_macros.html` (tras #276):

```html
<select name="tradition" required aria-label="Tradición">
  <option value="" selected disabled>Elige la tradición…</option>
  ...
</select>
{% if r.sugerida %}
<small>{{ etiqueta | pista_de_tradicion(r.procedencia) }}</small>
{% endif %}
```

`pista_de_tradicion` conserva la copy de U15 para `explicita` y dice si la sugerencia se transformó, es un valor
por defecto o su origen es desconocido. Sin sugerencia no hay `<small>` de pista. El detalle y la copia exacta
están en [`u15b-ausencia-procedencia.md`](u15b-ausencia-procedencia.md) §4.

- **No hay preselección:** el marcador vacío es el único `selected`; la sugerencia es texto, no un valor aplicado.
  `tests/test_web_discovery.py` comprueba los cuatro escenarios de presentación; el quinto se completa en
  `test_descubrir_dos_pasos_pg.py`. `tests/test_asistente_carpetas_pg.py` comprueba el mismo contrato en el
  asistente de carpetas. El mapeo completo a los cinco escenarios de CA6 está en §5.
- **La persona elige:** el `select` es `required` y no tiene valor por defecto.
- **El texto ya explica el porqué:** dice de dónde sale la sugerencia, que no es de la obra y que la elección es de
  la persona. Se aplicó en `_resultados_descubrir.html` y en `_asistente_macros.html`.
- **Comprobado en Chrome real (2026-10-21):** búsqueda real de `Mortadelo`, 20/20 selectores vacíos y obligatorios,
  0 preselecciones; al elegir **Manga** sobre una pista **Tebeo español**, la vista previa muestra Manga y la base
  sigue sin series. Ver [`verificacion-navegador-2026-10-21.md`](verificacion-navegador-2026-10-21.md) §4.
  Esa verificación es anterior a #276 y **no cubre** la nueva procedencia ni la ausencia; las pruebas automáticas
  de #276 sí.

## 5. Criterios de aceptación de #202 (mapeo 1:1)

| CA de #202 | Estado | Evidencia y límite |
|---|---|---|
| 1. Medición reproducible, con datos, procedencia y estado por observación; por candidata y por título, sin inflar aciertos | **PASS con límites** | `resultados-reales.json` guarda consulta, fuente, resultado, ID, fecha y sugerencia; 20 títulos × 2 fuentes = 40 consultas. Solo se evalúa el **primer resultado** de cada fuente: los recuentos son por título/fuente y no suman varias candidatas de una consulta. Comic Vine y AniList quedan NOT RUN. |
| 2. Ficha con fecha, versión, muestra, denominadores, discrepancias y limitaciones; criterio de decisión antes de concluir | **PASS** | Ficha fechada (2026-10-21), commits `8589b47`/`b540726`, 20 títulos, denominadores 16/20 y 8/20, discrepancias por edición y límites. El protocolo y los criterios se fijaron en la issue antes de medir; la decisión está en §6. |
| 3. Distinguir sugerencia respaldada por evidencia explícita, sugerencia no fiable y evidencia insuficiente; no declarar fiable una fuente entera por una muestra pequeña | **PASS con límites** | §2 separa el valor por defecto de Comic Vine/AniList/Tebeosfera de la transformación de GCD; §3.b mide GCD (10/16) y Tebeosfera (8/20). Comic Vine y AniList no se midieron: no se declaran fiables ni se extrapola su comportamiento. |
| 4. No preseleccionar; explicar en español que la persona debe elegir; no sustituir su elección ni confundir tradición con formato | **PASS** | El `select` es `required` y solo tiene seleccionado el marcador vacío; el texto atribuye la pista a la fuente. Las pruebas de Postgres confirman que la tradición elegida (p. ej. Manga) manda sobre la sugerida (Americana) y que el alta guarda la elegida. Además, Chrome real (2026-10-21): 20/20 selectores vacíos, 0 preselecciones y texto completo; ver `verificacion-navegador-2026-10-21.md` §4.1. No hay campo de formato en esta presentación. |
| 5. Cambio limitado y contrato vigente; si no permite representar falta de selección o procedencia, registrar impedimento y proponer trabajo separado sin ampliarlo en silencio | **PASS** | #273 registró el impedimento y abrió **#276** (U15b). #276 amplía el contrato de forma explícita: `tradition_guess` opcional, procedencia con cuatro valores, token retrocompatible y copy diferenciada. No cambia el enrutado del enriquecedor ni añade fuentes. |
| 6. Pruebas de los cinco escenarios de CA6, regresión automática y CI | **PASS en local; #202 sigue abierta** | Ver tabla siguiente. Los cinco escenarios tienen prueba automática; la elección explícita se completa contra Postgres real. La suite no-Postgres pasa (3968 tests) y las pruebas PG de Descubrir, descubrimiento por grupo y asistente pasan. **No** se ha desplegado ni se ha repetido la verificación en Chrome con la procedencia nueva. #202 no se cierra hasta su DoD y el Sprint 0. |

| Escenario de CA6 | Prueba | Estado |
|---|---|---|
| Dato explícito respaldado | `TestEscenariosCA6DeU15::test_dato_explicito_respaldado_se_presenta_como_pista_y_no_se_preselecciona` | **PASS**: conserva la copy de U15. |
| Sugerencia no fiable | `TestBuscar::test_la_tradicion_no_viene_preseleccionada_y_la_sugerencia_es_solo_un_texto` + `TestEscenariosCA6DeU15::test_sugerencia_no_fiable_de_comic_vine_para_un_tebeo_es_solo_una_pista`; en el asistente, `TestCriterio4Eleccion::test_la_sugerencia_de_la_fuente_se_distingue_y_no_esta_elegida` | **PASS**: se atribuye al valor por defecto de la fuente. |
| Origen desconocido | `TestEscenariosCA6DeU15::test_origen_desconocido_no_se_presenta_como_dato_confirmado`; token antiguo en `test_tokens_revision.py` | **PASS**: se dice que no consta de dónde sale. |
| Ausencia de sugerencia | `TestEscenariosCA6DeU15::test_ausencia_de_sugerencia_no_muestra_texto_de_pista`; GCD sin idioma/país en `test_discovery_service.py`; asistente en `TestCriterio3SinPreseleccion::test_sin_sugerencia_no_hay_texto_de_pista_y_el_selector_sigue_vacio` | **PASS**: `None`, no `other`; no hay texto de pista. |
| Elección explícita de la persona | `test_descubrir_dos_pasos_pg.py::TestRevisarNoEscribeNada::test_la_vista_previa_ofrece_crear_con_la_tradicion_elegida_y_no_escribe` y `TestCrear::test_crea_la_serie_con_la_tradicion_elegida_el_identificador_protegido_y_la_procedencia`; Chrome real: `verificacion-navegador-2026-10-21.md` §4.3 | **PASS** (Postgres real; Chrome real anterior a #276) |

## 6. Decisión adoptada (2026-10-21)

1. **Mantener la no preselección** en todos los casos, aunque la fuente sea «fiable»: la evidencia de código y la
   medición real muestran que la sugerencia no mira la obra.
2. **Texto aplicado** en Descubrir y en el asistente de carpetas:
   > «La fuente lo clasifica como **Grapa americana**. Es solo una pista de la fuente, no de la obra: elige tú.»
   No toca lógica de negocio ni esquema.
3. **Medición real ejecutada parcialmente:** GCD y Tebeosfera respondieron; Comic Vine no tiene clave en este
   entorno y AniList devolvió 403. Las dos fuentes que faltan quedan **NOT RUN**, no PASS. No se inventan resultados.
4. **#202 no se cierra con la PR #273.** La verificación de presentación en navegador real ya está ejecutada
   (2026-10-21, `a2721722`, Chrome 154; ver `verificacion-navegador-2026-10-21.md`). #276 (U15b) implementa la
   ausencia y la procedencia, pero la PR está pendiente de revisión y no se ha desplegado. El tablero no marca
   «Hecha» sin el DoD del Sprint 0 y sin aceptación explícita de los NOT RUN de Comic Vine y AniList.
5. **No se toca la Pi.** El despliegue no está autorizado.

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

Verificación en Chrome real (requiere la app arrancada con GCD/Tebeosfera y Chrome del sistema):

```bash
pip install playwright==1.64.0
python docs/design/ui-u15/verificar_navegador.py \
  --base-url http://127.0.0.1:8766 \
  --out /tmp/u15-verificacion \
  --sha "$(git rev-parse HEAD)"
```

## 8. Archivos

- `titulos.json` — 20 fixtures y tradición de referencia.
- `medir_u15.py` — modelo determinista del mapeo actual.
- `buscar_20.py` — 20 búsquedas reales en GCD y Tebeosfera.
- `resultados-reales.json` / `resultados-reales.md` — respuestas, IDs, fecha y sugerencias.
- `verificacion-navegador-2026-10-21.md` / `verificacion-navegador.json` / `capturas/` — verificación en Chrome real.
- `verificar_navegador.py` — script reproducible de la verificación en navegador.
- `u15b-ausencia-procedencia.md` — contrato, copy y pruebas de #276 (ausencia y procedencia).
- `docs/design/auditoria-ui-2026-10-15.md` §M3 y §8 — evidencia original de Mortadelo.
- `tests/test_web_discovery.py` y `tests/test_asistente_carpetas_pg.py` — contrato de no preselección y texto.
