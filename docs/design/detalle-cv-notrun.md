# Comic Vine en el detalle de edición (#465, PR-3) — NOT RUN

> **Estado:** método implementado y probado con una **fixture manual documentada**, pero la
> respuesta real de `/volume/` y `/issue/` sigue **sin verificar**. No hay `COMICVINE_API_KEY`
> en el repo ni en esta sesión, así que no se ha abierto ninguna respuesta real.

## Qué queda NOT RUN

- Forma real del objeto `publisher` y de `first_issue`/`last_issue` en `/volume/`.
- Valores reales de `start_year`/`count_of_issues` para los casos del corpus.
- Campos reales de `/issue/` (`issue_number`, `cover_date`, `volume`).
- Que el volumen que CV indexa sea la edición española: la evidencia del benchmark dice que
  suele ser la USA (Viz); el detalle sirve de **contraste**, no de resolución.

## Verificación exacta cuando el PO tenga la clave en la Pi

Una petición por endpoint, con la cortesía de 1 s del cliente y **sin volcar la clave**;
el comando usa `ComicVineClient`, que ya pasa por `pedir_con_cortesia` y añade la clave
internamente. No se imprime la clave ni la URL con parámetros.

```bash
docker compose run --rm --no-deps --entrypoint python zascarr - <<'PY'
import asyncio, json
from zascarr.services.comic_vine import ComicVineClient

VOLUME_ID = 31306      # el del fixture manual; sustituir por el que se quiera verificar
ISSUE_ID = 1           # sustituir por un id 4000-... concreto

async def main():
    async with ComicVineClient() as cliente:
        volumen = await cliente.get_volume(VOLUME_ID)
        print("volume:", None if volumen is None else {
            "id": volumen.cv_id, "name": volumen.name,
            "publisher": volumen.publisher, "start_year": volumen.start_year,
            "count_of_issues": volumen.count_of_issues,
            "first_issue": volumen.first_issue, "last_issue": volumen.last_issue,
        })
        issue = await cliente.get_issue(ISSUE_ID)
        print("issue:", None if issue is None else {
            "id": issue.cv_id, "issue_number": issue.issue_number,
            "cover_date": issue.cover_date,
        })

asyncio.run(main())
PY
```

Si no hay clave, `get_volume`/`get_issue` levantan `RuntimeError` **antes** de cualquier
petición; Discovery sigue devolviendo `configuracion_incompleta` sin red.

## Límites

- El fixture `docs/design/fixtures-cobertura/comicvine_volume_31306.json` es manual y está
  marcado como tal; no es una captura.
- Cualquier verificación real debe hacerse en una ejecución autorizada y no se versiona la
  respuesta completa.
