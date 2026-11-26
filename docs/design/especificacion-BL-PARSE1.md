# Especificación BL-PARSE1 — números que el parser pierde o inventa (F3 + F4)

> **Estado:** **aprobada por el PO el 2026-11-26**, con D1 = convención `E{N}` (propuesta de R4).
> **Hecha:** fusionada en #1309 (`d1062090`) y **aceptada en la Pi el 2026-11-26** (resultado en §8).
> **Tarjeta:** [#1314](https://github.com/juanajok/zascarr/issues/1314) en el Project 1.
> **Origen:** [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md), familias F3 y F4.
> **Código de referencia:** `main` en `4b5f9d7b` (el mismo que corre en la Pi).

## 1. Problema

El embudo sobre los 5.096 archivos de la biblioteca encontró dos familias del parser:

- **F3, número perdido.** En `NN Serie…` el prefijo `NN` es el número de la grapa, pero se descarta
  como orden de lectura. Pasa en dos sitios:
  - la cohorte (`core/cohort.py`) lo quita aunque sea el único número del nombre;
  - `naming._separar_prefijo_numerico` lo da por orden de lectura cuando el único «otro número» es el
    del volumen (`Vol 02`).
- **F4, número inventado.** Tras perder el prefijo, el volumen de la serie se convierte en número
  (`05 Catwoman Vol 02` → #2, en 17 archivos vinculados y 19 sin vincular). Además, un paréntesis
  suelto esconde el número real (`Flash v2 206)` → #2), y un `Especial N` buscaría la grapa normal #N.

Medido con un prototipo en el simulador (cohorte calculada por carpeta, como el importer), frente al
vínculo actual de cada archivo:

| Regla | Archivos con otro número | Coincide con el vínculo | Deja de coincidir | Sin vínculo |
|---|---:|---:|---:|---:|
| R1 + R2 | 93 | **74** | **0** | 19 |
| R3 | 2 | — | 0 | 2 |

Dreadstar (79 archivos) no cambia con ninguna regla: su prefijo convive con otro número, y la
decisión de 2026-09-26 (es orden de lectura) se mantiene.

## 2. Alcance

**Entra:** `core/cohort.py`, `utils/naming.py`, `core/matcher.py` y las llamadas de
`services/importer.py` y `services/library_adopter.py` a la cohorte y al matcher.

**No entra:** créditos y subtítulos dentro de la serie (F5), la carpeta como señal de serie (F2),
datos del catálogo (F1), años de 4 cifras como número (§6) ni crear Issues. Sin migración, sin
campos nuevos en la BD y sin cambiar `issue_number` de ninguna fila existente.

## 3. Definición compartida: «otro número candidato»

Una única función pura en `utils/naming.py` (la cohorte ya importa de ahí `CREDITS_PATTERN`):

```python
def otros_numeros_candidatos(resto: str, carpeta: str | None = None) -> list[str]:
    """Números del resto del nombre que podrían ser el de la grapa (sin el prefijo)."""
```

Toma `resto`, que es el nombre sin el prefijo inicial, y descarta, en este orden:

1. la extensión (`.cbr`, `.cbz`…);
2. el contenido entre corchetes;
3. los créditos (`CREDITS_PATTERN`);
4. los marcadores de volumen: `Vol N`, `Vol. N`, `Volumen N`, `Volume N`, `vN` y `Tomo N`, sin
   distinguir mayúsculas;
5. los años `19xx`/`20xx`;
6. si se da `carpeta`, los números que también aparecen en el nombre de la carpeta, comparados sin
   ceros a la izquierda (`52` en `… The New 52! Vol 04`).

Devuelve las cifras que quedan, en orden. La lista vacía significa que el prefijo es el único número
del nombre.

## 4. Reglas

### R1. La cohorte no quita el único número (F3)

`quitar_prefijo_de_cohorte(nombre, pista, carpeta=None)` gana el parámetro opcional `carpeta`. Si
`otros_numeros_candidatos(resto_sin_prefijo, carpeta)` está vacío, devuelve `nombre` **sin tocar**.
En cualquier otro caso se comporta como hoy.

- `detectar_ordenes_de_lectura` no cambia: la cohorte se sigue calculando igual. Solo cambia su
  aplicación a cada archivo.
- Los llamadores pasan la carpeta padre del archivo: `services/importer._triage_and_match` y
  `services/library_adopter` (`_propuesta_del_cambio`).
- Ejemplos:
  - `01 Catwoman The New 52!.cbr` en la carpeta `2011 - 2014 Catwoman The New 52! Vol 04` → se
    conserva `01`, porque el `52` está en la carpeta.
  - `42 Dreadstar (First Comics) 30 USA.cbr` → se quita `42`, como hoy, porque queda el `30`.

### R2. El volumen no cuenta como «otro número» del prefijo (F3)

En `_separar_prefijo_numerico`, la comprobación «hay otro número en el resto» (`#N` o un número suelto
de 1–3 cifras) se hace sobre el resto **sin marcadores de volumen** (§3, paso 4). Si el resto **tenía**
un marcador de volumen y sin él no queda ningún otro número, el prefijo de 1–2 cifras es el número de la
grapa y el resto es la serie. El marcador es la evidencia: sin él (`12 Monkeys`), el prefijo se queda
como hoy, sin decidir. *(Precisión añadida el 2026-11-26 al implementar; es lo que medía el prototipo.)*

No cambian:
- los prefijos con punto o paréntesis (`13. Nightwing`), que siguen siendo orden de lectura;
- los decimales (`22.1 Catwoman`);
- los prefijos de 3 cifras;
- el caso sin ninguna evidencia (`12 Monkeys`).

Ejemplos, sin carpeta (con la carpeta de la serie ya acierta hoy por `_prefijo_de_issue_con_carpeta`):
- `05 Catwoman Vol 02.cbr` → serie `Catwoman`, número `5`, volumen `2`, `edition_kind = None`.
- `72 Catwoman Vol 02 No Man_s Land.cbr` → número `72`, volumen `2`.

### R3. Un paréntesis suelto no esconde el número (F4)

El patrón genérico de 3–4 cifras de `ISSUE_PATTERNS` descarta un número seguido de `)`, porque lo
toma por un año entre paréntesis. A esas alturas los paréntesis cerrados ya se han quitado, así que
el `)` es huérfano. La regla nueva: el número **solo** se descarta si en el texto hay un `(` sin
cerrar antes de él; si no, se acepta.

Ejemplo: `235.- Flash v2 206) por DrMediaNoche(CRG).cbr` → número `206`, volumen `2`, sin
`edition_kind`.

### R4. Un especial con número no enlaza con la grapa normal (F4)

**Requiere la decisión D1 (§5).** El parser no cambia: `Superman Vol2 Especial 2` sigue dando serie
`Superman`, número `2` e `is_special = True` (prueba existente
`test_anual_y_especial_no_son_la_misma_clasificacion`).

`SeriesMatcher.decide()` gana `especial: bool = False`, que el importer rellena con
`parsed.is_special`, igual que `annual`. Con `especial=True` y número `N`:

- Se busca en la serie el Issue de número `E` + `N` sin ceros a la izquierda (`E2`), con la misma
  regla de formato que hoy (`_seleccionar_issue`).
- Si existe, se enlaza como cualquier otro número.
- **Si no existe, el resultado es `unsorted`** con los candidatos de serie y la nota exacta:
  `parece un especial y la serie «{título}» no tiene el número «E{N}»: no se enlaza a la grapa {N}`.
- **Nunca** se busca ni se enlaza el Issue de número `N`. Es la misma regla que ya tienen los anuales.

Hoy los 8 archivos `Superman Vol2 Especial N` solo se libran del enlace erróneo por el empate de
F1. Esta regla tiene que estar en `main` **antes** de arreglar los datos de F1.

## 5. Decisión del PO

**D1 (decidida el 2026-11-26: se adopta `E{N}` para buscar).** Convención de número de los especiales. Los 8 especiales que asignaste a mano usan `E1…E8`.
La propuesta (R4) adopta `E{N}` para **buscar**, nunca para crear. La alternativa es no buscar nunca:
todo especial con número iría a «Por revisar».
- La propuesta enlaza solos los especiales que ya existan como `E{N}`.
- La alternativa es más simple, pero te pregunta siempre.

En los dos casos el especial deja de enlazarse a la grapa #N.

## 6. Considerado y descartado

- **El volumen que declara la carpeta no se usa como número.** Con R1 + R2 no cambia nada en la
  biblioteca, y rompería una carpeta por tomo (`En un rayo de sol Vol.1/`). Fuera.
- **Un año de 4 cifras no es número si hay otro.** Arregla `Shadow of the Bat _69 The Spirit of 2000`
  (2 archivos), pero rompe `AIDP 09 - 1946` (3 vinculados con número 1946). Fuera; necesita otra
  señal.

## 7. Textos visibles

Solo la nota de R4 (§4), que se guarda en `files.metadata.notes` y se muestra en «Por revisar» como
las demás notas del matcher. No usa términos técnicos (glosario §14: «número», «serie», «especial»).

## 8. Criterios de aceptación y pruebas

Una prueba por criterio, con el nombre del mecanismo. Unitarias sin BD, salvo las marcadas `pg`.

| # | Criterio | Prueba |
|---|---|---|
| C1 | `otros_numeros_candidatos` ignora extensión, corchetes, créditos, volumen, años y números de la carpeta | `tests/test_naming_core.py::test_otros_numeros_ignora_volumen_anio_corchetes_creditos_y_carpeta` |
| C2 | La cohorte conserva el prefijo si es el único número | `tests/test_cohort.py::test_cohorte_no_quita_el_unico_numero_del_nombre` |
| C3 | La cohorte conserva el prefijo si el otro número está en la carpeta | `tests/test_cohort.py::test_cohorte_no_cuenta_numeros_de_la_carpeta` |
| C4 | Dreadstar sigue perdiendo el prefijo (decisión 2026-09-26) | `tests/test_cohort.py::test_cohorte_sigue_quitando_el_prefijo_si_queda_otro_numero` (más las pruebas existentes) |
| C5 | `NN Serie Vol MM` da el número NN y el volumen MM | `tests/test_naming_core.py::test_prefijo_con_volumen_detras_es_el_numero` |
| C6 | No inventa el número desde el volumen tras quitar un prefijo | `tests/test_naming_core.py::test_volumen_no_se_convierte_en_numero_si_habia_prefijo` |
| C7 | Sin cambios en `13. Nightwing`, `22.1 Catwoman`, `12 Monkeys`, `14 JLD #11` y `Nancy in Hell Tomo 1` | `tests/test_naming_core.py::test_prefijos_que_no_cambian_con_bl_parse1` |
| C8 | Un número con `)` huérfano detrás es el número | `tests/test_naming_core.py::test_parentesis_huerfano_no_esconde_el_numero` |
| C9 | `(1987)` y los demás años entre paréntesis siguen sin ser número | pruebas existentes de `test_naming_core.py` |
| C10 | El importer pasa la carpeta a la cohorte | `tests/test_importer_*.py::test_triage_and_match_pasa_la_carpeta_a_la_cohorte` |
| C11 | Un especial enlaza con `E{N}` si existe | `tests/test_matcher_sql_pg.py::test_especial_enlaza_con_su_numero_e` (pg) |
| C12 | Un especial sin `E{N}` va a `unsorted` con la nota exacta, aunque exista la grapa #N | `tests/test_matcher_sql_pg.py::test_especial_no_enlaza_con_la_grapa_del_mismo_numero` (pg) |
| C13 | El importer pasa `especial=parsed.is_special` | `tests/test_importer_*.py::test_triage_and_match_marca_los_especiales` |
| C14 | Regresión con nombres reales de la biblioteca, cada uno con su número esperado | `tests/test_naming_core.py::test_bl_parse1_nombres_reales` (parametrizada: `Catwoman Vol 02`, `The New 52! Vol 04`, `No Man_s Land`, `Flash v2 206)`) |

**Aceptación en datos reales (tras el verde, con tu autorización para la tanda en la Pi):** repetir el
embudo de solo lectura y comprobar:
- el parser coincide con el vínculo en ≥ 74 archivos más que en la foto del 2026-11-26;
- **0** archivos que coincidían dejan de coincidir;
- **0** enlaces nuevos a otra serie o a otro número;
- los 8 `Especial N` no enlazan con la grapa #N.

**Resultado (2026-11-26, código `d1062090` desplegado en la Pi, misma transacción `READ ONLY` con
`ROLLBACK`, 5.096 archivos, 0 errores):**

| Criterio | Medido | |
|---|---|---|
| ≥ 74 coincidencias más | **+74** (3.930 → 4.004 de 4.501 con vínculo; 87,3 % → 89,0 %) | PASS |
| 0 que dejan de coincidir | 0 | PASS |
| 0 enlaces nuevos a otra serie o número | 0 (los 10 enlaces a otro número de la foto previa siguen siendo los mismos 10) | PASS |
| Especiales sin enlace a la grapa #N | 0 de 19 enlazados; uno sale con la nota de §7 | PASS |

Los 8 `Especial N` de la foto previa eran un riesgo **latente** (no estaban enlazados): se habrían
enlazado con la grapa al deshacer los empates de catálogo (F1). R4 cierra esa puerta antes de F1. En
estados del matcher, 59 archivos pasan de `unsorted` a `direct` (1.092 → 1.033).

## 9. Orden de los commits (SDD + TDD)

1. `spec:` este documento y el embudo, aprobados.
2. `test:` C1–C14 en rojo; la PR acredita el rojo de cada una y su motivo.
3. Implementación mínima de R1–R4, hasta el verde de la suite completa (con `--basetemp` en el disco
   raíz, CLAUDE.md §8).
4. `refactor:` si hace falta, con todo en verde.
5. Repetir el embudo en la Pi y anotar el resultado en la PR.
