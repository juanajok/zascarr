# Evidencia retirada — OCTA-E2 (2026-11-17)

- **Historia:** [#937](https://github.com/juanajok/zascarr/issues/937), épica OCTA-E
  [#918](https://github.com/juanajok/zascarr/issues/918).
- **Revisión:** 204 imágenes de `docs/` revisadas por muestreo dirigido y por la procedencia
  declarada en sus READMEs: capturas de la Pi, biblioteca real o portadas comerciales frente a
  maquetas/fixtures sintéticos.

## Qué se retira

**45 imágenes** de cinco grupos, todas con contenido que no debe estar en un repo público:

| Grupo | Imágenes | Por qué |
|---|---:|---|
| `docs/design/ui-actual/` | 12 | Biblioteca real del PO: portadas comerciales y títulos. |
| `docs/design/ui-u7/capturas-205-2026-11-14/` | 6 | Biblioteca real con portadas comerciales. |
| `docs/design/ui-u13/` + `capturas-pi-2026-11-14/` | 15 | Rutas, nombres de carpetas, series y recuentos reales. |
| `docs/design/ui-u15/capturas/` | 11 | Resultados con portadas comerciales (Mortadelo, etc.). |
| `docs/design/ui-156/` | 1 | Ruta `/media/WDElements/Tebeos` y recuento real de la biblioteca. |

La lista exacta, con sha256 y decisión por fichero, está en
[`evidencia-retirada-E2-2026-11-17.csv`](evidencia-retirada-E2-2026-11-17.csv). Los originales
están en el **archivo privado del operador**, fuera del repositorio, con un `SHA256SUMS`.

## Qué se conserva y por qué

- **`ui-baseline`, `ui-u11`, `ui-u14`, `ui-u16`, `ui-u17`, `ui-u19`, `ui-u20`, `ui-u21`,
  `ui-v1`–`ui-v4`, `ui-u12`**: maquetas, fixtures o pantallas de configuración sin datos
  personales ni portadas reales.
- **`etiquetas-maqueta.png`**: maqueta estática con portadas sintéticas (letras), aunque use
  títulos de ejemplo.
- **`benchmark-U12-experimento/ok.png`**: imagen de color sin contenido.
- Capturas nuevas: solo con `ui.portada` o material libre/sintético (guía E6).

## Riesgo residual: la historia de Git

`git rm` limpia **HEAD**, no los commits anteriores: los blobs de esas 45 imágenes siguen en el
historial del repo público. Para un borrado completo hace falta una reescritura de historia
(`git filter-repo`/BFG) y un `push --force`, que **no se ha ejecutado**: afecta a todos los clones
y es una operación destructiva que requiere decisión explícita del PO. Mientras tanto, el repo
público no las sirve en la rama actual, pero sí pueden recuperarse del historial.

## Verificación

- `git ls-files docs/design` ya no lista esas rutas.
- El CSV y el archivo privado conservan la trazabilidad y los hashes.
- Las capturas conservadas siguen enlazadas desde sus documentos.
