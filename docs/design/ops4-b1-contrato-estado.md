# OPS4 · B1 — Contrato del estado durable de actualización (v2) (#443)

> **Estado:** implementado en la rama `feat/ops4-b1-443` (2026-11-26) y verificado en local; la función sigue **deshabilitada por defecto** (`OPS4_ACTUALIZACION_HABILITADA=false`): este contrato no enciende la UI, no arma el socket y no ejecuta nada. Evidencia: oráculo `ops4-b1-check.py` (contrato, monotonía y reconciliación), 403 pruebas OPS4/instalador, prueba de concurrencia de dos procesos reales sobre el estado y `ruff` limpio. **NOT RUN:** `update.sh`, VM/Pi, y la vista `/estado` (B7).
>
> **Fuera de este incremento:** la llamada a las fases desde `scripts/update.sh` (el CLI ya está listo; queda añadir las invocaciones), la vista `/estado` y su plantilla (es B7) y la reserva atómica del cerrojo de operaciones (es B2).

## 1. Fichero de estado v2

Un objeto JSON UTF-8 de **como máximo 4096 bytes**, canónico (`sort_keys`, sin espacios, `\n` final), con **exactamente** estas 12 claves:

| Clave | Tipo | Regla |
|---|---|---|
| `schema` | entero | siempre `2` |
| `id` | texto | 32 hexadecimales minúsculas |
| `unidad` | texto | siempre `zascarr-actualizar.service` |
| `estado` | texto | `aceptada`, `en_curso`, `hecha`, `fallida` o `incierta` |
| `fase` | texto | `aceptada`, `reservada`, `preparacion`, `copia`, `git`, `build`, `migracion`, `arranque` o `fin` |
| `inicio_epoch` | entero | segundos Unix, `0 <= inicio <= actualizado < 2**63` |
| `actualizado_epoch` | entero | nunca retrocede |
| `head0` | texto o `null` | SHA-1 completo (40 hex) del HEAD antes de actualizar; una vez fijado no cambia |
| `sha_destino` | texto o `null` | SHA-1 completo fijado para el intento; una vez fijado no cambia |
| `sha_actual` | texto o `null` | SHA-1 completo realmente instalado; puede cambiar, nunca volver a `null` |
| `resultado` | texto o `null` | `null` mientras no hay terminal; en terminal, igual a `estado` |
| `codigo` | texto o `null` | `null` mientras no hay terminal; en terminal, `success:exited:0`, `exit-code:exited:75` u `otro` |

Estados terminales: `hecha`, `fallida`, `incierta`. Orden de fases (monótono, nunca retrocede):
`aceptada` < `reservada` < `preparacion` < `copia` < `git` < `build` < `migracion` < `arranque` < `fin`.

Un fichero con claves de más o de menos, tipos cambiados, `schema` distinto de 1 o 2, hash mal formado, época invertida o fase desconocida es **inválido** y se falla cerrado.

## 2. Compatibilidad

El lector estricto del host y el lector de la app **siguen aceptando el esquema 1** (las 5 claves actuales) durante la transición. Al leer un v1, `fase` equivale a `aceptada` y `head0`/`sha_destino`/`sha_actual`/`resultado`/`codigo` valen `null`. Ningún lector debe inventar los campos que faltan en el fichero.

## 3. Escritor del host (`deploy/ops/escritor_estado_actualizar_ops4.py`)

- `FASES`: tupla con las 8 fases en orden.
- `estado_inicial(id_: str, ahora: int) -> dict`: instantánea v2 canónica con `estado="aceptada"`, `fase="aceptada"`, `unidad="zascarr-actualizar.service"`, ambas épocas `ahora`, y `head0`/`sha_destino`/`sha_actual`/`resultado`/`codigo` a `None`. Rechaza (lanza `ValueError`) un `id_` o `ahora` inválidos.
- `escribir_estado(ruta, datos, *, fsync=os.fsync, replace=_reemplazar, propietario=None)`: sin cambios de firma ni de atomicidad. Publica tanto v1 como v2; para v2 aplica las reglas de la tabla. **Adquiere el cerrojo de publicación** (ver §3.1) antes de leer el directorio y lo libera al terminar, también en los caminos de error.
- `validar_estado(datos) -> bool`: acepta un v1 válido o un v2 válido y rechaza cualquier otra cosa (claves, tipos, `unidad`, hashes, épocas, fase, resultado o código). Es el único punto de validación: lo usan `escribir_estado`, `leer_estado_estricto` y `calcular_transicion`.
- `leer_estado_estricto(ruta)`: acepta v1 y v2 con las mismas garantías actuales (sin seguir enlaces, sin abrir FIFO, sin aceptar escritura de grupo u otros, tamaño doble comprobado). Devuelve `OK` y el objeto validado.
- `calcular_transicion(actual, estado, *, ahora, id_=None, inicio_epoch=None, fase=None, head0=_NO_CAMBIA, sha_destino=_NO_CAMBIA, sha_actual=_NO_CAMBIA, codigo=None) -> dict | None`: **núcleo puro** que decide la siguiente instantánea sin tocar disco ni mutar `actual`; devuelve `None` cuando la transición es inválida (reglas de abajo). Es la única fuente de la decisión; `publicar_transicion` solo lee, delega en él y escribe.
- `publicar_transicion(ruta, estado, *, ahora, id_=None, inicio_epoch=None, fase=None, head0=_NO_CAMBIA, sha_destino=_NO_CAMBIA, sha_actual=_NO_CAMBIA, codigo=None, propietario=None, fsync=..., replace=...)`: mantiene el cerrojo de publicación tomado mientras lee, decide y escribe, y delega la publicación en el **publicador interno sin cerrojo** (nunca vuelve a llamar a `escribir_estado`, que lo volvería a tomar y se autobloquearía):
  - Exige estado válido, `ahora` entero, fichero previo válido y mismo `id`/`inicio_epoch` si se pasan; si no, `INVALIDO` sin escribir.
  - Si el previo es terminal, `INVALIDO` sin escribir (nunca se pisa un terminal).
  - No baja `actualizado_epoch`; un `ahora` anterior es `INVALIDO`.
  - La fase nueva no puede ser anterior a la actual (v1 equivale a `aceptada`); un `fase=None` conserva la actual.
  - `head0` y `sha_destino` no se pueden cambiar una vez fijados (un valor distinto es `INVALIDO`); `sha_actual` puede cambiar pero no volver a `None`. Un `_NO_CAMBIA` conserva el valor previo.
  - En terminal exige `fase="fin"`, fija `resultado=estado` y `codigo` (solo `None`, `success:exited:0`, `exit-code:exited:75` u `otro`); en no terminal deja `resultado=None` y `codigo=None`.
  - Publica con la misma atomicidad y monotonía actuales y solo devuelve `OK` si todas las fases durables confirman.

### 3.1 Cerrojo de publicación (B1, obligatorio)

La lectura, la decisión y el reemplazo del estado deben ser **una sola sección crítica** frente a otro escritor del host (auxiliar, finalizador o CLI invocado por `update.sh`). El cerrojo:

- es un `flock` exclusivo sobre el **descriptor del directorio del estado** (el mismo que ya se abre con `O_DIRECTORY|O_NOFOLLOW`), sin ficheros de cerrojo nuevos;
- lo toman **todas** las rutas de publicación: la inicial del auxiliar (a través de `escribir_estado`) y cada transición (a través de `publicar_transicion`);
- se mantiene durante lectura, decisión y `replace`, y se libera en **todas** las salidas (incluidos los rechazos);
- **no se anida**: quien ya lo tiene usa el publicador interno sin cerrojo; `escribir_estado` es solo para llamadores que no lo tienen;
- si no se puede abrir el directorio, no hay dónde publicar (`INVALIDO`); si no se puede tomar el cerrojo, se falla cerrado (`INCIERTO`) y no se escribe;
- no sustituye al cerrojo único de operaciones (es B2) ni coordina entre hosts.

## 4. Cierre de la unidad (`deploy/ops/estado_actualizar_ops4.py`)

`main` conserva su comportamiento y gana un segundo modo, sin shell y con argumentos fijos:

- `--ruta RUTA --resultado hecha|fallida|incierta --intento MARCA [--codigo CÓDIGO]`: exige la marca de la invocación; si falta es argumento inválido y si la marca no es válida no escribe. Publica con el id de la marca, que se compara atómicamente con el estado vigente. El código omitido vale `otro`; `ExecStopPost` pasa el código mapeado de `SERVICE_RESULT`. El modo de fase aún no está ligado a la invocación y no debe conectarse a `update.sh` sin cerrar esa garantía.
- `--ruta RUTA --fase preparacion|copia|git|build|migracion|arranque [--head0 SHA] [--sha-destino SHA] [--sha-actual SHA]`: publica una fase intermedia del mismo intento (estado `en_curso`), conservando `id`/`inicio_epoch` y los hashes ya fijados. Valida que cada SHA sea 40 hex.
- Sigue devolviendo 2 ante argumentos inválidos, 0 si no hay estado válido o ya es terminal, y 1 solo si la escritura durable quedó incierta.
- Orden de claves y códigos cerrados; nunca imprime estado, rutas ni secretos.

## 5. Lector de la app (`src/zascarr/services/estado_actualizacion.py`)

- `leer_estado_actualizacion(path, *, id_esperado, ahora_epoch=None)` conserva su contrato y acepta v1 y v2; un id distinto o un fichero inválido sigue siendo `INCIERTA`.
- `IntentoActualizacion`: `dataclass` congelado con `estado: EstadoActualizacion`, `fase: str`, `inicio_epoch: int`, `actualizado_epoch: int`, `head0: str | None`, `sha_destino: str | None`, `sha_actual: str | None`, `resultado: str | None`, `codigo: str | None`, `sin_noticias: bool`.
- `interpretar_ultimo_intento(datos, *, ahora_epoch) -> IntentoActualizacion | None`: **núcleo puro** que decide sobre un objeto ya leído, sin E/S ni mutarlo; aplica la validación v1/v2, el reloj y la reconciliación. Devuelve `None` si no es un estado válido.
- `leer_ultimo_intento(path, *, ahora_epoch=None) -> IntentoActualizacion | None`: lee el último intento **sin id de petición**. Devuelve `None` si el fichero falta o es inválido (incluido `schema` desconocido, épocas futuras, hash mal formado o claves de más). Si el estado es `aceptada`/`en_curso` y `ahora - actualizado_epoch >= 7200`, devuelve `estado=INCIERTA` y `sin_noticias=True`; nunca lo convierte en `fallida`. Un terminal es terminal aunque sea antiguo.
- Sin cadenas libres, rutas ni errores del sistema en la salida; solo categorías cerradas.

## 6. Verificación

`docs/design/ops4-b1-check.py` es el oráculo determinista del operador: `contrato`, `monotonia` y `reconciliacion`, sobre una imagen Python 3.11 sin red y **sin escrituras** (el contenedor de verificación del pipeline es de raíz y montaje de solo lectura y no tiene tmpfs). Por eso verifica el núcleo puro del contrato —`estado_inicial`, `validar_estado`, `calcular_transicion` e `interpretar_ultimo_intento`—.

La parte con E/S la cubre la suite del proyecto, que se ejecuta en un sistema de ficheros real:

- `tests/test_ops4_escritor_estado.py` añade el contrato v2, la monotonía y una **prueba de concurrencia con dos procesos reales** (`test_publicacion_concurrente_no_pierde_terminal`): uno publica fases y otro el terminal, y el terminal no se pierde.
- `tests/test_ops4_estado_actualizacion.py` cubre el último intento v2, la compatibilidad v1 y el límite de 7200 s.
- `tests/test_ops4_estado_final_unidad.py` ejecuta la cadena real de `ExecStopPost` y comprueba el código cerrado.
- `tests/test_ops4_auxiliar.py` adapta los dobles a la transición cerrada.

Fuera quedan `update.sh` (la llamada a las fases), `/estado` (B7), la VM, la Pi y la revisión de SecOps del SHA final: **NOT RUN** y así se declara.
