# Plan de enriquecimiento por campo (#128, MIT-M6-US02)

> Vista previa, confirmación y resultado de un enriquecimiento **sin** escribir hasta la confirmación.
> No añade fuentes, migraciones, edición masiva ni cambia `locked_fields`/ComicInfo.

## 1. Alcance de esta entrega

Campos de **serie** que gestiona el enricher actual:

| Campo | Etiqueta | Acciones |
|---|---|---|
| `comic_vine_id` / `anilist_id` / `tebeosfera_slug` | Identidad en la fuente | añadir; conservar si ya hay otra identidad (nunca se sustituye) |
| `description` | Sinopsis | añadir, conservar, proponer sustitución, omitir por ausencia, bloqueado |
| `cover_url` | Portada | ídem |
| `total_issues` | Números en total | ídem |

También se incluyen los campos de los **números candidatos** de una serie de Comic Vine: identidad externa,
sinopsis y portada de cada `Issue`. Los **créditos** quedan fuera de esta iteración: crear creadores y
relaciones merece su propio contrato. La ficha no cambia de unidad ni crea series, números, archivos o vínculos.

## 2. Flujo y contrato

1. En la ficha, «Revisar cambios de datos» envía `POST /ui/series/{id}/enriquecimiento/previsualizar`.
2. El servicio busca **una** fuente por tradición (misma regla del enricher), exige que esté encendida y
   construye un **plan por campo**. No escribe ni marca `enrichment_attempted_at`.
3. El plan se firma con HMAC (propósito `enriquecimiento`, contexto `series_id`, TTL 15 min) y viaja en un
   campo oculto. La vista muestra valor actual, propuesta, origen, acción, observación y checkbox.
4. Confirmar envía el **mismo token** y solo las claves seleccionadas a
   `POST /ui/series/{id}/enriquecimiento/aplicar`. El servicio verifica firma, propósito, contexto, caducidad y
   una **huella** de los valores gestionados/protecciones: si algo cambió, rechaza el plan como desactualizado y
   no aplica nada. No vuelve a consultar la fuente.
5. El resultado distingue `aplicado`, `conservado`, `bloqueado`, `omitido` y `no_aplicado` con motivo. Si no se
   selecciona nada, no cambia nada.

## 3. Reglas de seguridad y datos

- Una fuente ausente/desconocida, apagada, serie manual o sin coincidencia se explican y no producen plan.
- Un campo en `locked_fields` se muestra con su propuesta y se marca `bloqueado`; no se aplica aunque el
  formulario lo seleccione.
- Ausencia de propuesta = `omitir_por_ausencia`; nunca borra el valor actual.
- La identidad externa existente no se sustituye por otra: se conserva y se explica.
- El token firmado impide manipular valores/acciones; el contexto y la huella impiden aplicarlo a otra ficha o
  a una ficha cambiada.
- Sin datos sensibles en URL ni logs; el token va en el cuerpo del formulario.

## 4. Verificación

- `tests/test_enriquecimiento_plan.py`: acciones de serie y de número, bloqueo, omisión, aplicación selectiva,
  plan desactualizado, token manipulado, serie manual, falta de coincidencia e identidad no sustituida.
- La vista previa limita los números consultados a 50 y avisa si hay más; los créditos no se incluyen.
- `tests/test_web_enriquecimiento.py`: vista previa, error de fuente, reenvío del token y resultado/fallo.
- `tests/test_web_series.py`: la ficha ofrece revisar sin aplicar.
- **NOT RUN:** consulta real a una fuente externa en navegador, lector de pantalla, móvil físico/zoom y Pi.
  El flujo visual se comprueba con plantillas y pruebas HTTP, no con una fuente real.
