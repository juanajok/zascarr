# Fixtures de RAR (#418, BL-PORT3)

Tres RAR mínimos para las pruebas con `unar` real (`tests/test_lector_rar_real.py`). **Se crean a mano**
con el `rar` oficial (no es software libre y no se puede generar desde el repositorio); el PO los acepta
antes de fusionar. Imágenes **sintéticas**: nada de la biblioteca real.

| Fichero | Formato | Contenido (por este orden) |
|---|---|---|
| `minimo_rar4.cbr` | RAR 4 | `01.jpg` (JPEG 8×8 **rojo**), `02.jpg` (8×8 azul) |
| `minimo_rar5.cbr` | RAR 5 | `01.jpg` (8×8 **rojo**), `02.jpg` (8×8 azul) |
| `solido_rar5.cbr` | RAR 5 sólido | `01.jpg` (8×8 **rojo**), `02.jpg` (azul), `03.jpg` (verde) |

Cada uno < 5 KB. Las pruebas esperan que `01.jpg` sea rojo (R > 150, G y B < 100 en el centro).

## Cómo se crean

```bash
python3 - <<'PY'
from PIL import Image
for nombre, color in (("01", (220, 20, 20)), ("02", (20, 20, 220)), ("03", (20, 200, 20))):
    Image.new("RGB", (8, 8), color).save(f"{nombre}.jpg", quality=95)
PY
rar a -ma4 -m3      minimo_rar4.cbr 01.jpg 02.jpg
rar a -ma5 -m3      minimo_rar5.cbr 01.jpg 02.jpg
rar a -ma5 -m3 -s   solido_rar5.cbr 01.jpg 02.jpg 03.jpg
sha256sum *.cbr     # anotar abajo
```

## Huellas (a rellenar al crearlos)

| Fichero | SHA-256 |
|---|---|
| `minimo_rar4.cbr` | _pendiente_ |
| `minimo_rar5.cbr` | _pendiente_ |
| `solido_rar5.cbr` | _pendiente_ |

## Lo que NO hay (NOT RUN real)

RAR cifrado y multivolumen: crearlos exige una muestra que no se puede fabricar aquí; solo se prueban con
el `lsar`/`unar` falso de `tests/_rar_falso.py`.
