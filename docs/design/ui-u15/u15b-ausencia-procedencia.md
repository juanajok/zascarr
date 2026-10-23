# U15b — Ausencia de sugerencia y procedencia (#276)

> **Estado: fusionado en `bf67699` (PR #281); no desplegado. Verificado en Chrome real el 2026-10-22
> (`verificacion-navegador-2026-10-22.md`). #202 pasa a «Fusionado — pendiente de despliegue» con la firma de la
> decisión de los NOT RUN el 2026-10-22.**
> Fecha de la ficha: 2026-10-21.

## 1. Problema que cierra

Antes de #276, `DiscoveryResult.tradition_guess` era obligatorio y el contrato no tenía procedencia. Una fuente
que no reconocía ninguna tradición (GCD devolvía `other`) no podía decir «no sugiero nada», y la UI presentaba
cualquier valor como si la fuente lo clasificara. #276 separa dos cosas que no son lo mismo:

- **no hay sugerencia** (`None`), y
- **hay sugerencia, pero su origen es explícito, transformado, un valor por defecto o desconocido**.

En ningún caso la sugerencia se convierte en la tradición aplicada: la elige la persona en el selector, que sigue
obligatorio y vacío.

## 2. Contrato

`DiscoveryResult` (`src/zascarr/services/discovery.py`):

```python
tradition_guess: ComicTradition | None = None
tradition_provenance: ProcedenciaTradicion | None = None

@property
def procedencia(self) -> ProcedenciaTradicion | None:
    if self.tradition_guess is None:
        return None
    return self.tradition_provenance or ProcedenciaTradicion.DESCONOCIDA
```

`ProcedenciaTradicion` tiene exactamente estos valores:

| Valor | Significado |
|---|---|
| `explicita` | La fuente declara la tradición. |
| `transformada` | Se deduce de otro dato de la fuente (GCD: idioma/país). |
| `por_defecto` | La fuente no la da; el producto aplica un valor de partida. |
| `desconocida` | Hay sugerencia, pero no consta de dónde sale. |

Mapeo actual de fuentes:

| Fuente | Sugerencia | Procedencia |
|---|---|---|
| Comic Vine | `american` | `por_defecto` |
| AniList | `manga` | `explicita` |
| Tebeosfera | `tebeo` | `por_defecto` |
| GCD con idioma/país reconocido | `british` o el valor del idioma | `transformada` |
| GCD sin idioma/país reconocido | `None` (no `other`) | `None` |

`other` sigue existiendo como valor de `ComicTradition` para datos ya guardados, pero **no se usa para representar
la ausencia de sugerencia**. Si una fuente no sugiere nada, el contrato dice `None`.

## 3. Token firmado y retrocompatibilidad

`CandidataFirmada` (`src/zascarr/services/tokens_revision.py`) admite:

```python
tradicion: str | None
procedencia: str | None = None
```

- Un token nuevo sin sugerencia **omite** `tradicion` y `procedencia`; el verificador devuelve `None` en ambos.
- Un token anterior a #276 (con `tradicion` y sin `procedencia`) sigue siendo válido: se interpreta como
  **origen desconocido**, nunca como dato explícito.
- Si aparece `procedencia`, tiene que ser uno de los cuatro valores y no puede ir sin `tradicion`.
- El token no puede convertir `None` en la cadena «None»: la validación de esquema se mantiene.
- Los máximos de token se recalcularon con la serialización real: `MAX_TOKEN_CANDIDATA` pasa de 20.313 a
  **20.353** caracteres (+40 del campo de procedencia); `MAX_TOKEN_CANDIDATA_SIN_GRUPO` pasa de 12.333 a
  **12.373**. Los tokens de alta no cambian.

La procedencia viaja también en `Candidata` (respuesta de `/api/revision/descubrir` y del asistente) y en
`VistaPreviaAlta.procedencia_sugerida`; es contexto de la sugerencia, no un campo de la serie.

## 4. Presentación

La copy se centraliza en `pista_de_tradicion(etiqueta, procedencia)` (`src/zascarr/web/descubrir_texto.py`) y se
usa en Descubrir y en el asistente de carpetas:

| Caso | Texto |
|---|---|
| `explicita` | «La fuente lo clasifica como **X**. Es solo una pista de la fuente, no de la obra: elige tú.» |
| `transformada` | «La fuente no usa esta tradición: a partir de sus datos se sugiere **X**. Es solo una pista de la fuente, no de la obra: elige tú.» |
| `por_defecto` | «La fuente no indica tradición: se sugiere **X** por defecto. Es solo una pista de la fuente, no de la obra: elige tú.» |
| `desconocida` | «La fuente sugiere **X**, pero no consta de dónde sale. Es solo una pista de la fuente, no de la obra: elige tú.» |
| sin sugerencia | **No se muestra texto de pista.** |

La copy de `explicita` es literalmente la de U15. En el asistente, la pista de la carpeta solo acompaña a una
sugerencia de fuente; sin sugerencia no se muestra ninguna pista. El paso de revisión repite la procedencia como
contexto («Procedencia de la sugerencia: …»), y el selector mantiene
`<option value="" selected disabled>Elige la tradición…</option>` como único `selected`, y la elección de la
persona es la que se aplica al alta.

## 5. Evidencia de los cinco escenarios de CA6

| Escenario | Prueba | Estado |
|---|---|---|
| Dato explícito respaldado | `TestEscenariosCA6DeU15::test_dato_explicito_respaldado_se_presenta_como_pista_y_no_se_preselecciona` | PASS |
| Sugerencia no fiable | `TestEscenariosCA6DeU15::test_sugerencia_no_fiable_de_comic_vine_para_un_tebeo_es_solo_una_pista` y `TestCriterio4Eleccion::test_la_sugerencia_de_la_fuente_se_distingue_y_no_esta_elegida` | PASS; Chrome 2026-10-22: 10 `por_defecto` y 9 `transformada` |
| Origen desconocido | `TestEscenariosCA6DeU15::test_origen_desconocido_no_se_presenta_como_dato_confirmado`; token antiguo en `test_tokens_revision.py` | PASS |
| Ausencia de sugerencia | `TestEscenariosCA6DeU15::test_ausencia_de_sugerencia_no_muestra_texto_de_pista`; GCD sin idioma/país en `test_discovery_service.py`; asistente en `TestCriterio3SinPreseleccion::test_sin_sugerencia_no_hay_texto_de_pista_y_el_selector_sigue_vacio` | PASS; Chrome 2026-10-22: 1 tarjeta GCD sin pista en `Mortadelo` y 7 en `Lucky Luke` |
| Elección explícita de la persona | `test_descubrir_dos_pasos_pg.py::TestRevisarNoEscribeNada::test_la_vista_previa_ofrece_crear_con_la_tradicion_elegida_y_no_escribe` y `TestCrear::test_crea_la_serie_con_la_tradicion_elegida_el_identificador_protegido_y_la_procedencia` | PASS (Postgres real y Chrome 2026-10-22) |

Comandos ejecutados en esta rama (resultado: 5363 tests con Postgres y 3968 no-Postgres):

```bash
PYTHONPATH=src ../zascarr-venv/bin/pytest -q -m 'not integration'
TEST_DATABASE_URL='postgresql://test:test@127.0.0.1:15450/zascarr_test' \
  PYTHONPATH=src ../zascarr-venv/bin/pytest -q \
  tests/test_descubrir_dos_pasos_pg.py tests/test_descubrimiento_grupo_pg.py \
  tests/test_asistente_carpetas_pg.py
```

## 6. Límites y estado de #202

- Esta ficha documenta la implementación, las pruebas locales y la verificación en Chrome real del 2026-10-22;
  #276 está fusionada en `bf67699`, pero **no desplegada**. La Pi no se ha tocado.
- #202 pasa a «Fusionado — pendiente de despliegue» con la firma de
  `decision-u15-not-run-2026-10-22.md` el 2026-10-22. Comic Vine y AniList siguen **NOT RUN**; #276 no convierte
  esos NOT RUN en PASS.
- La prueba de cinco segundos con personas y el lector de pantalla real pertenecen a #208/U21 y siguen **NOT RUN**;
  no se sustituyen por pruebas automáticas.
