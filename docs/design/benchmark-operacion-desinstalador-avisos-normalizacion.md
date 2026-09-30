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

Y no es un caso exótico: **`docker compose` sí quita las comillas** (verificado
con `docker compose config`: `ZASCARR_DATA_DIR="/var/lib/zz"` → `/var/lib/zz`).
O sea, el `.env` funciona para la app y engaña al desinstalador. `bootstrap.sh`
escribe sin comillas (`set_env_var`), así que el caso llega por **edición manual**
— el mismo escenario que motivó A4, y coherente con M7 (valores con espacios y
`&`, que invitan a entrecomillar).

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

### Resultado deseado

1. Un **único lector de `.env`** que interprete como `docker compose` (quitar
   comillas simples/dobles envolventes; no tocar el resto). Compartido, no
   copiado.
2. **Reutilizar `_rutas.sh`** (`resolver_ruta`, `motivo_solapamiento`) en vez de
   las versiones locales; y `comprobar_requisitos` de `_comun.sh`.
3. **Comprobar que el directorio existe antes de purgar** y distinguir tres
   estados: «no había nada» / «se borró» / «no se pudo borrar (quedan restos)».
   Nunca «borrado» sin comprobarlo.
4. Leer la imagen de Postgres del propio `docker-compose.yml`.

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
(`models/__init__.py:539`, `LocalAlias.pattern_norm`), así que **las dos
mitades del mismo filtro comparan en espacios distintos**: la igualdad directa
con `normalize_series_name` y la de alias con `normalize_title`.

### Resultado deseado

- Una sola normalización para comparar en el filtro de D8: la de los alias
  (`normalize_title`), que es la que ya está persistida en `local_aliases`.
- `normalize_series_name` sigue teniendo sentido donde la comparación es *fuzzy*
  contra títulos de release (`orchestrator.py:542,560`), que es un problema
  distinto; si se queda, que sea **a propósito y documentado**.
- Prueba de **paridad** sobre el mismo corpus que `test_title_norm.py`
  (`The Sandman`, `Sandman, The`, `S.H.I.E.L.D.`, `Nausicaä`, `Die
  Fantastischen Vier`, …): los casos que deben colapsar, colapsan; los que no,
  quedan listados como divergencia esperada. Es lo que evita que vuelvan a
  separarse sin que nadie se entere.

---

## Referencias consultadas

- **Internas (son la referencia principal aquí):** `_rutas.sh` (A9) y
  `_comun.sh`; `bootstrap.sh` (A1/A3/M7); `docker-compose.yml`;
  `docs/design/benchmark-E4-avisos.md`; `test_title_norm.py` (el patrón de
  prueba de paridad que se quiere imitar).
- **Docker Compose**: semántica de `.env` (las comillas se quitan) —
  **verificado en local** con `docker compose config`, no citado de memoria.
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
2. `.env` entrecomillado y el directorio **ausente** → «no había nada que
   borrar», no «borrado».
3. `ZASCARR_DATA_DIR` que es un **symlink roto** → se detecta y se aborta
   (hoy `readlink -f` no lo ve).
4. `ZASCARR_DATA_DIR` y biblioteca con el **mismo inodo** por bind mount →
   se aborta el `--purge` (hoy `se_solapan` no lo ve).
5. `webhook_url` con esquema no `http(s)` o sin host → rechazado en Ajustes con
   mensaje.
6. `webhook_type` desconocido → rechazado al guardar (hoy cae en `generic`).
7. «Enviar aviso de prueba» → manda un mensaje de prueba y muestra éxito o la
   causa del fallo.
8. Un fallo de envío registra la causa (código HTTP o clase de excepción) y
   **no** la URL ni el token.
9. Modo «solo recuento» → el cuerpo no lleva ningún nombre de fichero.
10. Paridad `normalize_series_name`/`normalize_title` sobre el corpus de
    `test_title_norm.py`: iguales donde debe, y divergencias esperadas listadas.

## Orden de commits sugerido

1. `uninstall.sh`: lector único de `.env` + reutilizar `_rutas.sh` + distinguir
   los tres estados + imagen del compose (con sus pruebas, que hoy no existen
   para este script).
2. E4: validación de tipo/URL + botón de prueba + causa en el log + modo
   recuento.
3. M2: unificar la normalización del filtro D8 + prueba de paridad.

Cada uno es un cambio de dominio distinto: pueden ser commits (o PR) separados.

## Lo que no está verificado

- No se ha ejecutado `uninstall.sh` de verdad (borra contenedores e imágenes);
  el fallo de las comillas está **reproducido en aislamiento** (el `grep|cut` +
  `readlink -f` + comprobación de restos), no con `docker`.
- No se ha probado ningún webhook real (ni ntfy ni Gotify) desde este entorno.
- La prueba de paridad de normalizadores no existe todavía; esta ficha solo fija
  qué debe comprobar.
- No se ha medido cuántas series reales cambiarían de resultado al unificar la
  normalización del filtro D8. Antes de tocar el filtro conviene contarlo contra
  una instalación real (`scripts/medicion/` es el sitio).

## Decisión

**Adoptar** los tres arreglos, en ese orden, cada uno con sus pruebas primero.
**Descartar** seguir con `readlink -f`/`se_solapan` locales, el `else` silencioso
de tipos de webhook y la convivencia de los dos normalizadores en el filtro.
