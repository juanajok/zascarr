# Asociar la primera fuente de una serie manual (2026-11-23)

## El hueco

El enricher **no toca** `metadata_source='manual'` (es una decisión del coleccionista) y
`AsociarFuente`/`AsociacionDeFuente` exigían una identidad previa: no había camino de usuario
para dar a una serie manual su **primera** fuente. Se resolvía con escrituras directas y el
recolector después, que no es un camino de producto.

## Lo implementado

- **`comparar(..., permitir_sin_identidad=True)`**: la propuesta se ofrece también para una
  serie sin identidad; `Comparacion.primera_fuente` lo indica y la UI permite buscar.
- **`AsociacionDeFuente.confirmar`**: si la serie no tenía ninguna identidad y el token firmado
  es válido, fija además `metadata_source` a la fuente confirmada. El resto del camino
  (unicidad, `metadata.asociaciones`, `vinculacion_operaciones`, huella A/B) es el mismo.
  La serie deja de ser «manual» solo por esta acción explícita.
- **`B9`** sigue midiendo lo que importa: tras confirmar hay que recolectar la ficha
  (`entity_source_records`); sin registro actual el id no se puede afirmar.
- **Puntuación** (`services/asociacion_automatica.py`): título normalizado (acentos,
  artículos, «Vol.», Integral/Omnibus/Tomo), número de números como **subconjunto**, editorial
  por **contención**, año ±1 y nombres de archivo cuando falta el año. Umbral 0,85 para
  aplicar; 0,70–0,85 para revisar. Cada candidata lleva su `puntuacion` y `motivos`.

## Lo que queda

- El botón de la ficha ya permite el alta, pero el **recolector de la ficha** tras confirmar
  se lanza aparte (CCM). El siguiente paso natural es que la confirmación dispare la
  recolección y devuelva la evidencia en el mismo flujo.
- El camino automático en lote (las 206) puede usar `puntuar` para proponer, pero **no**
  aplica solo: exige confirmación.
