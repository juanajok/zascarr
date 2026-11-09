# Piloto del banco de cobertura española (#135) — informe y veredicto editorial

> **Estado:** ejecutado el 2026-11-06 en la Pi con autorización firmada
> (`piloto-cobertura-2026-11-06`, 12 casos, techo 80 peticiones). **72 peticiones reales**, 0 errores.
> La cobertura editorial se declara aquí por primera vez, tras revisión humana del PO.
> **Base:** `main` al 2026-11-06 (`f4df6a4`). Corpus `sha256:7f1a0f1f…` (12 acreditados / 18 en borrador).

## 1. Qué se ejecutó

| | |
|---|---|
| Casos | 12 (3 por estrato: serie, edición/publicación, número/formato, campo) |
| Celdas planificadas | 288 (caso × fuente × unidad) |
| Celdas con método autorizado | 33 |
| Peticiones reales | **72** (Comic Vine 12, Tebeosfera 20, GCD 20, AniList 20) |
| Parada | `final` (nadie agotó el presupuesto global de 80) |
| Errores | 0 |
| Fuentes encendidas | las cuatro, desde Ajustes (el banco aplica la fila `runtime_settings`) |

## 2. Disponibilidad técnica (¿responde la fuente?)

| Fuente | Peticiones | Respondió con datos | Serie |
|---|---:|---:|---|
| Comic Vine | 12 | **12/12** | |
| Tebeosfera | 20 | 3/4 por unidad | |
| GCD | 20 | 3/7 | |
| AniList | 20 | **1/10** | solo Dragon Ball |

Responder no es acertar: AniList devolvió algo en 1 de 10 búsquedas.

## 3. Veredicto editorial (revisión humana del PO)

Contraste de los candidatos devueltos contra la etiqueta acreditada del corpus.
`✓ serie` = devuelve la obra correcta, no la edición española; `✗` = devuelve otra cosa.

| Caso | Etiqueta acreditada | Comic Vine | GCD | Tebeosfera | AniList | Veredicto |
|---|---|---|---|---|---|---|
| ES-001 Mortadelo | Bruguera, Olé!, 1958 | Colección Olé ✓ serie | Mortadelo y Filemón ✓ serie | Alegres Historietas ✗ | — | **coincide a nivel serie** |
| ES-005 Thorgal | Norma, Pandora, 1990 | Thorgal ✓ serie | Les mondes de Thorgal ✗ (francés) | Thorgal ✓ serie | — | **coincide a nivel serie** |
| ES-007 Dragon Ball | Planeta, Ultimate, 2006 | Dragon Ball ✓ serie | Dragon Ball ✓ serie | BATMAN ✗ | Dragon Ball ✓ serie | **coincide a nivel serie** |
| ES-010 Tintín 1985 | Juventud, 1985 | Tintin ✓ serie | — | — | — | serie sí, **edición no evaluada** |
| ES-014 Blueberry integral | Norma, 2015 | Marshal Blueberry Integral ✗ (spin-off) | — | — | — | **no coincide** |
| ES-016 One Piece | Planeta, 2004 | One Piece ✓ serie | — | — | — | serie sí, edición no evaluada |
| ES-018 Tintín oro negro | Juventud, 1989, nº 15 | otros álbumes ✗ | — | — | — | **no coincide** |
| ES-019 Astérix godos | Salvat, 2011, nº 3 | otros álbumes ✗ | — | — | — | **no coincide** |
| ES-022 Blueberry integral | Norma, 2015 | Marshal Blueberry Integral ✗ | — | — | — | **no coincide** |
| ES-026 Tintín portada | Juventud, 1989 | Tintin ✓ serie | — | — | — | serie sí, edición no evaluada |
| ES-028 Todo Mafalda | Lumen, 2011 | «Lumen» ✗ (editorial); Mafalda ✓ (2.º) | — | — | — | parcial |
| ES-029 Dragon Ball 34 tomos | Planeta, 2007 | Dragon Ball ✓ serie | — | — | — | serie sí, edición no evaluada |

### Resultado

- **A nivel serie:** 8 de 12 casos con coincidencia (ES-001, 005, 007, 010, 016, 026, 029 y parcial 028); 2 fallos claros (ES-018, ES-019) y 2 parciales (ES-014, ES-022).
- **A nivel edición española: 0 de 12 verificadas.** Ninguna fuente devolvió la edición concreta (editorial + año + número) de forma contrastable. Encontrar la serie no acredita la edición: es el criterio 1 de la historia.
- **No es ausencia de cobertura, es limitación del método probado.** El banco solo ejercitó `search_series` (Comic Vine, GCD, AniList) y el buscador de colecciones de Tebeosfera. Resolver una edición exige otro método (detalle de colección/volumen), que no está integrado.

## 4. Hallazgos técnicos del piloto

1. **El banco no leía los interruptores de Ajustes.** Leía el `.env` y las fuentes están en Postgres (`runtime_settings`). Corregido: aplica el override al arrancar. Además, `_configuracion_fuente` buscaba `comic_vine_enabled` cuando el campo es `comicvine_enabled`.
2. **El tope por fuente detenía el banco entero.** Tebeosfera llegando a 20 cortaba las demás fuentes. Corregido: `limite_por_fuente` por fuente; `presupuesto_agotado` solo con el tope global.
3. **AniList publicaba candidatos vacíos.** `AniListResult` usa `title_romaji`/`title_english` y el saneador leía `name`/`title`. Corregido con test.
4. **Tebeosfera devuelve resultados ajenos por su propio ranking.** Diagnóstico con HTML real (una petición, 70 354 bytes, 83 filas, todas dentro del contenedor): buscando «Dragon Ball» el sitio pone BATMAN antes que BOLA DE DRAC. **No es un fallo del parser ni del formulario**; ver `diagnostico-tebeosfera-135-2026-11-06.md`.
5. **GCD no filtra por idioma**: para Thorgal devuelve la edición francesa.

## 5. PASS / FAIL / NOT RUN (primera fase, sin detalle)

> Los resultados con detalle están en §8 y **actualizan** el FAIL de esta sección: hay 1 coincidencia verificada.

- **PASS**: ejecución autorizada (72 peticiones, 0 errores); las cuatro fuentes responden; 8/12 resuelven la serie; el arnés detecta y corrige sus propios fallos; registro e informe saneados (sin URL, sin nombres, sin claves).
- **FAIL**: 0/12 acreditan la edición española; 2 casos no encuentran ni la obra (ES-018, ES-019); GCD devuelve ediciones de otro idioma.
- **NOT RUN**: unidades `edicion`, `formato`, `numero` y `publicacion` en Comic Vine, GCD y AniList (sin método autorizado); búsqueda por edición (método distinto, no integrado); las otras 18 etiquetas del corpus (siguen en borrador); generalización a la población (12 casos elegidos a mano).

## 6. Decisión

1. **No se justifica integrar fuentes para metadatos de edición** con lo medido: el método probado no las resuelve.
2. **La resolución de serie ya la cubre Comic Vine** (12/12); no hay hueco que llenar ahí.
3. **Historias aparte, si el PO quiere**: (a) ranking/filtrado de candidatos de Tebeosfera; (b) método de detalle de edición para Tebeosfera y Comic Vine; (c) filtro de idioma en GCD. Ninguna entra en #135.
4. El banco queda listo para repetir el piloto con otro corpus o más casos; la autorización caduca el 2026-11-13.

## 7. Límites

- 12 casos elegidos a mano: no es una muestra representativa del tebeo español.
- Solo se probaron los métodos de búsqueda por serie y el buscador de Tebeosfera.
- Un único ejecutor y una sola fecha; el comportamiento de las fuentes cambia.
- La revisión es `revision_simple` (sin segundo revisor), declarada de antemano.

## 8. Contraste con detalle (2026-11-07)

Segunda fase: el banco obtiene el **detalle** del primer candidato y lo contrasta con la etiqueta
acreditada. Autorización `piloto-cobertura-detalle-2026-11-07` (150 peticiones, 45 por fuente),
ejecutada **por tandas** (una fuente por pasada) para no chocar con la cortesía.

| Fuente | Casos con contraste | Resultado |
|---|---:|---|
| Comic Vine | 12/12 | **12 `incorrecto`**: su volumen es la edición USA (Viz), no la española |
| Tebeosfera | 4/12 | **1 `coincidencia_verificada`** (ES-014, Blueberry integral de Norma) · 3 `incorrecto` (ES-001, ES-005, ES-007) · `ambiguo` en `publicacion`/`formato` |
| GCD | 0 | **NOT RUN**: 429 a la primera petición (límite de cortesía del servicio) |
| AniList | 0 | sin método de edición (por diseño) |

- **Primera coincidencia editorial verificada del proyecto: ES-014** (Blueberry, edición integral de
  Norma). El camino del detalle de edición funciona.
- **Los `incorrecto` de Tebeosfera no son un fallo del contraste**: el candidato que devuelve su
  buscador no es la edición de la etiqueta (el ranking del sitio sigue siendo el límite conocido).
- **Solo 4 de 12 casos tuvieron candidato de Tebeosfera** en esta pasada; el resto no llegó al
  contraste. Con ellos no se puede decir nada.
- **El detalle de número no se ejercitó**: los casos con número (ES-018, ES-019) no estaban entre los
  cuatro con candidato. Queda **NOT RUN**, no fallido.

Conclusión revisada: **la edición española se puede acreditar** (1 de 1 intento con candidato
correcto), pero el cuello de botella ya no es el detalle: es **que el buscador de Tebeosfera
devuelva el candidato adecuado** y que GCD no nos frene. Ambas cosas son historias de selección y
ritmo, no de contrato.

### 8.1 Pasada final de Tebeosfera (2026-11-08)

Tras corregir la recall de la búsqueda (#497, #500, #502), Tebeosfera se ejecutó sola y con la
unidad `serie` (el detalle sale del mismo candidato en `serie`, `edicion` y `campo`):

| Resultado | Casos |
|---|---|
| `coincidencia_verificada` | **ES-014 y ES-022** (los dos integrales de Blueberry de Norma) |
| `incorrecto` | ES-001, ES-005, ES-007, ES-016, ES-028, ES-029 |
| `ambiguo` | ES-019 (la ficha no da año/país) |
| `sin_resultados` en el detalle | ES-018 |
| sin candidato | ES-010 y ES-026 |

- **2 de 12 verificadas**, y son la **misma edición** (Blueberry integral): el acierto es coherente,
  no un golpe de suerte del buscador.
- Los 5 `incorrecto` de Tebeosfera son candidatos que no son la edición de la etiqueta; el contraste
  hace su trabajo al decirlo.
- **Los dos casos de Tintín sin candidato** (ES-010, ES-026) buscan con tilde («Tintín»). La hipótesis
  abierta es que el buscador distinga acentos; no se ha verificado. Queda como límite conocido, no
  como fallo del banco.
- El **detalle de número no llegó a contrastar**: ES-018 encontró candidato pero su detalle salió
  `sin_resultados`. Sigue NOT RUN en la práctica.

Con esto, el balance del bloque es: **el contrato de detalle funciona (2 verificadas), Comic Vine no
sirve para ediciones españolas (12/12 incorrecto), GCD quedó NOT RUN por 429 y la recall de
Tebeosfera ya solo deja 2 casos fuera.**

### 8.2 Cierre de Tebeosfera (2026-11-08, pasada final)

Con el último escalón (sin tilde), la pasada de `--fuentes tebeosfera --unidades serie` deja
**11 de 12 casos con veredicto o motivo**:

| Resultado | Casos |
|---|---|
| `coincidencia_verificada` | **ES-014 y ES-022** (integrales de Blueberry de Norma) |
| `incorrecto` | ES-001, ES-005, ES-007, ES-010, ES-016, ES-026, ES-028, ES-029 |
| `ambiguo` | ES-019 |
| `sin_resultados` en el detalle | ES-018 |

- **La hipótesis del acento se confirmó**: ES-010 y ES-026 («Tintín…») ya encuentran candidato
  sin tilde. Que el candidato no sea la edición correcta (`incorrecto`) es un resultado, no un fallo.
- **ES-018 sigue sin detalle**: encontró candidato, pero la ficha de número no se localizó
  (`sin_resultados`). El detalle de número queda **NOT RUN** en la práctica.
- Balance del banco: **2 verificadas de 12**, 8 incorrectas y 1 ambigua; ninguna silenciada.

### 8.3 GCD con editorial resuelta (2026-11-08)

Tras resolver el nombre de la editorial (#516), GCD da veredicto en sus 4 casos con candidato:

| Resultado | Casos |
|---|---|
| `coincidencia_verificada` | **ES-022** (integral de Blueberry de Norma) |
| `incorrecto` | ES-001, ES-005, ES-007 |
| sin candidato | los otros 8 (su búsqueda solo mira la primera página) |

**ES-022 queda acreditada por dos fuentes independientes** (Tebeosfera y GCD): es la señal más
fuerte del piloto. Comic Vine sigue sin acreditar ninguna (12/12 `incorrecto`) y AniList no tiene
método de edición.

### 8.4 Balance final del bloque

| Fuente | Con veredicto | Verificadas | Incorrectas | Ambiguas | Sin candidato |
|---|---:|---:|---:|---:|---:|
| Comic Vine | 12/12 | 0 | 12 | 0 | 0 |
| Tebeosfera | 11/12 | 2 | 8 | 1 | 0 (1 sin detalle) |
| GCD | 4/12 | 1 | 3 | 0 | 8 |
| AniList | 0/12 | — | — | — | sin método |

- **2 ediciones acreditadas**: ES-014 y ES-022, los dos integrales de Blueberry de Norma. ES-022,
  además, por dos fuentes.
- **Comic Vine no sirve para la edición española** (12/12 incorrecto): su volumen es la USA.
- **La recall sigue siendo el límite**: GCD solo mira la primera página (8 sin candidato) y Tebeosfera
  deja 1 caso sin detalle de número (ES-018).
- **El contrato de detalle funciona**: distingue acierto, error y ambigüedad sin inventar.

### 8.5 GCD con filtro de año: ES-007 verificada (2026-11-09)

Tras el ranking explicable y el filtro de año (#526), la búsqueda de GCD con `anio=2006` devuelve
**«Dragon Ball. Ultimate Edition»** y el contraste la acredita:

```
ES-007 | contraste=coincidencia_verificada | detalle=ok | peticiones=2
   editorial=Planeta DeAgostini | anio=2006 | candidato=Dragon Ball. Ultimate Edition
```

- **3 ediciones acreditadas** ya en el bloque: ES-007 y ES-022 por GCD, ES-014 y ES-022 por Tebeosfera.
- **ES-022 queda acreditada por dos fuentes** independientes.
- La afirmación de §8.3 («GCD: 8 sin candidato») era cierta **sin filtro de año**; con él, la edición
  correcta aparece. La frase correcta es «no estaba en la primera página ni sin filtro».
- **GCD sigue pendiente de repetir el resto de casos** con el código final (cuota 30/h); los no
  medidos quedan **NOT RUN**, no fallidos.

El cuello de botella original —«las fuentes no tienen la edición española»— era falso: la tienen, y
lo que fallaba era **cómo la buscábamos** (recorte antes del filtro, primera página, sin año,
sin ranking).
