# Benchmark previo — LECUX2 (cierre de lectura)

- **Historia:** [#1069](https://github.com/juanajok/zascarr/issues/1069); épica #1067.
- **Fuente:** `docs/design/benchmark-BL-LEC-mercado-lectores-2026.md` (revisión 2026-11-17).

## Lo observado

| App | Patrón relevante | Decisión |
|---|---|---|
| **CDisplayEx** | La ficha le atribuye «al acabar, seguir con el siguiente álbum»; ya se recoge en LEC3, no en esta historia. | **Descartar** como fuente de cierre automático; se mantiene el «siguiente» de LEC3. |
| **Kavita** | Lector con menú, progreso y controles explícitos; no se verificó que marque «Leído» automáticamente al final. | **No atribuir** auto-cierre; se ofrece acción explícita. |
| **Komga / Panels / Chunky** | Lectores con progreso y controles de lectura; la ficha no mide un comportamiento de «marcar leído al final» reproducible. | **No copiar** un automatismo no verificado. |
| **YACReader** | Atajos y barra explícita; el cierre de estado no forma parte del alcance medido. | **No aplica** directamente. |

## Decisión

Se adopta la **Propuesta A de D-LUX2**: botón explícito **«Marcar como leído»** como acción
principal de la tarjeta de fin, con «Deshacer»; sin cierre automático. La escritura pasa por
`services.lectura.marcar` (la misma verdad que BL-C3), conserva nota/puntuación al deshacer y
no crea una segunda tarjeta: se integra en la tarjeta `#fin` que ya pinta LEC3.

No se atribuye a las apps un comportamiento no comprobado; lo no medido es **NOT RUN**.
