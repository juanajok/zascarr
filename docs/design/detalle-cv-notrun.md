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
el comando usa `verificar_cv_detalle.py` y `ComicVineClient`, que ya pasan por `pedir_con_cortesia`
y añaden la clave internamente (la script la lee de `runtime_settings`). No se imprime la clave ni
la URL con parámetros.

```bash
mkdir -p /tmp/cv-detalle
docker compose run --rm --no-deps --entrypoint python \
  -v "$PWD/scripts/medicion/verificar_cv_detalle.py:/app/scripts/medicion/verificar_cv_detalle.py:ro" \
  -v "$PWD/src/zascarr/services/comic_vine.py:/app/src/zascarr/services/comic_vine.py:ro" \
  -v /tmp/cv-detalle:/verificacion \
  zascarr scripts/medicion/verificar_cv_detalle.py \
    --volume 31306 \
    --sha-ejecutor "$(git rev-parse HEAD)" \
    --salida /verificacion/comicvine_volume_31306_real.json
```

Si no hay clave, `get_volume`/`get_issue` levantan `RuntimeError` **antes** de cualquier
petición; Discovery sigue devolviendo `configuracion_incompleta` sin red.

## Límites

- El fixture `docs/design/fixtures-cobertura/comicvine_volume_31306.json` es manual y está
  marcado como tal; no es una captura.
- Cualquier verificación real debe hacerse en una ejecución autorizada y no se versiona la
  respuesta completa.
