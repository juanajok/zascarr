# U21 — Verificación de la ficha de serie en Chrome real (2026-10-21)

> **Estado: PASS de presentación de la ficha en Chrome real; no es validación con personas.** Se miden **8 palabras
> de entrada**, **48 palabras antes del selector de política** (45 sin el resumen del desplegable; 29 introductorias
> sin datos variables), **0 párrafos en mayúsculas**, **360 px sin desbordamiento**, foco visible y fuentes
> plegadas. Siguen **NOT RUN** la prueba de cinco segundos con personas y un lector de pantalla real. **#208 no se
> cierra; no hay despliegue en la Pi.**

## 1. Entorno

| Dato | Valor |
|---|---|
| Fecha de la captura | 2026-10-21T17:18:11Z |
| Código | `69fb148` (base `f985a86`) |
| Rama | `sprint0/u21-ficha-serie` |
| App | `uvicorn zascarr.main:app`, `127.0.0.1:8767`, `AUTH_MODE=none` |
| `PYTHONPATH` | `/tmp/opencode/zascarr-u21-work/src` (imprescindible: el editable install del venv apunta a otro worktree) |
| Base de datos | PostgreSQL 15.19, `zascarr_verify_u15` en `127.0.0.1:15450`, migrada a `head` |
| Navegador | Chrome real **154.0.8037.92**, headless, Playwright **1.64.0** |
| Python | 3.14.4, Linux |
| Script | `docs/design/ui-u21/medir_ficha.py` |

La app se arrancó desde el árbol de la rama con `PYTHONPATH` explícito. Sin esa variable, el entorno virtual carga
el paquete editable de otro worktree y la evidencia no correspondería a este código. El comando completo está en
§6.

## 2. Fixture

Serie local `Mortadelo y Filemón (fixture U21)`, id `d844ac7b-8200-471d-bac9-ddde0a7701e5`:

- 10 números en total, 3 presentes y 7 ausentes.
- `wishlist_policy = faltantes`; `metadata_source = comic_vine`.
- 3 archivos CBZ vinculados a los números 1–3.
- Sin portada cacheada: la imagen devuelve 404 y se pinta el marcador de portada ausente. No es una regresión de
  U21; el fixture no incluye imagen.

La app y la base son locales y desechables. La medición **no llama a GCD, Tebeosfera, Comic Vine ni AniList** y no
modifica la política ni la base: el script solo abre y cierra el desplegable de fuentes con el teclado.

## 3. Resultados

| Medida | Resultado | Umbral | Estado |
|---|---:|---:|---|
| Frase de entrada (`p.series-intro`) | **8** palabras | ≤ 20 | PASS |
| Antes del selector, con datos variables y resumen visible | **48** palabras | ≤ 50 | PASS |
| Antes del selector, sin el resumen del desplegable | 45 palabras | ≤ 50 | PASS (referencia) |
| Texto introductorio sin datos variables | **29** palabras | ≤ 50 | PASS |
| Total visible de `main` | 190 palabras | — | publicado aparte |
| Párrafos con `text-transform: uppercase` | **0** | 0 | PASS |

La cifra de **48** es la conservadora: incluye título, editorial, recuento, el resumen «Fuentes y atribución»,
la entrada, el rótulo y el subtítulo de la política y el rótulo «Qué buscar». Es la que se compara con el umbral.
Las 29 palabras introductorias excluyen los datos variables de la cabecera, como pide el contrato de #208. El total
de 190 incluye chips y nombres de archivo; se publica para no ocultar el coste de lectura.

**Acción de referencia:** `select#wishlist_policy` (rótulo «Qué buscar»), el control que inicia la tarea de esta
pantalla. El enlace «← Biblioteca» es navegación y el `summary` «Fuentes y atribución» es ayuda; ninguno inicia la
tarea. No hay formulario de metadatos ni botón «Guardar» en la ficha actual.

**Orden:** la sección «Búsqueda automática» aparece antes de «Te faltan» y de «En tu biblioteca». La garantía de
efecto («Al cambiar el selector se guarda al momento…») y la nota de «Números que aún no han salido» están junto al
selector, antes del veredicto y del listado; ya no hay una frase de «Guardar» al final.

**Fuentes:** «Fuentes y atribución» es un `<details>` cerrado por defecto. Al abrirlo con Enter se ve el aviso de
metadatos y el enlace «Aviso legal»; el texto legal no se ha eliminado. El resumen visible cuenta en la medida.

**Teclado:** partiendo del enlace de vuelta, el orden es `summary` «Fuentes y atribución» → `select`
`#wishlist_policy` → `summary` de archivos → «Aviso legal». El selector muestra un anillo de foco `solid` de 3 px;
Enter abre y cierra el desplegable.

**Lector de pantalla (árbol de accesibilidad, no lector real):** el selector expone `combobox "Qué buscar"`, la
opción «Buscar los números que me faltan» como seleccionada y «Números que aún no han salido (deshabilitado)» como
deshabilitada. El desplegable aparece como grupo «Fuentes y atribución». El snapshot completo está en
`aria-ficha-2026-10-21.txt`.

**360 px:** en claro y en oscuro, `scrollWidth = clientWidth = 360`; el selector cabe dentro del viewport y no hay
desbordamiento horizontal. Las capturas de página completa muestran la barra fija en una posición intermedia porque
Playwright compone la página entera; no es un solapamiento en el scroll real.

Capturas:

- `capturas/2026-10-21-ficha-1280-claro.png`
- `capturas/2026-10-21-ficha-1280-oscuro.png`
- `capturas/2026-10-21-ficha-360-claro.png`
- `capturas/2026-10-21-ficha-360-oscuro.png`

Datos completos: `verificacion-ficha-2026-10-21.json`.

## 4. Correspondencia con los criterios de #208

| Criterio | Estado | Evidencia |
|---|---|---|
| CA1. Convención y umbrales en `CLAUDE.md` §6 | PASS (previa) | Regla vigente; no se modifica aquí |
| CA2. Suite con recuento, ruta, estado y fixture | PASS | `TestPresupuestoTextoU21` (6 casos) más los tests existentes de la ficha y avisos legales: 28 + 18 = 46 en verde; el 404 existente cubre el estado de error, no se añadió un fixture vacío específico |
| CA3. Carpetas ≤ 20 / ≤ 50 antes de «Elegir la serie» | PASS (previa, #273) | `docs/design/ui-u21/medicion.md` §3.2 y `tests/test_web_carpetas_pg.py`; no se re-mide aquí |
| CA4. Tarjeta de carpeta con nombre, archivos, sugerencia y estado | PASS (previa, #273) | Igual que CA3; fuera de esta medición |
| CA5. Ficha sin párrafos en mayúsculas y notas junto al control | PASS | 0 párrafos con `text-transform: uppercase`; notas de efecto y futuros junto al selector, una frase cada una |
| CA6. Garantía solo donde hay efecto; avisos legales conservados | PASS | La ficha no mueve ni renombra archivos, así que no repite esa garantía; el aviso de metadatos sigue disponible en el desplegable y el pie legal no cambia |
| CA7. Prueba de cinco segundos de #197 | **NOT RUN** | No se ha hecho con personas; no se declara validación |
| CA8. Teclado, detalles, claro/oscuro y 360 px | PASS | Foco visible, Enter en el desplegable, capturas y medidas de §3 |
| DoD. Navegador real con capturas, entorno y SHA | PASS para presentación | Este documento y el JSON |
| DoD. Lector de pantalla real | **NOT RUN** | Solo árbol de accesibilidad de Chrome; no se sustituye por una prueba con lector |
| DoD. Cinco segundos acreditado o deuda aceptada | **NOT RUN** | Requiere decisión del responsable; bloquea el cierre |
| DoD. Pi / despliegue | **NOT RUN** | No autorizado; no se ha tocado |

**#208 sigue abierto.** Este PASS cubre la presentación de la ficha, no la validación con personas ni el lector de
pantalla real. La PR que añade esta evidencia es «parte de #208» y no la cierra.

## 5. Límites

- No hay prueba de cinco segundos con personas: la de #197 sigue pendiente y no se simula como si fuera real.
- No hay lector de pantalla real (NVDA, Orca u otro). El árbol de accesibilidad de Chrome es una comprobación
  técnica, no una sesión con tecnología de asistencia.
- La ficha se mide con un fixture local; no se ha repetido con una serie real de la biblioteca del responsable.
- No se ha medido Carpetas en navegador en esta pasada; su evidencia sigue siendo la de #273.
- No se compara 146 → 190 con la medición histórica: distinta definición, distintos datos y otro alcance. La cifra
  de 48 antes de la acción es la que se compara con el umbral actual.
- No se ha desplegado en la Pi ni se ha abierto una validación en producción.

## 6. Reproducir

```bash
# Base y app locales; el PYTHONPATH evita cargar el editable install de otro worktree.
PYTHONPATH="$PWD/src" DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:15450/zascarr_verify_u15' \
  SECRET_KEY='u21-verify-secret-0123456789abcdef' AUTH_MODE=none \
  /tmp/opencode/zascarr-venv/bin/uvicorn zascarr.main:app --host 127.0.0.1 --port 8767

# Medición y capturas.
/tmp/opencode/zascarr-venv/bin/python docs/design/ui-u21/medir_ficha.py \
  --base-url http://127.0.0.1:8767 \
  --series-id d844ac7b-8200-471d-bac9-ddde0a7701e5 \
  --out /tmp/opencode/zascarr-u21-ficha \
  --sha 69fb148

# Contrato HTML de la ficha.
PYTHONPATH="$PWD/src" /tmp/opencode/zascarr-venv/bin/python -m pytest \
  tests/test_web_series.py::TestPresupuestoTextoU21 -q
```

El script exige que la serie exista y que el selector `#wishlist_policy` esté presente. Si se cambia el título,
la editorial o el recuento del fixture, cambia la cifra de 48; las 8 de entrada y las 29 introductorias son las
cifras estables del texto.
