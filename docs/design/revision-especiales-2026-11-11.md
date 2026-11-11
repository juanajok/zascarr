# Revisión de especiales sin número (2026-11-11)

## Datos en producción

| Serie | Archivo | Issue | Formato |
|---|---|---|---|
| `Criminal` | Bad Weekend | NULL | `graphic_novel` |
| `Lobo` | Año 1 | NULL | `graphic_novel` |
| `Lazarus: X+66` | X+66 | NULL | `trade_paperback` |
| `Catwoman Annual` | 22.1 Catwoman… | #2 | `single_issue` |

Los cuatro conservan su ruta original; no hubo movimientos.

## Comprobaciones

- **Huecos**: `numero_de_grapa(None, formato)` devuelve `None`; los
  especiales no cuentan como grapa poseída ni como hueco.
- **Ficha del número**: ya distingue «Número» + título y «Sin número».
- **Ficha de serie**: la sección «Archivos por número» pintaba
  `#(sin número)` y no mostraba el título del especial.
- **Datos**: cuatro filas correctas, sin Issues duplicados.

## Corrección

- `NumeroConArchivos` incorpora `titulo`.
- `archivos_por_numero` selecciona `Issue.title`.
- La ficha de serie pinta **«Sin número · Bad Weekend»** en vez de
  `#(sin número)`.
- Test de regresión en `tests/test_web_ficha_447.py`.

## Estado

- Rama `fix/series-especiales-ui`; sin deploy todavía.
- Verificados 61 tests de ficha, desvinculación y colección mezclada.
- La Pi mantiene los datos y el código desplegado antes de esta corrección.
