# Ficha — Lote de operación: desinstalador, avisos (E4) y normalización de nombres

Tercer y último lote de la batida de deuda técnica. Los dos anteriores fueron
integridad del hash (`benchmark-integridad-hash-dedupe.md`) y seguridad de
auth/Origen/Host (`benchmark-seguridad-auth-origen-host.md`). Esta ficha recoge
los hallazgos de operación que quedaron sin empezar. **Ficha primero, sin
código**, como en los lotes anteriores.

Orden por gravedad:

1. **`uninstall.sh` puede decir «borrado» sin haber borrado** (el más grave: un
   desinstalador que miente sobre datos que siguen en disco).
2. **Aviso de importación (E4)**: destino sin validar, tipos desconocidos que
   caen en «generic» en silencio, sin botón de prueba, fallo sin causa en el log
   y nombres de fichero en el cuerpo (delator en un tema público de ntfy).
3. **Dos normalizadores de nombres en la misma función (M2)**, que divergen.

---

## 1. `uninstall.sh` — el más grave

### Comportamiento actual (verificado)

- `scripts/uninstall.sh:90-101` (`resolver_var_ruta`) lee el valor del `.env` con
  `grep -m1 "^VAR=" | cut -d= -f2-`: **no quita las comillas envolventes**.
- Con `ZASCARR_DATA_DIR="/var/lib/zascarr"` el valor leído es
  `"/var/lib/zascarr"` (con comillas). `resolver_ruta` (líneas 116-122) usa
  `readlink -f`, que no resuelve esa cadena, y se queda tal cual.
- La comprobación de restos (líneas 240-256) busca
  `"/var/lib/zascarr"/postgres`, que no existe → `RESTOS` vacío →
  **`success "Datos de la app borrados"` sin que se haya borrado nada**.
- Reproducido en local (sin Docker): valor leído `["/var/lib/zascarr"]`,
  resuelto `["/var/lib/zascarr"]`, restos `NO`.

Y no es un caso exótico: **`docker compose config` interpreta el `.env` de
verdad**. Verificado en local con las cuatro formas a la vez — comillas
(`A="/ruta/a"`), comentario en línea (`B=/ruta/b # nota`), `export D=/ruta/d` y
final CRLF (`E=/ruta/e\r\n`) — y las cinco salen resueltas como `/ruta/…`, sin
comillas, sin comentario, sin `export` y sin `\r`. O sea, el `.env` funciona para
la app y engaña al desinstalador. `bootstrap.sh` escribe sin comillas
(`set_env_var`), así que el caso llega por **edición manual** — el mismo
escenario que motivó A4, y coherente con M7 (valores con espacios y `&`, que
invitan a entrecomillar).

### Segundo problema: lógica propia más débil que la compartida

`uninstall.sh` reimplementa lo que `_rutas.sh` ya hace mejor:

| | `uninstall.sh` | `_rutas.sh` |
|---|---|---|
| Resolver ruta | `readlink -f` (116-122) | `realpath -m` + detección de **symlink roto** componente a componente + comprobación de fichero/carpeta (33-106) |
| Solapamiento | prefijo de texto (`se_solapan`, 139-146) | misma ruta, **mismo `(st_dev, st_ino)`** (bind mounts) y anidamiento por componentes (`motivo_solapamiento`, 111-145) |

Consecuencia: un `ZASCARR_DATA_DIR` que llega a la biblioteca **por bind mount**
(mismo inodo, texto distinto) hoy no se detecta en el desinstalador. `_rutas.sh`
ya lo cubre (y es lo que usa `bootstrap.sh`).

### Tercero: la imagen de Postgres, hardcodeada

`scripts/uninstall.sh:230` purga con `docker run … postgres:15-alpine`, mientras
`docker-compose.yml:22` declara `image: postgres:15-alpine`. Hoy coinciden, pero
un salto de versión en el compose dejaría al desinstalador purgando con una
imagen distinta (o inexistente en caché).

### Más casos que las comillas (ampliación de la revisión)

Las comillas no son el único desajuste: `docker compose` también

- quita un **comentario en línea** de un valor sin comillas
  (`ZASCARR_DATA_DIR=/var/lib/x # datos` → `/var/lib/x`),
- acepta `export VAR=…`,
- y con finales de línea **CRLF** deja un `\r` al final del valor.

Cada uno reproduciría el mismo «borrado» en vacío.

### Resultado deseado

1. **Las rutas resueltas salen de `docker compose config`**, que es exactamente
   lo que ve la app. Es la fuente autoritativa y cubre de golpe las comillas,
   `export`, el comentario en línea y el CRLF — sin reimplementar el parser de
   Compose. El lector propio queda como **reserva** para cuando
   `docker compose config` no pueda responder (un `.env` a medias, Docker
   caído), y entonces interpreta al menos esos cuatro casos, **con una prueba por
   cada uno**:
   - comillas simples o dobles envolventes: `VAR="/ruta"` → `/ruta`;
   - comentario en línea sin comillas: `VAR=/ruta # nota` → `/ruta`;
   - `export VAR=…` → `VAR`;
   - finales CRLF: quitar el `\r` final.
2. **Red de seguridad independiente del lector:** si la ruta resuelta **no
   existe como directorio**, `--purge` se **niega** y explica por qué (hoy sigue
   adelante y «borra» en vacío). Cubre cualquier desajuste de interpretación que
   no se haya previsto.
3. **Reutilizar `_rutas.sh`** (`resolver_ruta`, `motivo_solapamiento`) en vez de
   las versiones locales; y `comprobar_requisitos` de `_comun.sh`.
4. Distinguir tres estados al purgar: «no había nada» / «se borró» / «no se pudo
   borrar (quedan restos)». Nunca «borrado» sin comprobarlo.
5. Leer la imagen de Postgres del propio `docker-compose.yml`.

### Cómo se prueban (método fijado)

`uninstall.sh` no tiene hoy ninguna prueba; el fallo de las comillas solo está
reproducido en aislamiento (el `grep|cut` + `readlink -f` + la comprobación de
restos), no contra el script. Se estrena con el patrón que ya fija
`tests/test_diagnostico_red.py` para scripts que hablan con Docker: **dobles de
`docker` en el `PATH`** y un **árbol sintético** (`ZASCARR_ROOT` y
`ZASCARR_DATA_DIR` en un directorio temporal). El script se ejecuta de verdad,
pero **nunca ve el Docker real ni las rutas reales**: no hay `docker compose
down` de verdad ni ningún `rm` sobre algo que importe.

### Implementado (2026-09-30)

- **Las rutas salen de `docker compose config --environment`** (lo que ve la app)
  y del **lector propio** solo como reserva, con las cuatro formas. La red de
  seguridad **distingue el origen**: si lo resolvió Compose y la carpeta no
  existe, es «no había nada que purgar» y la desinstalación **sigue** (el `.env`
  incluido) — si no, cualquier ejecución sobre una instalación ya a medias
  quedaría a medias para siempre. Si lo resolvió el lector de reserva, se niega.
- **Fuera de `--purge` un fallo de resolución solo avisa y sigue**: parar los
  contenedores no necesita la ruta resuelta, y el script se documenta como
  tolerante. El `die` queda para `--purge`.
- **El `#` solo es comentario si va precedido de espacio** (como en Compose):
  `/media/Comics#1` no se trunca a `/media/Comics`.
- **La imagen de purga sale de `docker compose config --images`**, no del texto
  del YAML: así se resuelve aunque esté entrecomillada o venga de `${VAR}`.

---

## 2. Aviso de importación (E4)

### Comportamiento actual (verificado)

- `services/notifier.py:36-43` (`_configurado`): solo comprueba que la URL no
  esté vacía. **No valida esquema ni destino.** Un `file:///…`, un `ftp://` o una
  URL sin host llegan hasta `httpx` y fallan (o hacen algo inesperado) sin
  explicación.
- `config.py:188`: `webhook_type: str = Field(default="generic")` — un `str`
  libre con los valores buenos en un comentario. `notifier.py:83-84` manda
  **cualquier valor desconocido al `else` (generic) en silencio**: un typo
  (`ntfyy`) envía un JSON que el receptor no entiende y no avisa de nada.
- No hay **botón de prueba**: Comic Vine, Prowlarr, Transmission y aMule tienen
  `/ui/ajustes/probar/*`; el webhook no.
- `notifier.py:56-58`: el fallo se registra como `notifier.send_failed` **sin la
  causa** — ni el código HTTP ni la clase de excepción. Con «mejor esfuerzo» (no
  se reintenta), el log es lo único que queda, y no dice qué pasó.
- `notifier.py:27-34`: el cuerpo lista **los nombres de fichero** (hasta 20). En
  un tema **público** de ntfy.sh, cualquiera que lo conozca los lee: revela qué
  tebeos se está descargando alguien. (El enlace a la documentación de ntfy lo
  aportó la revisión.)

### Nota de amenaza (para no exagerar)

Quien configura el webhook es **el propio operador autenticado**, no un
atacante, así que esto **no es un SSRF**: el operador ya puede llegar a esas
direcciones. Lo que se busca es **fallar claro y pronto** ante un error de
tecleo, y no filtrar datos a un tercero.

### Resultado deseado

1. Validar en Ajustes: esquema `http`/`https` y host presente; mensaje en
   español si no.
2. Aceptar **solo tipos conocidos** (`generic|gotify|ntfy|telegram`); un valor
   raro se rechaza al guardar, no se convierte en generic en silencio.
3. Botón **«Enviar aviso de prueba»** (`/ui/ajustes/probar/avisos`) que use el
   mismo `Notifier` y muestre el resultado, como las otras integraciones.
4. Registrar la **causa** del fallo: código HTTP si lo hubo, o la clase de
   excepción; **nunca** la URL ni el token.
5. Opción **«enviar solo el recuento»** (sin nombres de fichero) para temas
   públicos.
6. **(Opcional)** Persistir el **último resultado de envío** (cuándo y cómo fue:
   ok, o la causa del fallo) y mostrarlo en `/estado`, junto a los demás
   semáforos. Hoy «mejor esfuerzo» deja solo una línea de log que nadie mira; es
   pequeño y encaja con el botón de prueba. `/estado` ya es una página de
   semáforos que sondea `/api/health`, así que el dato tendría que salir por
   ahí.

---

## 3. Normalizador duplicado (M2)

### Comportamiento actual (verificado)

`services/orchestrator.py:524-535` (`_candidato_es_del_numero`, el filtro de D8)
usa **los dos** normalizadores en la misma función:

```python
norm_cand  = normalize_series_name(parsed.series or "")
norm_serie = normalize_series_name(titulo_serie or "")
if norm_serie and norm_cand == norm_serie:
    return True
return normalize_title(parsed.series or "") in (alias_serie or set())
```

Y divergen de verdad:

| Entrada | `normalize_title` (`core/matcher.py:79-99`) | `normalize_series_name` (`utils/naming.py:451-456`) |
|---|---|---|
| `Nausicaä` | `nausicaa` (NFKD) | `nausicaä` (no quita acentos) |
| `Sandman, The` | `sandman` (artículo pospuesto) | `sandman the` (no lo quita) |
| `Die Fantastischen Vier` | `fantastischen vier` (`die` en `_ARTICLE_WORDS`) | `die fantastischen vier` (su lista no tiene `die/der/das/il/lo`) |
| `X-Men` | `x men` (puntuación → espacio) | `xmen` (puntuación borrada) |

Además, los alias se guardan con `normalize_title`
(`models/__init__.py:539`, `LocalAlias.pattern_norm`).

**Corrección de la revisión (dirección del problema).** No son «espacios
distintos» en sentido estricto: cada mitad aplica **su** función a **los dos**
extremos, así que cada comparación es coherente consigo misma. El defecto real
es que la comparación **directa es más estricta** que la de alias y produce
**falsos negativos**: un release sin tildes se descarta aunque el catálogo las
tenga. Medido:

| Par | `normalize_series_name` (directa) | `normalize_title` (alias) |
|---|---|---|
| `Astérix` / `Asterix` | **distintas** | iguales |
| `Filemón` / `Filemon` | **distintas** | iguales |
| `X-Men` / `X Men` | **distintas** | iguales |
| `Batman` / `The Batman` | iguales | iguales |

Es decir: un tebeo español con tilde en el catálogo («Astérix», «Filemón») y un
release sin ella («Asterix», «Filemon») **no coincide hoy** por la vía directa.
Solo entra si hay un alias local, o sea después de que el coleccionista lo haya
corregido a mano una vez.

**La dirección del fallo es la segura**: el coste de un falso negativo es que el
item se queda en Pendientes (se revisa a mano), mientras que un falso positivo
importaría algo que no es. Se dice explícitamente para no «arreglarlo» en la
dirección contraria.

### Resultado deseado

- **Plegado de acentos simétrico**: la comparación directa debe aplicar el mismo
  plegado (NFKD sin diacríticos) a los dos extremos, que es lo que arregla el
  falso negativo hispano. **No** se adopta `normalize_title` en bloque: además
  de los acentos quita **artículos**, y eso sí puede fundir títulos distintos.
- **El artículo se decide de forma explícita**, no como efecto colateral:
  - **Artículo inicial** (`The Batman` / `Batman`): **ya se funde hoy con los
    dos** normalizadores (medido arriba), así que la decisión es **mantenerlo**
    y dejarlo escrito; no es un cambio de comportamiento.
  - **Artículo pospuesto** (`Sandman, The`) y la lista ampliada
    (`die/der/das/il/lo`), que solo quita `normalize_title`: **decisión
    explícita**. La propuesta es **no** añadirlos en este cambio — el objetivo es
    el plegado de acentos, y meter el artículo pospuesto amplía el alcance sin
    una necesidad medida.
- `normalize_series_name` sigue teniendo sentido donde la comparación es *fuzzy*
  contra títulos de release (`orchestrator.py:542,560`), que es un problema
  distinto; si se queda, que sea **a propósito y documentado**.
- **La regresión contra el banco real tiene que pasar antes y después**:
  `TestMedicionD8ContraElBancoReal` (`tests/test_orchestrator.py:875`, sobre
  `scripts/medicion/muestra81_etiquetada.csv`) exige que el filtro siga
  rechazando la sobre-captura del parser y que la igualdad siga siendo la
  mayoría del banco (≥80 %). Si el plegado de acentos mueve esos números, se
  revisa con datos, no se ajusta la prueba.
- **Dos casos nuevos, obligatorios**: «Astérix»/«Asterix» **debe coincidir**, y
  «Batman»/«The Batman» **debe quedar documentado** (hoy coinciden con los dos
  normalizadores; la prueba lo fija para que no cambie por accidente).

---

## Referencias consultadas

- **Internas (son la referencia principal aquí):** `_rutas.sh` (A9) y
  `_comun.sh`; `bootstrap.sh` (A1/A3/M7); `docker-compose.yml`;
  `docs/design/benchmark-E4-avisos.md`; `tests/test_diagnostico_red.py` (el
  patrón de pruebas con dobles de `docker` que se quiere imitar);
  `TestMedicionD8ContraElBancoReal` y el banco
  `scripts/medicion/muestra81_etiquetada.csv` (la regresión que debe seguir
  verde); `test_title_norm.py` (paridad Python/SQL de `normalize_title`).
- **Docker Compose**: semántica de `.env` (comillas, comentario en línea,
  `export`, CRLF) — **verificado en local** con `docker compose config`, no
  citado de memoria.
- **ntfy** (`docs.ntfy.sh/publish`): los temas públicos son legibles por
  cualquiera — es lo que convierte «nombres de fichero en el cuerpo» en fuga.
- **No se han consultado Sonarr/Radarr/Kapowarr/Mylar3 para este lote.** No
  publican un desinstalador equivalente cuyo comportamiento copiar, y cada uno
  lleva su propia normalización de nombres. Se declara explícitamente en vez de
  inventar una cita.

## Supuestos que NO valen en ZascArr

- «El `.env` solo lo escribe `bootstrap.sh`»: falso, el operador lo edita a mano
  (A4 nació de eso).
- «Un desinstalador que no borra es inofensivo»: falso, deja al operador
  creyendo que sus datos de app desaparecieron.
- «El webhook lo configura un atacante»: falso, lo configura el operador; la
  validación es contra errores de tecleo y fugas a terceros, no SSRF.
- «Los dos normalizadores hacen lo mismo»: falso, y ahí está el fallo.

## Invariantes

- El desinstalador **nunca** toca la biblioteca ni las descargas, con o sin
  `--purge`.
- **Nunca** dice «borrado» sin comprobarlo (ya es un invariante del script; se
  extiende al caso de las comillas).
- Sin dependencias nuevas (CLAUDE.md §2).
- Todo mensaje de usuario, en español llano; el «exit code» no se enseña.

## Casos de prueba (deben fallar contra `main`)

1. `.env` con `ZASCARR_DATA_DIR="/var/lib/zascarr"` y `covers/` presente →
   `--purge` lo borra de verdad (o dice que no pudo); **nunca** «borrado» en vacío.
2. Un caso por cada forma del `.env` que hoy se interpreta mal: comillas
   (`"/ruta"`), comentario en línea (`/ruta # nota`), `export VAR=…` y finales
   CRLF. Los cuatro deben resolver a la MISMA ruta que resuelve
   `docker compose config`.
3. `.env` entrecomillado y el directorio **ausente** → se **niega** a purgar y
   explica por qué (red de seguridad), no «borrado».
4. `ZASCARR_DATA_DIR` que es un **symlink roto** → se detecta y se aborta
   (hoy `readlink -f` no lo ve).
5. `ZASCARR_DATA_DIR` y biblioteca con el **mismo inodo** por bind mount →
   se aborta el `--purge` (hoy `se_solapan` no lo ve).
6. `webhook_url` con esquema no `http(s)` o sin host → rechazado en Ajustes con
   mensaje.
7. `webhook_type` desconocido → rechazado al guardar (hoy cae en `generic`).
8. «Enviar aviso de prueba» → manda un mensaje de prueba y muestra éxito o la
   causa del fallo.
9. Un fallo de envío registra la causa (código HTTP o clase de excepción) y
   **no** la URL ni el token.
10. Modo «solo recuento» → el cuerpo no lleva ningún nombre de fichero.
11. **(Opcional)** El último resultado de envío aparece en `/estado`.
12. **«Astérix»/«Asterix» debe coincidir** en el filtro de D8 (hoy no).
13. **«Batman»/«The Batman» documentado**: hoy coinciden con los dos
    normalizadores; la prueba lo fija explícitamente.
14. `TestMedicionD8ContraElBancoReal` **pasa antes y después** del cambio de
    normalización (no se toca la prueba para que pase).

## Orden de commits sugerido

1. `uninstall.sh`: `docker compose config` como fuente de rutas (lector propio
   como reserva, con un caso por forma) + red de seguridad si el directorio no
   existe + reutilizar `_rutas.sh` + los tres estados + imagen del compose; con
   las pruebas siguiendo el patrón de `test_diagnostico_red.py`.
2. E4: validación de tipo/URL + botón de prueba + causa en el log + modo
   recuento (+ el último resultado en `/estado`, si entra).
3. M2: plegado de acentos simétrico en el filtro D8 (artículo decidido y
   escrito) + los dos casos nuevos + la regresión del banco real en verde.

Cada uno es un cambio de dominio distinto: pueden ser commits (o PR) separados.

## Lo que no está verificado

- No se ha ejecutado `uninstall.sh` de verdad (borra contenedores e imágenes);
  el fallo de las comillas está **reproducido en aislamiento** (el `grep|cut` +
  `readlink -f` + comprobación de restos), no con `docker`. Las cuatro formas del
  `.env` sí están verificadas contra `docker compose config`, pero **no** que el
  lector de reserva las interprete igual: eso lo fija la implementación, con una
  prueba por forma.
- **Que Compose resuelva las cuatro formas está verificado a mano** con
  `docker compose config --environment`; las pruebas del script usan un **doble**
  que devuelve el valor ya resuelto, así que prueban el script, no a Compose. La
  afirmación sobre Compose descansa en esa comprobación manual (y en que
  `config --environment` es, por definición, lo que ve la app).
- **`config --environment` requiere una versión reciente de Compose.** Si el flag
  no existe en la instalación, el fallo se traga (`|| true`) y entra el lector de
  reserva: es el comportamiento correcto, pero conviene saberlo. Las pruebas
  cubren ese camino (`STUB_CONFIG_FALLA`).
- No se ha probado el comportamiento de `docker compose config` con un `.env` a
  medias (que es justo el caso en que entra el lector de reserva).
- No se ha probado ningún webhook real (ni ntfy ni Gotify) desde este entorno.
- No se ha medido cuántas series reales cambiarían de resultado con el plegado de
  acentos en el filtro D8. Antes de tocar el filtro conviene contarlo contra el
  banco de `scripts/medicion/` (que es lo que hace la regresión existente).
- La decisión sobre el artículo pospuesto (`Sandman, The`) y la lista ampliada
  (`die/der/das/il/lo`) queda **propuesta**, no medida: no hay datos de cuántos
  títulos reales cambiarían de resultado por ella.

## Decisión

**Adoptar** los tres arreglos, en ese orden, cada uno con sus pruebas primero.
**Descartar** seguir con `readlink -f`/`se_solapan` locales, el `else` silencioso
de tipos de webhook y el plegado de acentos hecho a mano sin regresión contra el
banco real. **Descartar también** adoptar `normalize_title` en bloque para la
comparación directa: el arreglo es el plegado de acentos simétrico, con el
artículo decidido explícitamente.
