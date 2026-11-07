# Comic Vine en el detalle de edición (#465, PR-3) — verificado el 2026-11-07

> **Estado:** la respuesta real de `/volume/` y `/issue/` **ya está verificada** contra la API con la
> clave de Ajustes de la Pi (2 peticiones, cortesía de 1 s). Fixture real:
> [`fixtures-cobertura/comicvine_volume_31306_real.json`](fixtures-cobertura/comicvine_volume_31306_real.json).

## Qué se verificó

Volumen **31306** (`Dragon Ball`) y su primer número:

```
name:             "Dragon Ball"
publisher:        "Viz"          ← cadena, no objeto/URL
start_year:        2003
count_of_issues:   16
first_issue:      {id: 194861, issue_number: "1"}
last_issue:       {id: 294807, issue_number: "16"}
issue 194861:     issue_number "1", cover_date "2003-05-01"
```

- `publisher` llega como **nombre** (`"Viz"`), no como URL: el parser no necesita resolverlo.
- `first_issue`/`last_issue` son objetos con `id` y `issue_number`.
- La forma del `field_list` y el `format=json` son correctos (la respuesta es `results`).

## Qué significa para el corpus

El volumen que Comic Vine indexa para «Dragon Ball» es **la edición USA de Viz (2003, 16 tomos)**,
no la Ultimate de Planeta de 2006 que pide el caso ES-007. Confirma lo que decía el benchmark:

- **Comic Vine sirve como contraste**, no para resolver la edición española.
- `detalle_desde_cv_volumen` devolverá editorial `Viz` y año 2003; frente a la etiqueta acreditada
  (Planeta, 2006) el contraste será **`incorrecto`**, y es el resultado honesto.

## Qué sigue NOT RUN

- Que exista en Comic Vine una edición **española** de cualquiera de los 12 casos (la búsqueda por
  volumen no se ha hecho para todos; el volumen conocido es USA).
- Los demás volúmenes del corpus: solo se verificó el 31306.
- La ficha de número de Tebeosfera (`/numeros/…`), que sigue sin abrirse.

## Cómo repetirlo

Una petición por endpoint, cortesía de 1 s, sin volcar la clave:

```bash
docker compose run --rm --no-deps --entrypoint python \
  -v "$PWD/scripts/medicion/verificar_cv_detalle.py:/app/scripts/medicion/verificar_cv_detalle.py:ro" \
  -v "$PWD/src/zascarr:/app/src/zascarr:ro" \
  -v /tmp/cv-detalle:/verificacion \
  zascarr scripts/medicion/verificar_cv_detalle.py \
    --volume 31306 --salida /verificacion/comicvine_volume_31306_real.json
```

Sin clave en Ajustes sale con código 2 y **cero peticiones**.
