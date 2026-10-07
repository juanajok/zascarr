# Backlog de producto: ZascArr "listo para usar"

## Visión y persona

**Visión:** un coleccionista de tebeos instala ZascArr una vez, apunta a su
carpeta de descargas, y a partir de ahí su tebeoteca se organiza, se enriquece
y se completa sola — sin saber qué es Docker, PostgreSQL ni un indexador.

**Persona principal — "El Coleccionista":** aficionado al tebeo con cientos o
miles de CBZ/CBR acumulados, mezcla de grapa americana, manga y clásicos
Bruguera. Sabe leer en Kavita o en su tablet. No sabe, ni quiere saber, qué es
un contenedor. Su frustración actual: carpetas caóticas, duplicados, tebeos
descargados a medias y no saber qué le falta de una saga.

**Implicación de producto honesta:** el estado actual del repo es un backend
con API REST. Para esta persona, `curl http://127.0.0.1:8000/api/series` no es
"usable". El agujero de producto más grande del proyecto no es ningún bug del
peer review — es la **Fase 6 (UI web)**, que para este stakeholder no es una
fase futura sino EL producto. Todo el backlog fluye de esa constatación.

## Backlog priorizado

Formato: ID · historia · criterio de aceptación clave · prioridad
(P0 = indispensable para el release, P1 = primera mejora, P2 = parking) ·
estimación (S < 2 días, M < 1 semana, L > 1 semana).

**Proceso de diseño:** antes de implementar una historia P0/P1 de comportamiento nuevo,
rellena la ficha de referencia en `docs/design/benchmark-referencias.md` (comparar las
referencias pertinentes y registrar adoptar/adaptar/descartar con versión y pruebas; ver
CLAUDE.md §13). Un arreglo evidente de texto o CSS no requiere ficha.

### Épica A — "Lo instalo yo solo"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| A1 | ~~Como coleccionista, quiero un único comando o script que lo instale todo, para no tener que seguir un manual de 20 pasos~~ | ~~`bootstrap.sh` pregunta 3 cosas (¿dónde están tus tebeos? ¿dónde descargas? ¿idioma?) y termina con una URL que funciona~~ | ✅ Hecho | M |
| A2 | ~~Como coleccionista, quiero que el instalador me diga en español llano qué falló ("no encuentro el disco", no "exit code 1")~~ | ~~Mensajes de error del bootstrap mapeados a causas y soluciones comunes~~ | ✅ Hecho | S |
| A3 | ~~Como coleccionista, quiero que si algo se tuerce, mi colección nunca se dañe~~ | ~~El instalador y el importador NUNCA borran archivos originales; solo copian/mueven a destinos verificados~~ | ✅ Hecho | S |
| A4 | ~~Como coleccionista, quiero desinstalar sin dejar restos ni perder mi tebeoteca~~ | ~~`scripts/uninstall.sh` (`make uninstall`/`make uninstall-purge`): borra contenedores, red e imagen propia; conserva SIEMPRE `HOST_LIBRARY_DIR` y las carpetas de descargas, con o sin `--purge`. Sin `--purge` también conserva `ZASCARR_DATA_DIR` (Postgres/Redis/portadas) y `.env`; con `--purge` los borra también, nunca la biblioteca — con las rutas resueltas y validadas contra solapamientos antes de tocar nada, y el resultado real verificado (no asumido) antes de decir "completada". Confirmación explícita antes de tocar nada y resumen claro al final de qué se borró y qué se quedó, con ruta exacta~~ | ✅ Hecho | S |
| A5 | Como coleccionista con el disco casi lleno, quiero repartir tradiciones entre discos sin engañar al sistema | N carpetas-raíz; cada una asignada a una o varias tradiciones; el importer escribe en la raíz que le toca a esa tradición | P2 | L |
| A6 | ~~Como coleccionista, cuando abra ZascArr fuera de localhost quiero contraseña y que funcione tras un reverse proxy~~ | ~~`auth_mode` (`none`/`password`/`user_password`) editable desde `/ui/ajustes` → Seguridad, mismo mecanismo de override en caliente que D11 (sin migración nueva). Cookie de sesión firmada con HMAC-SHA256 para la UI (30 días) + HTTP Basic Auth para `/api/*` — ambos caminos comparten las mismas credenciales. Contraseña siempre PBKDF2-SHA256, nunca en claro. `AuthMiddleware` global, no-op mientras `auth_mode="none"` (por defecto) — la suite existente no lo ve~~ | ✅ Hecho | M |
| A7 | Como quien ya tiene un usuario de servicio propio para toda la suite *arr (o quiere uno distinto de `media`), quiero poder elegirlo al instalar en vez de depender de exportar `ZASCARR_USER` a mano | `bootstrap.sh` pregunta el usuario de servicio (por defecto `media`, Intro lo acepta) igual que ya pregunta biblioteca/descargas/idioma; si no existe, `asegurar_usuario_servicio()` lo crea (ya es idempotente, solo falta que el nombre venga de la pregunta y no solo de la variable de entorno) | P2 | S |
| A8 | ~~Como administrador, quiero que las migraciones de la BD corran DENTRO del contenedor, para que el instalador no tenga que tocar el Python del host de la Pi~~ | ~~`bootstrap.sh` hacía `pip install --break-system-packages -e .` y `alembic upgrade head` contra el Python del sistema — origen del conflicto `typing_extensions` (M3) y de la exigencia de Python 3.11+ en el host. Ahora: `docker compose build zascarr` explícito, luego `docker compose run --rm zascarr alembic upgrade head` — `DATABASE_URL` lo resuelve el propio `docker-compose.yml` desde `.env` (por nombre `postgres`, no `127.0.0.1`). El chequeo de versión de Python en el host desapareció entero: no hace falta ningún Python fuera del contenedor. `scripts/update.sh` sigue el mismo patrón~~ | ✅ Hecho | M |
| A9 | ~~Como coleccionista, quiero que el instalador me avise si doy la misma carpeta para biblioteca y para descargas, en vez de dejarlo pasar en silencio~~ | ~~`bootstrap.sh` compara la ruta **efectiva** de `HOST_LIBRARY_DIR` con la de `HOST_DOWNLOADS_DIR`/`HOST_AMULE_INCOMING_DIR` —symlinks resueltos, no el texto escrito— y avisa también si una está **dentro** de la otra (dos carpetas anidadas tienen inodos distintos y aun así se solapan), muestra las rutas resueltas y exige confirmación explícita antes de seguir. No cambia rutas, permisos ni montajes~~ | ✅ Hecho | S |
| A10 | ~~Como coleccionista con `ufw` activo (caso real, reportado: ya protege el resto de la suite *arr con reglas "solo LAN"), quiero que el instalador detecte que el puente de Docker no está permitido en los puertos de Prowlarr/Transmission/aMule y me dé el comando exacto para arreglarlo, en vez de que "Probar conexión" falle sin más pista~~ | ~~`scripts/diagnostico-red.sh` (nuevo, **solo lectura**: no ejecuta `ufw`) lee de Docker la **subred y la puerta de enlace reales** de la red que usa el contenedor —no las adivina—, comprueba a dónde resuelve `host.docker.internal` **dentro** del contenedor, mira las reglas de `ufw` con contención CIDR (una regla atada a otra interfaz no cuenta) y, si falta, imprime el `ufw allow from <subred real> to any port <puerto> proto tcp` **para que lo pegue el usuario**. Si no puede determinarlo, lo dice y no propone regla alguna. Se invoca al final de `bootstrap.sh`, desde `/ui/ajustes` y a mano. Ficha en `docs/design/benchmark-A10-red-docker.md`~~ | ✅ Hecho | S |
| A11 | ~~Como coleccionista, quiero que me pregunten **si quiero abrir ZascArr a mi red local** en vez de editar el `docker-compose.yml` a mano, para poder usarlo desde el móvil sin abrir la puerta por descuido~~ | ~~Pregunta explícita en el instalador (o en Ajustes) con tres opciones —«solo esta máquina», «mi LAN», «tras proxy inverso»— y la publicación del puerto consecuente: la primera deja `127.0.0.1`, las dos que abren **exigen contraseña** (A6) y la tercera pide además dominio y TLS. Por defecto, la primera. Decisión y motivos en **ADR 0004**~~ **Hecho:** pregunta en `bootstrap.sh` (opción por defecto = solo esta máquina) y paso de contraseña **antes** de publicar el puerto; si no se consigue, no se abre. Ficha `docs/design/benchmark-A11-exposicion.md`, ADR 0004 | ✅ Hecho | M |

**Notas de implementación (A2+A3, hecho):**

- **A9 (2026-09-28, hecho):** `scripts/_rutas.sh` (nuevo, *sourceable* y sin efectos: **no** toca rutas, permisos ni montajes) resuelve cada ruta con `realpath -m` —`-m` porque en una instalación nueva la biblioteca todavía no existe: canonicaliza lo que hay y conserva el resto— y compara sobre la ruta **efectiva**, no sobre lo que se escribió. Tres decisiones que conviene no deshacer sin querer: **(1)** se comprueban **dos** cosas, no solo `(st_dev, st_ino)` como decía el backlog: la igualdad de inodo no ve dos carpetas **anidadas** (inodos distintos, pero el importador escanea recursivamente y se solapan igual), y el texto tampoco ve dos rutas distintas que son la misma carpeta por un bind mount — se comprueban las dos, y el anidamiento se decide **por componentes** (`"${a}/" == "${b}/"*`), que es lo que hace que `/media/lib` NO cuente como dentro de `/media/library` aunque sea prefijo de texto. **(2)** Se compara la **biblioteca contra cada cola**, y **no** las dos colas entre sí: `bootstrap.sh` da a descargas y a aMule la misma carpeta **a propósito** (dos montajes —`/media/downloads` y `/media/incoming`— del mismo sitio), así que comparar esa pareja habría avisado en **todas** las instalaciones — falso positivo detectado ejecutando el bloque real, no leyéndolo. **(3)** Si hay solapamiento se **pregunta** (por defecto NO, y sin terminal también NO) y no se cambia nada. **(4)** Un `realpath -m` a secas **no** basta para lo que promete el mensaje de error: está pensado justamente para canonicalizar rutas con componentes ausentes o no disponibles, así que **sigue un symlink roto y devuelve su destino inexistente como si fuera una carpeta nueva legítima** (lo destapó la revisión: el test que había usaba un fichero en medio, no un enlace colgante). Ahora se inspeccionan también los componentes de la **ruta original** con `[[ -L ]] && [[ ! -e ]]`: se acepta un sufijo nuevo, pero **todo lo que ya existe —symlinks incluidos— tiene que resolverse de verdad**. Cubre el enlace roto como ruta final, como componente intermedio, con sufijo detrás, y el bucle. Si una ruta no se puede resolver se dice con el nombre del enlace y se corta sin tocar nada. En `.env` sigue guardándose **lo que el usuario escribió**, no la ruta resuelta: reescribirla sería "cambiar rutas automáticamente", que es justo lo que A9 no hace. Regresión: `tests/test_bootstrap_rutas.py` (39 casos, sin BD) monta un árbol sintético —carpetas iguales, dos symlinks distintos al mismo directorio, anidadas, anidamiento por symlink, prefijo de texto que NO es anidamiento, `stat` simulado para el caso del bind mount, fichero por medio, symlink roto (final, intermedio y con sufijo detrás), bucle de symlinks y symlink **válido** con sufijo nuevo— y comprueba además el **idioma exacto** con el que `bootstrap.sh` llama a la comprobación bajo `set -euo pipefail`: si el código de retorno se capturase mal, un solapamiento detectado abortaría el instalador **antes** de poder preguntar. La lógica vive en Bash, no en el paquete de Python, porque la usa el instalador **en el host** antes de que exista nada instalado.
- **A10 (2026-09-28, hecho):** `scripts/diagnostico-red.sh` (nuevo, **solo lectura**) + el mensaje de «Probar conexión» apuntando a él. La ficha (`docs/design/benchmark-A10-red-docker.md`) fija el criterio que pedía la revisión: **comprobar la subred y el recorrido REALES antes de imprimir un comando**, porque una regla aparentemente precisa dirigida a la red equivocada es peor que admitir «no puedo determinarlo». Lo que se hace y por qué: **(1)** la subred y la puerta de enlace se leen de `docker network inspect` sobre la red del contenedor, no se asumen — la subred «de Docker» que todo el mundo escribe (`172.17.0.0/16`) es la de `docker0`, y la red de Compose es **otra** (medido en sandbox: `172.18.0.0/16`); **(2)** se comprueba el **recorrido** dentro del contenedor (`host.docker.internal` vs. la puerta de enlace real): en el sandbox se reprodujo el fallo de producción — resolvía a `172.17.0.1` mientras su red tenía `172.18.0.1` — y esa causa **no la arregla ninguna regla de ufw**, así que se avisa con los dos valores antes de proponer nada; **(3)** la cobertura de las reglas se decide por **contención CIDR** (en Bash, sin dependencias), para que `172.16.0.0/12` —la regla que el proyecto ya recomendaba— cuente como cobertura de `172.18.0.0/16` y no se proponga una redundante, y para que la subred **equivocada** no cuente como cobertura; **(4)** una regla atada a **otra interfaz** (`on eth0`, el patrón «solo LAN») **no** cuenta, y por eso la regla propuesta **no lleva `on`**: `ufw(8)` dice que sin `on` aplica a todas, y el nombre del puente (`br-` + 12 hex del id de la red, verificado) cambia si Docker recrea la red; **(5)** si un `DENY`/`REJECT` previo casa con ese puerto, no se propone un `allow` al final (no serviría: `ufw` es *first match wins*) sino un `ufw insert <n>`; **(6)** si la URL apunta a **otra máquina** o a `127.0.0.1` (que dentro del contenedor es el contenedor), **no se propone regla** y se explica por qué; **(7)** si falta `sudo`, el contenedor está parado, la red no declara subred o no se pueden leer las reglas en su forma original, se dice **«no puedo determinarlo»** y **no se imprime ningún comando**. El script **nunca ejecuta `ufw`** salvo `status`/`show added` — hay un test que lo comprueba con un doble que registra todas las llamadas. **Endurecido tras la revisión de la PR #32 (mismo día):** la primera versión aún podía imprimir una regla o dar por cubierto algo que sus datos no sostenían, así que ahora **(a)** sin recorrido comprobado —o con el recorrido roto— **no se propone ninguna regla** (se explica cómo comprobarlo o cómo repararlo), **(b)** con varias redes se usa la subred de **la puerta de enlace a la que resuelve el contenedor**, y si varias comparten esa puerta de enlace se declara indeterminado, **(c)** la decisión **no depende del orden**, porque `ufw(8)` avisa de que `show added` no conserva el orden original ni refleja el cortafuegos activo: si alguna regla **deniega** el tráfico no se propone `allow` al final **ni** se dice que ya está cubierto, y se remite a `ufw status numbered`; y si las dos fuentes de reglas no cuadran, no se decide; **(d)** los puertos salen de la **configuración ACTIVA** leída dentro del contenedor con la precedencia de D11 (Ajustes sobrescribe `prowlarr_url`/`transmission_url`/`amule_url` en caliente, así que el `.env` puede estar desfasado y una regla calculada sobre él apuntaría al host o al puerto equivocados); si esa configuración no se puede leer **no se analiza el `.env` en su lugar**: o se pasan los puertos con `--puerto`, o se declara indeterminado. **(e)** el recuento de reglas acepta la horquilla de IPv6 (con IPv6 habilitado cada orden aparece como dos reglas activas, IPv4 e IPv6), para no declararse indeterminado en instalaciones válidas. **(f)** `proto udp` y `to <otra dirección>` ya **no** cuentan como cobertura TCP (se interpretan, o la regla queda como desconocida: un `ALLOW` ilegible no acredita cobertura y un `DENY` ilegible impide proponer). Once de las doce regresiones nuevas se comprobaron contra el script anterior. Regresión: `tests/test_diagnostico_red.py` (79 casos, sin red ni ufw reales: dobles de `docker` y `ufw` en el `PATH` para las 12 situaciones de la ficha, más los helpers puros —contención CIDR, parser de `ufw show added`, rangos de puertos y partido de URL— cargados aparte).
- **A2 (bootstrap en español llano):** cada punto de fallo de `bootstrap.sh`
  queda mapeado a una causa y una acción concretas en lugar de un "exit code":
  Docker ausente (cómo instalarlo), plugin compose ausente, demonio parado
  (`systemctl start docker`), disco de tebeos no montado ("no encuentro el
  disco… ¿está conectado?"), disco de descargas sin permisos, PostgreSQL/Redis
  que no levantan (apunta a `docker compose logs`), migraciones fallidas y
  ZascArr que no arranca. Añadido chequeo previo del demonio (`docker info`) y
  guardas `|| die` en cada `mkdir`/`cd`/`docker compose up`/`alembic`/`pip`.
- **A3 (nunca dañar la colección):** nuevo `src/zascarr/utils/fs.py` con
  `sanitize_segment` (un título con "/" o ".." ya no puede escapar de la
  biblioteca al construir la ruta canónica) y `safe_move`/`safe_move_async`
  (nunca sobreescribe un destino ocupado — elige nombre único con sufijo — y,
  entre discos distintos, copia a un temporal y verifica el tamaño ANTES de
  borrar el original; si la copia falla, el original queda intacto). Aplicado
  en `Importer._import_file` y `ReviewService.assign_to_series`, que antes
  usaban `shutil.move` a ciegas (sobrescribía en silencio). `build_library_path`
  sanitiza título y número de issue. Regresión: `tests/test_fs.py` y
  `tests/test_importer.py::TestBuildLibraryPathSanitizado`. El instalador
  documenta su garantía en cabecera: solo crea directorios y copia `.env`,
  jamás borra ni mueve ficheros de la colección.

### Épica B — "Importo mi caos actual"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| B1 | ~~Como coleccionista, quiero arrastrar mi carpeta de descargas y que el sistema la organice solo~~ | ~~El importador procesa `/downloads` y `_Unsorted/` según matcher/triage ya construidos, con informe final legible~~ | ✅ Backend hecho | M |
| B2 | ~~Como coleccionista, quiero ver los tebeos que el sistema no supo clasificar y decidir yo con un clic~~ | ~~Bandeja de "pendientes de revisar" en la UI: miniatura, título detectado, botones "es esta serie / ninguna / ignorar"~~ | ✅ Hecho | L |
| B3 | ~~Como coleccionista, quiero que los duplicados se detecten y no se importen dos veces~~ | ~~Dedupe por SHA256 ya existe; la UI muestra "duplicado de X, descartado" en el informe~~ | ✅ Backend hecho | S |
| B4 | ~~Como coleccionista, quiero que cada tebeo aparezca con portada, guionista, dibujante y sinopsis aunque el archivo no traiga metadatos~~ | ~~Enricher multi-fuente (Comic Vine/AniList/Tebeosfera; GCD pospuesto — ADR-0002) + corrección del bug de `metadata_source='manual'` (C3)~~ | ✅ Hecho | L |
| B5 | ~~Como coleccionista de tankōbon y álbumes BD, quiero que Vol./T/Tomo funcionen tan bien como el # americano~~ | ~~Tests de naming con fixtures reales de releases españolas (patrones `nº`, `v01c047` rescatados de zascarr)~~ | ✅ Hecho | M |
| B6 | Como coleccionista, quiero que mi biblioteca sea legible por Kavita/ComicTagger/cualquier otra herramienta sin depender de ZascArr~~ | ~~Tras enriquecer, escribir `ComicInfo.xml` dentro del CBZ (hoy solo se lee, nunca se escribe). **Contrato fijado (ficha §13, `docs/design/benchmark-B6-comicinfo.md`):** regla de **procedencia** para campos gestionados ya presentes (vacío→rellenar; probado propio→actualizar; desconocido→conservar salvo autorización), una sola entrada `ComicInfo.xml`, **manifiesto de hashes** de las entradas no-XML + `testzip`, temporal hermano verificado **antes** de `os.replace`, `fsync` del temporal y del directorio (durabilidad ≠ atomicidad), **espacio libre** como criterio de seguridad en la Pi, y **recalcular `File.sha256_hash`/`file_size_bytes`** con reconciliación idempotente si falla el commit. Incluye **mapa mínimo de campos** (`Series`/`Number`/`Volume`/`Year`/`Publisher`/`Summary`/`LanguageISO`; `Year` sale de `Issue.release_date` —no de `Series.start_year`— y `LanguageISO` **no** se infiere de la tradición), sin inventar: sin dato no se escribe o se conserva, **previsualización por campo** y **modo `dry-run`** (qué cambiará / qué se conserva, sin escribir) con **un solo plan** compartido entre vista previa y ejecución —que **caduca si el CBZ cambia** entre ambas—, e **informe por lote**. CBR nunca se parchea~~ | ✅ Hecho | M |
| B7 | ~~Como coleccionista, si borro un tebeo del disco a mano, quiero que deje de contar como "lo tengo" sin que yo avise~~ | ~~`Importer.scan_and_import()` (el mismo ciclo que ya existía) revisa en cada pasada, además de las descargas nuevas, todos los `File` ya en biblioteca: el que ya no existe en disco se marca `is_missing=True`/`missing_since` (migración `0014`), sin borrar la fila. Se revierte solo si el fichero reaparece (disco de red que estuvo desmontado, restaurado desde una papelera). Guardarraíles: si la carpeta de la biblioteca en sí parece inaccesible o está vacía (punto de montaje sin desmontar de verdad), o si desaparece una fracción anómala de golpe, no se marca nada ese ciclo. Todo consumidor de "¿lo tengo?" (`Orchestrator._is_fulfilled`, contadores del dashboard, portada de serie) excluye `is_missing=True` — marcar la fila no basta si nadie más la respeta~~ | ✅ Hecho | S |
| B8 | Como administrador de la Pi, quiero apagar una fuente de metadatos (p.ej. Tebeosfera) sin redesplegar si se rompe su scraping | Toggle runtime por proveedor (`comicvine_enabled`/`anilist_enabled`/`tebeosfera_enabled` en `Settings`, mismo patrón que `forum_enabled`) + estado visible en el healthcheck | ✅ Hecho | S |

- **B8 (2026-09-28, hecho):** `comicvine_enabled`/`anilist_enabled`/`tebeosfera_enabled` (default `True`) en `config.py`, override en caliente vía D11 (`OVERRIDABLE_FIELDS["fuentes"]`). Apagar una fuente → el enricher **no instancia ni llama su cliente** (cero tráfico) y **no marca** `enrichment_attempted_at` (no consume el plazo de reintento); reactivar la vuelve elegible. Toggles en `/ui/ajustes` + estado `fuentes` en `/api/health`. Ficha en `docs/design/benchmark-B8-fuentes.md`. Regresión: `TestFuentesDesactivadas` (3 casos).
| B9 | Como coleccionista, quiero que un número sin título no se quede "Issue 5 - Unknown" y que cada tradición nombre distinto sin que yo edite plantillas | Plantillas de naming por tipo (número / sin título / special version / pack) con padding configurable; UI solo on/off y preset | P2 | M |
| B10 | Como coleccionista, si descargo un pack con varios números quiero que se deshaga solo; y si llega un CBR, prefiero CBZ si es posible | Extracción de archives multi-número; conversión cbr→cbz opt-in con cadena de preferencia documentada | P2 | M |
| B11 | ~~Como coleccionista que ya tiene su tebeoteca organizada en disco, quiero que ZascArr la reconozca sola en el primer arranque, sin tener que redescargar ni mover nada — como hace Sonarr al añadir una carpeta raíz con series que ya existen~~ | ~~`LibraryAdopter` (nuevo): escanea `library_path` recursivamente, reutiliza el mismo triage+matcher que `Importer` (extraído a `_triage_and_match`, compartido), pero **registra en BD sin mover ni renombrar**. Dispara sola en el primer arranque (background task en `main.py::lifespan`) si `library_path` tiene archivos y `series` está vacía, y solo UNA vez (marcador en `runtime_settings`)~~ | ✅ Hecho | L |
| B12 | ~~Como coleccionista, cuando el parser SÍ extrae título+número pero no hay serie que iguale (o el score queda por debajo del umbral), quiero ver una sugerencia con la que confío en un clic, en vez de rebuscar a mano en Pendientes~~ | ~~`MatchResult.candidates` (ya existía) se serializa en `File.metadata_` (`Importer` y `LibraryAdopter`, mismo helper compartido); `/ui/pendientes` muestra el mejor candidato con su score y un botón "sí es esta serie" que reutiliza el formulario de asignación ya existente — confirmación explícita, nunca autoasignación~~ | ✅ Hecho | M |
| B13 | ~~Como coleccionista, si asigno a mano varios archivos del mismo patrón ("La Patrulla X Omnigold N (...)") a la misma serie, quiero que ZascArr deje de preguntarme para ese patrón~~ | ~~Tabla `local_aliases` (patrón de nombre → series_id), aprendida en `ReviewService.assign_to_series` (toda asignación manual desde Pendientes es por definición una corrección) y consultada por `SeriesMatcher.decide()` ANTES del fuzzy. Alias local de esta instalación, nunca una regla global — CLAUDE.md §5~~ | ✅ Hecho | M |
| B14 | Como coleccionista con la tebeoteca ya ordenada por carpetas, quiero que ZascArr use el NOMBRE DE LA CARPETA para saber de qué serie es cada archivo, porque es justo lo que yo ya le dije al ordenarla | La carpeta es la señal más fiable de esta biblioteca y hoy se tira entera: `Comics/JSA (1999)/JSA (2004-08) 62` da serie `JSA 62`, mientras la carpeta dice `JSA` + año `1999`. Medido sobre 44 rutas reales (2026-09-25): la carpeta arregla ~la mitad de los fallos que quedan tras el fix del parser de v1.4.8 (XIII, JSA, Promethea, Superman, La Mazmorra, Monstress, Flash, WildCATS, Patrulla-X). La carpeta debe ser un CANDIDATO más que se valida contra la BD, nunca un override ciego: en `Comics/Green Lantern - Saga de Geoff Johns/03 Green Lantern Corps - Recarga.cbr` la carpeta miente y el nombre de archivo acierta. **Sigue pendiente** (la biblioteca real que motivó B14 tiene una carpeta plana de 711 archivos sueltos, ver B21 — ahí B14 no ayuda porque no hay carpeta). **Auditoría hecha (2026-10-05):** `docs/design/auditoria-b14-carpetas.md` — la carpeta no se usa hoy en ningún sitio; sobre 1.542 nombres reales el 63 % ya coincide con su carpeta y **el 8 % de la biblioteca (123 archivos) tiene una carpeta que NO es su serie** (autor, contenedor, crossover/orden de lectura, arco), incluidas carpetas que coinciden en un 89-100 % con sus archivos: **la heurística de mayoría y los umbrales ensayados (50-80 %) no garantizan ausencia de errores en ese corpus** (cifras obtenidas con el parser anterior a la PR #81, conservadas como evidencia histórica); política conservadora aceptada: la carpeta sugiere y agrupa, **no asigna sola**, y se valida contra el catálogo. Contexto comprobado en producción: 5 series, 14 archivos registrados sin Issue, 1.542 visibles y ningún marcador de adopción → el bloqueo era el registro con catálogo previo (PR #83); crear las series que faltan, con confirmación humana, queda para después **Ficha de la historia siguiente (2026-10-05):** `docs/design/ficha-propuestas-desde-carpetas.md` — propuestas de serie explicadas y confirmables desde el contexto de carpetas (Kapowarr, Sonarr, Mylar3, Suwayomi-Server y Aidoku leídos en versiones concretas); sin implementar. **Rebanada 1 (2026-10-06):** superficie de revisión de solo lectura; ficha técnica `docs/design/rebanada-1-superficie-de-revision.md`. **1a hecha** (servicio `services/revision_carpetas.py` + `GET /api/revision/carpetas`, lógica pura en `core/carpetas.py`, pruebas de aceptación sobre Postgres real); **1b hecha** (vista HTML de solo lectura `/ui/pendientes/carpetas`, sobre el mismo servicio, verificada en navegador real; sin crear series ni asignar: eso es la rebanada 2). | P0 | M |
| B21 | ~~Como coleccionista, cuando dos archivos tienen la misma forma ("42 Dreadstar...", "100 Balas...") pero uno el número es orden de lectura mío y el otro es parte del título, quiero que ZascArr lo distinga sin que yo tenga que organizarlos en carpetas~~ | ~~`core/cohort.py` (nuevo): agrupa nombres por "firma" (sin ningún token numérico, sin créditos de traductor/corchetes) y decide por EVIDENCIA — si el prefijo VARÍA en ≥3 hermanos con el resto del nombre estable, es orden de lectura y se descarta; si es CONSTANTE en toda la cohorte, es parte del título y no se toca. Nunca crea una serie (solo informa el número), nunca alimenta B13 en silencio (solo el humano aprende un alias), determinista por ciclo (cohorte congelada al principio de `scan_and_import`/`adopt`). Medido: +10 puntos de acierto poblacional (73%→83% clasifica, 76%→86% veraz) sobre la muestra oficial de 62 archivos de contenido único~~ | ✅ Hecho | M |
| B15 | ~~Como coleccionista, quiero que las ediciones tipo Omnigold/Integral/Tomo/Vol no se queden en Pendientes para siempre~~ (la mitad "carpeta que NO es una serie" sigue abierta, ver nota) | ~~El número de un Omnigold/Integral/Tomo/Vol vuelve a capturarse como `issue_number` (revierte el "SIEMPRE a Pendientes" de RF-07) pero etiquetado con `edition_kind` en `naming.py` (`"omnigold"/"integral"/"tomo"/"volumen"`; **desde la PR #10 el matcher SÍ lo usa** para decidir la edición, vía el mapa compartido `EDITION_KIND_A_FORMAT` — antes solo informaba qué `Issue.format` correspondía en el camino manual; ver la nota de la zona B15). Al confirmar la asignación en Pendientes, `ReviewService.assign_to_series` re-parsea el nombre original y crea el `Issue` con `format=OMNIBUS` (Omnigold/Integral) o `TRADE_PAPERBACK` (Tomo/Vol) en vez del `SINGLE_ISSUE` por defecto — **sin migración**: `Issue.format`/`IssueFormat` ya existían en el modelo desde antes de B15, así que no hizo falta el `collection_number` como columna nueva que se había previsto originalmente~~ | ✅ Hecho (parcial, ver nota) | M |
| B16 | ~~Como coleccionista, quiero saber cuándo tengo el mismo tebeo en dos carpetas, en vez de que el sistema elija una en silencio~~ | ~~`LibraryAudit` (nuevo) + `/ui/auditoria`: informe de SOLO LECTURA que agrupa *mismo contenido* (SHA256), *misma obra en otra edición*, *carpetas repetidas* y *carpetas sin ningún tebeo*. No borra, no mueve y no sugiere qué borrar. La adopción (B11) deja de dispararse sola en el primer arranque y pasa a ser un botón explícito con el informe delante~~ | ✅ Hecho | M |
| B20 | Como coleccionista que quiere leer en Kavita (tablet), quiero exportar una colección a un árbol de carpetas que Kavita entienda, sin tocar ni duplicar espacio en mi biblioteca canónica | **Diseño fijado el 2026-09-26, pendiente de implementar** (spec completa en `docs/design/B20-exportacion-kavita.md`, ver nota). Relación con B14 **conceptual, no de dependencia** (B20 crea carpetas de DESTINO para Kavita; B14 analiza carpetas de ORIGEN en la adopción — la exportación no aporta contexto a los ficheros planos originales); el formato de exportación es el contrato de lectura de los futuros consumidores de la exportación. Tres decisiones clave: `hardlink` por defecto (nunca `move`, la canónica no se toca; `copy` si el destino está en otro filesystem **o si el archivo se va a parchear** — un CBZ parcheado por hardlink compartiría inodo con la canónica y el parche alcanzaría al original; precisión de la revisión del 2026-09-27). **Límite explícito de esa garantía:** el hardlink no aísla el origen de terceros — si Kavita o un etiquetador editan el destino en sitio, editan la canónica (mismo inodo); el manifiesto detecta la deriva, no la evita, y quien quiera aislamiento debe elegir `copy` para TODA la exportación. CBR nunca se parchea (sonda del 2026-09-25: 0,5% de ComicInfo en CBR, escribir en RAR exige dependencia propietaria ya descartada — viaja tal cual, Kavita clasifica por nombre, que ya es canónico tras B15); `_zascarr_manifest.json` por colección exportada, que hace la exportación idempotente (re-exportar = solo novedades) y detecta deriva (destino editado a mano) sin pisarlo nunca en silencio | P1 | L |
| B22 | Como coleccionista, quiero que antes de tocar el catálogo se sepa de verdad cuántas ediciones distintas y colisiones tengo, y que las cuatro decisiones del modelo de identidad editorial queden cerradas por escrito, para no migrar a ciegas | **Solo censo + contrato (sin migración):** (1) censo de la biblioteca real — issues por `format`, colisiones de `UNIQUE(series_id, issue_number, volume)`, `volume=NULL`, `File.covered_issue_ids` no vacíos, y revisión a mano de unos pocos casos reales de Omnigold/integral/tomo manga/pack entre series; (2) ficha §13 aplicada a Kapowarr y Mylar3 solo en lo pertinente (identidad por edición, archivo↔issues, recopilaciones — `docs/design/benchmark-identidad-editorial.md`); (3) ADR cerrando las cuatro decisiones: `number_key`/especiales, edición vs `Imprint`, universo esperado de grapas, archivo↔publicaciones. **Criterio de parada:** si los datos apenas contienen coberturas contrastables o ninguna fuente da evidencia, recomendar «posponer» es un resultado válido, no un fracaso. Especificación en `docs/design/identidad-editorial-cobertura.md` | en curso | M |

**Notas de implementación:**

- **B6 (2026-09-28, hecho):** escritura de `ComicInfo.xml` dentro del CBZ, con el contrato de `docs/design/benchmark-B6-comicinfo.md` implementado pieza a pieza, sin atajos. Cuatro ficheros nuevos y una frontera respetada (`core/` no importa `models/`):
  - **`core/comicinfo_write.py`** — la precedencia, pura y sin disco ni BD. **`plan()` es la única función que decide** qué se escribe; devuelve una lista de `CampoPlan(tag, accion, actual, nuevo)` con cinco acciones: `cambia`, `conserva`, `ya_coincide`, `sin_dato` y `bloqueado`. El `dry-run` y la ejecución real consumen **esa misma lista** (`tests/…::test_un_solo_plan_entre_simulacion_y_ejecucion` comprueba que son idénticas) — no hay dos caminos que puedan divergir. `fusionar_xml()` parte del XML existente y **preserva todo elemento desconocido** (`PageCount`, `BlackAndWhite`, lo que sea): solo sustituye los `cambia`. Un valor en blanco (`""`, `"  "`) se trata como ausencia de dato, nunca como dato.
  - **`utils/cbz.py`** — la parte que protege la colección. Antes de tocar nada: **manifiesto SHA256 de las entradas no-XML** (por streaming) y **espacio libre** (`shutil.disk_usage` sobre el directorio real, margen de 1 MiB — en una Pi compartida no es una optimización, es la diferencia entre «no se pudo etiquetar» y «se llenó el disco a mitad de copia»). El CBZ nuevo se construye en un temporal **hermano** (`.{nombre}.zascarr.tmp`, mismo directorio ⇒ mismo sistema de ficheros ⇒ `os.replace` atómico), se **verifica antes** de publicarlo (ZIP íntegro con `testzip`, manifiesto idéntico al original y **exactamente una** `ComicInfo.xml`) y solo entonces se hace `fsync` del temporal, `os.replace` y `fsync` del directorio — durabilidad y atomicidad son garantías distintas y se piden por separado. Cualquier fallo limpia el temporal y deja el original **intacto**.
  - **`services/tagger.py`** — la orquestación con la BD. Mapa mínimo de la ficha: `Series.title`, `Issue.issue_number`, `Issue.volume`, **`Year` del año de `Issue.release_date`** (nunca `Series.start_year`), `Series.publisher.name` y `Issue.synopsis`. `LanguageISO` **no se genera jamás**: la tradición no acredita el idioma del ejemplar; si el XML ya lo trae, es preservación. Un campo en `locked_fields` (H3) sale como `bloqueado` y no se escribe aunque el dato exista y la precedencia lo permitiría. La procedencia se apoya en `File.metadata_["comicinfo_propio"]` (lo que ZascArr escribió la última vez): coincide con el XML ⇒ *overlay*; no coincide o no hay rastro ⇒ **se conserva lo manual**. El plan **caduca** (tamaño + mtime re-comprobados entre calcularlo y escribirlo) y **no se aplica a un CBZ distinto del previsualizado**. Tras el reemplazo se **recalculan `File.sha256_hash`/`file_size_bytes`**; si el commit falla, el reemplazo ya ocurrió (atómico) y la pasada siguiente **reconcilia** la BD sin volver a reescribir el XML (`_reconciliar`, más `--reconciliar-todo` para forzarlo) — reetiquetado idempotente. CBR/CB7/PDF se saltan sin abrirse. Todo el I/O bloqueante va por `asyncio.to_thread` (CLAUDE.md §4).
  - **`cli/etiquetar.py` + `scripts/etiquetar.sh`** — el comando administrativo que pide la ficha (punto 12). **Por defecto no escribe nada**: imprime el plan campo a campo en español llano (`cambiará` / `se conserva (procedencia desconocida)` / `ya coincide` / `sin dato (no se inventa)` / `bloqueado`). `--apply` lo aplica; `--no-overwrite` es la estrategia *add missing* de ComicTagger (solo rellena vacíos, ni siquiera con prueba de autoría); `--dryrun`, `--file-id`, `--limit`, `--reconciliar-todo` y `--json` completan la superficie. El wrapper entra por `docker compose run --rm zascarr` (el mismo camino que las migraciones en `update.sh`): **Python no vive en el host**, y las rutas de `File.file_path` solo son válidas dentro del contenedor.
  - **Regresión:** 96 casos — `tests/test_b6_comicinfo.py` (22, precedencia y fusión), `tests/test_b6_cbz.py` (18, manifiesto, dos `ComicInfo.xml` → una, espacio insuficiente, fallo a mitad y temporal único) y `tests/test_b6_cli.py` (6, el informe —`--json` incluido— y el código de salida de un lote cortado), sin BD; y `tests/test_b6_tagger_pg.py` (50 contra Postgres real: `Year` de `release_date`, `LanguageISO`, procedencia manual vs. overlay, `locked_fields`, `.cbr` intacto, `dry-run` que no escribe ni cambia mtime ni toca la sesión, plan único, plan caduco, reconciliación del hash, vida del bloqueo y fallo de BD a mitad de lote). Verificado además **a mano de punta a punta** contra Postgres real (23 casos: 21 sanos + 1 XML roto + 1 fichero ausente): simulación sin cambios en el hash → `--apply --limit 20` dos veces avanza de verdad (18+1+1 → 3+19) y acaba con los 22 presentes etiquetados → tercera pasada sin trabajo pendiente → cero temporales.
  - **Endurecimiento tras la revisión de la PR #30 (2026-09-28, hecho):** la revisión encontró cuatro rutas que los tests no alcanzaban y que tocan garantías centrales. **(1) `--limit` se quedaba atascado:** `run()` ordenaba por `imported_at` y cogía los primeros N sin excluir lo ya hecho, así que la segunda pasada volvía a leer los mismos y el fichero N+1 no recibía nunca su turno. Ahora cada revisión deja una **marca persistente** en `File.metadata_["comicinfo_estado"]` (resultado, `stat` del fichero, hash y los valores deseados con los que se comparó) y `run()` **no gasta cupo** en lo ya revisado y sin cambios; como la marca guarda también los datos de la BD, **una corrección de metadatos vuelve a poner el fichero en la cola** (y el overlay la propaga). Los ficheros **ausentes** tampoco gastan cupo, o unas cuantas rutas rotas dejarían fuera al resto de la biblioteca. **(2) El temporal tenía nombre fijo y se abría en modo que trunca:** ahora se crea **único y exclusivo** con `tempfile.mkstemp` en el mismo directorio, y se limpian los restos propios de un `kill -9` **solo con el bloqueo tomado**; además la secuencia leer → plan → reconstruir → verificar → `os.replace` va **bajo bloqueo por fichero** (el «plan caduca» cubre el cambio externo; el bloqueo, la carrera entre dos ZascArr). **(3) La reconciliación fallaba si cambiaban los bytes pero no el tamaño:** `_reconciliar()` salía antes de calcular el SHA256 cuando `file_size_bytes` coincidía, así que un XML nuevo del mismo tamaño dejaba el hash obsoleto para siempre salvo que alguien supiera usar `--reconciliar-todo`. Ahora se compara el **`stat`** con la marca y, si no cuadra, se recalcula el hash: la pasada normal paga un `stat` por fichero, no un hash. **(4) Un `ComicInfo.xml` ajeno o malformado perdía datos o abortaba el lote:** `fusionar_xml()` sustituía una raíz distinta de `<ComicInfo>` por un árbol nuevo (descartando lo de dentro) y el `ElementTree.fromstring()` de `planificar()` ocurría fuera de los `except` de `ejecutar()`, así que un XML roto tumbaba los 20 ficheros restantes. Ahora una raíz ajena o un XML ilegible son `archivo inválido` —**no se fusiona ni se sustituye**, y se registra por fichero sin abortar el lote— y lo mismo para un `File` cuya ruta ya no existe. El cuarto punto destapó de paso el mismo agujero en `run()`, que se saltaba las guardas de `ejecutar()` (fichero ausente → excepción fuera del lote), y una quinta cosa que solo se vio **ejecutando el comando de verdad**: `--json` reventaba con `Object of type UUID is not JSON serializable` porque `File.id` llega del ORM como `UUID` (normalizado en `ResultadoEtiquetado` y cubierto por `tests/test_b6_cli.py`). Los cuatro casos nuevos se comprobaron **contra el código anterior** para confirmar que fallaban de verdad. Los invariantes 14-19 quedan añadidos a la ficha.
  - **El bloqueo por fichero, rehecho tras una segunda revisión (2026-09-28):** el primer intento usaba un `flock` exclusivo **sobre el propio CBZ**, y eso **no protege la ruta después del `os.replace`**: `flock` va con el *inodo* abierto, y el reemplazo instala uno nuevo. La carrera es silenciosa y fea — A bloquea el inodo viejo; B espera ese mismo inodo; A reemplaza la ruta; C abre el inodo **nuevo** y entra sin esperar a nadie; cuando A suelta, B adquiere el bloqueo de un inodo ya huérfano y **B y C reconstruyen la misma ruta a la vez**, además de poder borrarse los temporales entre sí. Ahora la identidad **sobrevive al reemplazo**: un ***advisory lock* de PostgreSQL por `File.id`** (`services/tagger.py::bloqueo_de_fichero`), que no deja ficheros de bloqueo en la biblioteca y se suelta solo si el proceso muere (la conexión se cierra). **Corregido en una tercera revisión:** ese bloqueo era `pg_advisory_lock` (**de sesión**), y con él el `finally` solo registraba un fallo del `unlock` y seguía. Un bloqueo de sesión **sobrevive al `ROLLBACK`**, y devolver una conexión al *pool* la reinicia con `ROLLBACK` pero **no termina necesariamente esa sesión de PostgreSQL**: si el `unlock` fallaba con la transacción abortada, el bloqueo podía quedarse pegado a una conexión reutilizable —y la afirmación «se cerrará la conexión y soltará el lock» no era cierta—. Ahora es **`pg_advisory_xact_lock`** (de transacción) sobre una **conexión dedicada con su transacción corta**: lo suelta el `COMMIT`/`ROLLBACK` de esa transacción, pase lo que pase con el cuerpo, sin depender de que un `unlock` llegue a ejecutarse. La conexión es dedicada para no retenerlo en la transacción larga del lote hasta el commit final. Regresión: tras abortar la transacción dentro del bloque (un `SELECT 1/0`), otra conexión **sí** puede volver a tomar la clave; comprobado que el diseño de sesión deja la clave **atrapada** (con el viejo da `False`, con el nuevo `True`). `utils/cbz.py` ya no bloquea: documenta que la serialización la pone quien llama, y `_limpiar_temporales_viejos` **exige** ese bloqueo. Toda la escritura en la sesión se movió **fuera** del bloqueo (dentro solo queda el propio `pg_advisory_lock`), para que una transacción abortada no deje el *advisory lock* colgado en una conexión del pool. La regresión coordina **tres ejecutores alrededor de un `os.replace` real** (A se queda dentro tras reemplazar, B espera al inodo viejo, C llega después) y exige que `activos == 1` en ese instante y que nadie borre un temporal vivo; **comprobado que con el diseño de `flock` da 2 escritores simultáneos**. Además, `run()` gana una red de seguridad por fichero (`except Exception` → `error`, registrado). **Y ahí se colaba el segundo fallo de esa tercera revisión:** ese `except` seguía con **la misma `AsyncSession`**, y tras un `flush()` fallido SQLAlchemy exige un `rollback()` completo —capturar la excepción no la recupera—, así que los ficheros siguientes fallaban **todos** con `PendingRollbackError` mientras el informe decía que el lote había continuado, dejando CBZ ya sustituidos esperando reconciliación. Ahora `run()` comprueba si la sesión sigue utilizable: si lo está, el error es de un fichero y el lote continúa; si **no**, revierte, corta el lote y lo declara —con cuántos ficheros ya se sustituyeron y que sus filas se reconcilian solas en la siguiente pasada—, y el comando sale con código **distinto de cero**. Se evaluó aislar cada fichero con un `SAVEPOINT` (la opción preferida de la revisión): **no sirve tal cual**, y se comprobó empíricamente — la mutación tiene que ocurrir **dentro** del savepoint, y aquí se hace antes (en el camino que decide el plan), así que `begin_nested()` hace *autoflush* de los cambios pendientes y el fallo ocurre fuera de la protección: la sesión queda envenenada igual. Hacerlo bien exigía reestructurar toda la escritura alrededor de un diario de mutaciones para cubrir un caso —el error de BD por fila— que en este `UPDATE` no se da: los fallos reales son del motor entero, y ésos no los salva ningún savepoint. Se eligió, por tanto, la segunda opción que la revisión daba por buena: abortar con error explícito. **Matiz de uso que conviene decir:** las marcas de revisión solo se guardan al aplicar; el `dry-run` (modo por defecto) no escribe nada, tampoco en la BD, así que repetir `--dryrun --limit 20` vuelve a mostrar los mismos pendientes.
  - **Lo que B6 NO hace todavía, dicho claro:** no hay botón en la UI (la ficha solo pedía que la simulación viviera *al menos* en un comando administrativo; la UI renderizará el mismo plan más adelante); `--no-overwrite` no tiene ajuste en `/ui/ajustes`; `Genre`, `PageCount` y los créditos por rol — que el lector de `core/importer_triage.py` sí conoce — quedan **fuera del mapa mínimo** y no se escriben; y una biblioteca anterior a esta historia no tiene rastro de autoría, así que sus campos ya escritos quedan como **procedencia desconocida** y solo se rellenan los vacíos (que es justo el comportamiento querido, pero conviene saber que no corrige nada sin autorización explícita).

- **B7 (2026-09-26):** `Importer._detectar_desaparecidos()` (nuevo método, llamado al final de `scan_and_import()`, tras el bucle de importación de descargas nuevas): consulta TODOS los `File` ya en biblioteca y comprueba `Path(file_path).exists()` en un único hop a un hilo (`asyncio.to_thread`, no bloquea el loop — CLAUDE.md §4), no uno por fichero. Marca `is_missing=True`/`missing_since=now()` la primera vez que un fichero deja de existir, y lo revierte solo (`is_missing=False`, `missing_since=None`) si vuelve a aparecer — nunca se repite en el informe mientras siga igual de ausente, y el `File` nunca se borra por esto. **Guardarraíl explícito, verificado en vivo**: si la carpeta de la biblioteca en sí no existe o no es un directorio (disco de red desmontado, USB desconectado), la detección entera se omite ese ciclo — confundir un problema de montaje con "he perdido toda la colección" habría sido mucho peor que no detectar nada un ciclo. `ImportRun.disappeared_count` (migración `0014`, junto con `File.is_missing`/`missing_since`) sigue el mismo patrón que `imported_count`/`duplicate_count`/`unsorted_count`; el log `importer.cycle_done` (`main.py`) ahora dispara también cuando hay desaparecidos/reaparecidos aunque el ciclo no haya escaneado ninguna descarga nueva (antes solo disparaba con `files_scanned > 0`, lo que habría silenciado el aviso). Verificado en vivo contra Postgres real: ciclo con el fichero presente (nada marcado) → borrado a mano → ciclo detecta y marca → ciclo repetido no vuelve a avisar → fichero restaurado → ciclo revierte la marca → biblioteca apuntando a una ruta inexistente → guardarraíl activo, no marca nada.
- **Endurecimiento de B7 tras revisión de PR (2026-09-26):** marcar `File.is_missing` no bastaba — ninguna consulta que significa "¿lo tengo?" lo respetaba todavía. Se comprobaron y corrigieron las tres rutas señaladas en revisión: `Orchestrator._is_fulfilled` (`check_completions`) daba por cumplida una wishlist con un `File` enlazado aunque estuviera marcado desaparecido; `web/dashboard.py` contaba ese mismo `File` en `series_con_archivos`/`issues_importados`/últimas series actualizadas; `web/series.py::portada` podía elegir ese `File` como candidato de portada (e intentar, sin éxito, extraer de un CBZ que ya no existe) en vez de probar el siguiente número o caer al `cover_url` externo. Las tres ganan `.where(File.is_missing.is_(False))`. Además, dos guardarraíles nuevos en `_detectar_desaparecidos` que el guardarraíl original (`exists()`/`is_dir()` de la carpeta) no cubría: un punto de montaje desmontado a menudo deja atrás un directorio vacío pero accesible (`exists()`/`is_dir()` no lo distingue de una biblioteca real — se comprueba que tiene contenido); y una desaparición masiva en un solo ciclo (más de la mitad de una biblioteca de ≥10 ficheros) es mucho más probable un fallo de montaje parcial que un vaciado real a mano — se aborta sin marcar nada y se registra como error, en vez de convertirlo en cientos de cambios de estado silenciosos. Verificado en vivo contra Postgres real: import→borrado→detección→consultas de posesión en 0 (dashboard 100%→0%, portada 404, `check_completions` no cierra la wishlist)→restauración→detección→consultas de posesión de vuelta a 100%/`check_completions` cierra la wishlist.

**Limitación documentada, no bloqueante (revisión de PR, 2026-09-26):** `_detectar_desaparecidos()` hace `select(File)` sobre TODA la tabla mientras solo comprueba la salud de UNA raíz (`self._library`). Con la arquitectura actual esto es correcto — solo hay una raíz de biblioteca y todo archivo se mueve ahí al importarse, `_Unsorted` incluido — pero si en el futuro se admiten varias raíces con montajes independientes, un fallo en una no debería contaminar el cálculo de "desaparición masiva" (ni las marcas de `is_missing`) de otra. La siguiente iteración, si esto cambia, debería agrupar los `File` por raíz y verificar cada una por separado. Tampoco la comprobación de "directorio no vacío" certifica que el disco CORRECTO esté montado (podría montarse por error un disco distinto que también tenga contenido) — el umbral de desaparición masiva reduce mucho ese riesgo, no lo elimina del todo.
- **B15 (2026-09-26, parcial):** implementada solo la mitad "Omnigold/Integral/Tomo ya no se quedan en Pendientes para siempre" — la mitad "una carpeta que NO es una serie" (autor, saga editorial, crossover en `_Omnibus/`) sigue sin tocar y queda pendiente, más cerca de B14 (contexto de carpeta) que de esto. Desviación deliberada respecto al plan original: no se creó ningún `collection_number`/`covered_range` como columna nueva ni hizo falta migración — `Issue.format`/`IssueFormat` (`OMNIBUS`, `TRADE_PAPERBACK`, etc.) ya existían en el modelo desde antes de esta historia y eran arquitectónicamente suficientes para todo lo que B15 pedía. `naming.py` captura el número de un Omnigold/Integral/Tomo/Vol como `issue_number` normal (revierte el "SIEMPRE a Pendientes" de RF-07) y lo etiqueta con un campo nuevo `ParsedComicName.edition_kind` (no persistido, solo vive durante el parseo — nunca lo usa el matcher para decidir la serie); al confirmar la asignación manual en Pendientes, `ReviewService.assign_to_series` re-parsea el nombre original del archivo (no depende de que `File.metadata_["edicion"]` ya lo tuviera guardado, para no romper archivos registrados antes de este cambio) y crea el `Issue` con el `format` correspondiente en vez del `SINGLE_ISSUE` por defecto. **Resuelto después, el 2026-09-27** (ver «Huecos fiables» en este mismo bloque): `compute_missing_issues` dejó de depender de `Issue.sort_order` —que ningún código de `main` escribía— y **el formato manda**, así que un ómnibus/tomo no contamina el hueco de la grapa. Cuando se escribió esta nota, ese filtro todavía no existía. **Segundo hueco en la misma función, señalado en la revisión retrospectiva de B7 (2026-09-27):** `_fetch_sort_orders`/`compute_missing_issues` tampoco comprueban que exista un `File` **disponible** (`is_missing=false`), así que un número cuyo único archivo desapareció del disco sigue figurando como presente en la vista de huecos **si ese `Issue` tiene `sort_order` poblado**. Conviene separar las dos cosas: es un **defecto de diseño** con efecto todavía **no generalizado en los datos actuales**, porque hoy ese campo casi nunca se escribe (el mismo motivo por el que el hueco de formato de arriba es hoy inofensivo) — no un fallo observado en producción. Es el cuarto consumidor del "¿lo tengo?": B7 cerró los otros tres (`Orchestrator._is_fulfilled`, contadores del dashboard, portada de serie) y este quedó fuera. **El punto (b) se cerró el 2026-09-27** (ver la nota «Huecos fiables» de este mismo bloque): un número cuenta como poseído solo si hay **al menos un `File` disponible** (`is_missing=false`), un tomo **no ocupa** el hueco de la grapa con el mismo número, y **la unidad se comprueba antes de restar** (AniList da capítulos, no grapas). **Sigue pendiente (a):** definir qué grapas cubre cada tomo con una **relación explícita de cobertura editorial**, nunca inferirla del número. Mientras no exista, ninguna recopilación rellena huecos de grapa, y **C6 no empieza**.
- **Huecos fiables — `compute_missing_issues` (2026-09-27, hecho):** la vista de huecos **no mentía por un bug de la consulta, sino por un campo que nadie escribe**. `compute_missing_issues()` restaba a `Series.total_issues` el conjunto de `Issue.sort_order`, y **ningún código de `main` escribe `sort_order`**: la única derivación que existió (`_derive_sort_order`, número → float con los Annuals desplazados a `x.5`) se quedó en la rama abandonada `claude/elegant-driscoll-f8b4cf` y se perdió al rehacerse B15 en la PR #1. Medido con `scripts/medicion/censo_huecos.py`: **0/18 issues con `sort_order`** en una muestra de 5 series, y con el conjunto siempre vacío `compute_missing_issues(N, ∅)` devuelve `[1..N]` — la vista presentaba como faltante todo lo catalogado. Corregido en cuatro piezas: (1) la posesión sale del **disco** — un `Issue` cuenta solo si tiene algún `File` con `is_missing=false`, el mismo criterio que los demás consumidores de "¿lo tengo?" (B7) — en vez de un campo sin poblar; (2) el **formato** manda: solo `SINGLE_ISSUE` con número entero ocupa el hueco de la grapa, así que un ómnibus/tomo #12 **no** tapa la grapa #12 (y un `Annual 1`/`1.5` tampoco, regresión de C2 conservada); (3) **la unidad se comprueba antes de restar** (bloqueo de la revisión del 2026-09-27): `total_issues` lo copia el enricher y **no siempre cuenta grapas** — AniList mapea `chapters` y sus ficheros son TOMOS, así que restarlos habría reclamado "faltan 120" para un manga completo en 5 tomos. Solo `comic_vine` está acreditada hoy (`_UNIDAD_DE_GRAPA`); AniList, Tebeosfera, GCD y las series sin fuente devuelven `computable=False` con motivo; (4) sin `total_issues` tampoco se inventa nada. `huecos_de_serie()` devuelve `Huecos(faltantes, computable, motivo)`. Medición antes/después sobre una muestra mixta: la suma ciega daba **167** huecos; el criterio nuevo da **24** entre las series con unidad acreditada y **2 pasan a "no se puede calcular"** en vez de inventar 143 — una de ellas el manga de 120 capítulos. Son "huecos calculados según el criterio nuevo", **no "huecos reales"**: no hay etiquetado independiente que lo acredite. Regresión: `tests/test_huecos_pg.py` (12 casos contra Postgres real) + los tests de API/ficha/dashboard. **El fixture de ese módulo no vacía tablas compartidas**: crea filas con UUID de prueba dentro de una transacción que **revierte** al terminar cada test, y una guarda se niega a ejecutarse si la base no lleva `test` en el nombre (antes hacía `DELETE FROM` + `commit` sobre lo que señalara `TEST_DATABASE_URL`). **Pendiente antes de C6:** la identidad editorial (qué grapas cubre cada tomo) y que `/api/series/{id}/missing` — que hoy devuelve `[]` tanto si no falta nada como si no se puede calcular — transmita `computable`/`motivo`; el porcentaje del dashboard mezcla formatos y fuentes, así que no se presenta como completitud universal.
- **Fronteras del cálculo de huecos (2026-09-27, tras cerrar #13):** la vista de huecos de grapas queda acotada a lo que puede sostener; lo demás se declara, no se finge. Tres límites explícitos: (1) `GET /api/series/{id}/missing` devuelve `[]` tanto si la serie está completa como si NO se puede calcular — **no debe usarse directamente para C6**; antes hay que transmitir `computable`/`motivo` de forma inequívoca. (2) El **porcentaje global del dashboard** sigue mezclando `Issue` de distintos formatos con la suma de `Series.total_issues` de distintas fuentes: no es completitud universal — el contador de huecos de #13 es más acotado que esa métrica. (3) `comic_vine` es la fuente admitida para esta PRIMERA regla, **no una garantía** de que toda serie suya se numere del 1 al N en grapas: antes de automatizar peticiones hay que validar identidad editorial y universo esperado. **Siguiente historia, separada de #13:** diseñar la **relación explícita entre un tomo y las grapas que cubre**, con **procedencia** y, cuando la fuente no sea fiable, **confirmación manual**. No es otra regex ni C6: es un rediseño de catálogo. Precisión de esquema (revisión de #14): la identidad actual **no distingue ediciones por `format`** — `UNIQUE(series_id, issue_number, volume)` no lo incluye; con el mismo volumen (habitualmente 1) grapa y ómnibus del mismo número chocan, pero con volúmenes distintos **sí** coexisten, y como `volume` admite `NULL` (que PostgreSQL trata como distinto) puede incluso permitir duplicados ambiguos. No se parte de «nunca pueden coexistir». Además hay que evaluar `File.covered_issue_ids` (array de UUID, inicializado vacío por importación y adopción): está ligado a una copia física, no expresa procedencia ni confirmación y no tiene las garantías relacionales de una tabla de cobertura — decidir explícitamente si sirve solo para packs/archivos físicos o migra hacia «tomo → grapas» con origen y revisión humana. Especificación en `docs/design/identidad-editorial-cobertura.md` → historia **B22**.
- **B22 (2026-09-27, en curso — estado al 2026-10-01):** sin BD local, se hizo un **censo de nombres** sobre el listado real del disco (tebeoteca y descargas): evidencia **candidata** en los nombres (rangos), no prueba. El **benchmark §13 está cerrado** (`docs/design/benchmark-identidad-editorial.md`): versiones fijadas por commit (Kapowarr `c191dda` v1.3.2, Mylar3 `cdc94a4` v0.8.3) y leídas **en su código**, incluido lo que estaba pendiente de verificar en Mylar3 — **no hay N:M archivo↔issues** (1:1 por `Location`) y su campo de cobertura (`comics.Collects`) es **raspado del HTML de Comic Vine, condicionado a una frase en inglés y sin ningún uso funcional**. Hallazgo clave: **ninguna referencia implementa cobertura editorial de verdad**, así que no hay implementación que adoptar para el tomo→grapas, solo un precedente que nadie lee. El **censo de BD** (`scripts/medicion/censo_identidad.py`) está **escrito y listo** —solo lectura, seudonimizado por defecto, documentado ya en el README de `scripts/medicion/`—; solo falta **ejecutarlo** contra la instalación real, que este entorno no tiene (verificado que funciona: se corrió contra la BD de pruebas, vacía, sin errores). El **ADR-0003** (`Propuesto`) cierra las cuatro decisiones, incorpora el benchmark y su «Próximo paso» lleva la **tabla de qué decide cada resultado**, para que esa única ejecución cierre B22 en un paso, incluido el criterio de parada: si nada es contrastable, **«posponer» es un resultado válido**. Orden: censo local agregado → revisión final del ADR → decidir migración aditiva.
- **B15 — colisión grapa↔recopilación en la asignación manual (revisión retrospectiva de la PR #1, cerrado 2026-09-26):** `ReviewService.assign_to_series` buscaba el `Issue` por `series_id`+`issue_number` sin mirar `format`; con la grapa #12 ya existente, asignar "Omnigold 12" reutilizaba esa fila `SINGLE_ISSUE` en silencio (el propio `test_issue_existente_no_toca_el_format` fijaba ese comportamiento como válido). Corregido: el `format` esperado se calcula ANTES de buscar (por `edition_kind` del nombre original, nunca por `metadata_`) y, si el `Issue` existente tiene otro `format`, se rechaza con `ColisionDeEdicion` — el archivo se queda en Pendientes con `review_motivo="número compartido entre ediciones"`, visible en la bandeja y como 409 en `/ui/pendientes/{id}/asignar`. Regresión: `test_omnigold_sobre_grapa_existente_no_enlaza` y `test_omnigold_sobre_omnigold_existente_reutiliza` (mismo número y mismo format SÍ reutiliza). **El camino automático se cerró después, de forma conservadora (2026-09-27):** `core/matcher.py::SeriesMatcher.find_issue` ya no coge la primera fila a ciegas (`LIMIT 1`): recibe el `format` esperado — que el importer deriva del `edition_kind` del nombre con el mapa compartido `models.EDITION_KIND_A_FORMAT`, el mismo que usa el camino manual — y solo enlaza cuando la evidencia alcanza: **con marcador**, si COINCIDE con exactamente una candidata; **sin marcador** (`None`), solo si hay una ÚNICA candidata **y es una grapa estándar** — una única recopilación/tomo también va a Pendientes, porque «solo hay una fila» no demuestra que ese nombre sin marcador sea ese tomo (podría ser la grapa #12, aún sin catalogar), y el camino manual rechazaría ese mismo emparejamiento. Si no se puede decidir, `_resolve` devuelve `UNSORTED` y el archivo va a Pendientes en vez de a la edición equivocada; que el número NO exista sigue siendo el hueco del enricher de siempre (no manda nada a revisión). Regresión: `TestSeriesMatcherFormatoEdicion` (9 casos: la tabla de decisión con y sin marcador, más la guarda de que el literal de grapa de `core/` coincide con el enum) + `TestFormatoEsperadoAlMatcher` (el importer traduce Omnigold→`omnibus`, y sin marcador pasa `None`, no `single_issue`). El SQL crudo de `find_issue` **sí tiene ya regresión contra Postgres real**: `tests/test_matcher_sql_pg.py` (se salta sin `TEST_DATABASE_URL`, mismo patrón que `test_title_norm.py`) cubre la búsqueda por número, el filtrado por formato y la ambigüedad con una tabla TEMP que sombrea a `issues`. Ahí se cerró además un bug **preexistente** del `#0`: la normalización de ceros era asimétrica (`ltrim(issue_number,'0') = :num`, con el parámetro ya recortado en Python) y `ltrim('0','0')` es la cadena VACÍA, así que el issue #0 no encontraba nunca su fila (`'' = '0'`); ahora se recortan los dos lados y se excluye la fila sin número. **Sigue pendiente la identidad editorial completa** — que un tomo cubra un rango de grapas, y de ahí los huecos de C6 — que no se resuelve con `Issue.format`.
- **B4 (parcial, Comic Vine + AniList + Tebeosfera):** `EnrichmentService` enruta cada serie a UNA fuente según `Series.tradition`: `american`/`british` → Comic Vine, `manga`/`manhwa`/`manhua` → AniList, `tebeo`/`franco_belgian` → Tebeosfera. Solo `fumetti` queda sin fuente todavía. AniList y Tebeosfera enriquecen solo a nivel de Serie (título/sinopsis/portada/nº de números): ninguna tiene aquí un concepto de "issue" equivalente al de Comic Vine, así que `Issue.metadata_source` nunca se pone a `anilist` ni `tebeosfera`. Nuevas columnas `series.anilist_id` (migración `0003`) y `series.tebeosfera_slug` (migración `0004`, texto — Tebeosfera identifica por slug, no por ID numérico), paralelas a `comic_vine_id`.
- **B4 (Tebeosfera, hecho):** `src/zascarr/services/tebeosfera.py` — scraping de los dos endpoints AJAX internos del buscador de tebeosfera.com (sin API oficial), portado con inspiración de [theotocopulitos/tebeosfera-scraper](https://github.com/theotocopulitos/tebeosfera-scraper) tras leer su cliente HTTP y su parser. Confirmado en vivo contra el sitio real (no solo contra el repo de referencia, que puede haber quedado desactualizado): búsquedas de "Thorgal" (BD) y "Mortadelo y Filemón" (tebeo español) devuelven resultados correctos. Se encontró y arregló un bug real solo visible probando en vivo — `lxml.text_content()` no inserta espacio donde había un `<br>`, así que "1986 a 1988<br>4 números" se leía como el número de colección "19884" en vez de "4". GCD queda como única fuente pendiente — sin API ni referencia de scraping ya identificada, a diferencia de Tebeosfera.
- **B4 (H1+H2+H3 del peer review v2, hecho):** migración `0006`, una sola pasada porque las tres tocan schema.
  - **H1 (tildes en el matcher):** `matcher.find_series` comparaba `lower(title)` crudo contra un `:norm` ya sin acentos/puntuación — un título con tilde en BD ("Nausicaä") nunca hacía exact-match con un archivo sin tilde ("Nausicaa"). Se añadió `series.title_norm` (columna generada por Postgres, `f_title_norm(title)`, espejo inmutable de `core.matcher.normalize_title`) y el matcher pasa a consultar contra ella. Verificado con una batería de títulos patológicos, no solo los de la propuesta original, encontrando y corrigiendo **dos divergencias reales** antes de aceptar la función: (1) `f_title_norm` no replicaba el paso que quita puntos de abreviación antes de la limpieza general ("S.H.I.E.L.D." salía "s h i e l d" en vez de "shield"); (2) el patrón de artículo inicial no cubría el caso de un título que ES solo el artículo ("The" a secas quedaba en "the" en vez de ""), un caso que el propio `matcher.py` ya documentaba como corrección deliberada en Python. Test de paridad automatizado en `tests/test_title_norm.py` (se salta si no hay `TEST_DATABASE_URL` — es la única prueba de la suite que toca Postgres real).
  - **H2 (caché negativa del enricher):** una serie/issue sin match en ninguna fuente entraba en el batch en CADA ciclo para siempre, quemando rate limit de APIs externas en búsquedas condenadas. Ahora `enrichment_attempted_at` (columnas nuevas en `series`/`issues`) marca el intento — con match o sin él — y solo se reintenta pasados 30 días o si nunca se intentó. Un fallo de red (excepción) NO marca el intento, para poder reintentar en el siguiente ciclo en vez de esperar 30 días.
  - **H3 (`locked_fields` mal ubicado):** por un descuido de la migración `0001`, `locked_fields` había aterrizado solo en `wishlist`, donde ningún código lo leía. Se movió a `series`/`issues`/`creators`/`characters`. Caso de uso inmediato: `ReviewService.assign_to_series` creaba el `Issue` al vuelo con `metadata_source='manual'` para proteger la asignación serie+número, pero eso bloqueaba TAMBIÉN sinopsis/portada/créditos que el enricher debería poder rellenar después. Ahora usa `locked_fields=['series_id', 'issue_number']` — protege solo la asignación, el resto del enriquecimiento sigue funcionando.
  - **Bugs de infraestructura encontrados de paso (no venían en el review), corregidos en el mismo commit:**
    - La migración `0001` **nunca había podido aplicarse contra una base de datos realmente vacía**, desde el origen del proyecto — confirmado con Postgres real (contenedor limpio, offline SQL vía `alembic upgrade head --sql` aplicado con `psql`), no una suposición. Cada `sa.Enum(...)` usado en `op.create_table()` volvía a emitir `CREATE TYPE` aunque el tipo ya se hubiera creado a mano unas líneas antes en la misma migración (cada `create_table` es un contexto de compilación DDL independiente sin memoria de eso), y además `create_type=False` no es un parámetro real del `sa.Enum` genérico de SQLAlchemy — se acepta en silencio y se ignora; hace falta `postgresql.ENUM` explícito para que surta efecto.
    - Los 6 `Enum(PythonEnum, name=...)` del ORM (`models/__init__.py`) mandaban el `.name` del enum de Python (mayúsculas, p.ej. `"AMERICAN"`) en vez del `.value` (minúsculas, `"american"`) — que es justo lo que el tipo `comic_tradition` de Postgres acepta. Ninguna escritura ORM de `tradition`/`format`/`role`/`file_format`/`status` (wishlist y reading_progress) había funcionado nunca contra una Postgres real. Corregido con `values_callable=lambda obj: [e.value for e in obj]` en los 6.
- **B5 (hecho):** `naming.py` ahora resuelve los 8 casos reales de `tests/test_naming_core.py::TestRealWorldFilenames`, incluyendo "Batman_v2_012" (guion bajo como separador), "Batman (New 52) 012 (2013)" (paréntesis de reboot no confundidos con año), "Sandman.001.(1989)" (años 19xx, no solo 20xx), "MF #001 - Safari Callejero" y "Asterix T01 - Asterix el Galo" (subtítulo tras " - ", y "T01" de BD de tomo único tratado como número, a diferencia de "Vol."/"Tomo N" que siguen siendo volumen puro).
- **B1/B3 (backend hecho, falta UI):** `Importer.scan_and_import()` ahora devuelve un `ImportReport` (importados/duplicados/sin-clasificar/errores, en líneas legibles) y corre solo como job periódico en `main.py` (antes `import_interval_minutes` era un ajuste sin usar — el importador nunca se ejecutaba solo). Cada ciclo se persiste en la nueva tabla `import_runs` (migración `0002`), idea rescatada de zascarr (`scrape_runs`) para poder responder "¿qué pasó en el ciclo de las 03:00?" desde una futura UI. Sin endpoint API todavía — eso le toca a B2/Épica C cuando haya UI que lo consuma.
- **B4 (cierre formal, ADR-0002):** declarada completa con alcance Comic Vine
  + AniList + Tebeosfera, que cubren **7 de las 9** tradiciones
  (`american`/`british` → Comic Vine; `manga`/`manhwa`/`manhua` → AniList;
  `tebeo`/`franco_belgian` → Tebeosfera). GCD queda pospuesta a post-1.0 con
  estrategia de mirror local de dumps (no API en vivo); quedan sin fuente
  `fumetti` (pospuesto a GCD) y `other` (cajón de sastre). De paso se corrigió
  que las series sin fuente se re-seleccionaran en cada ciclo acaparando el
  lote: ahora se marcan `enrichment_attempted_at` igual que las que no
  encuentran match (H2). Decisión completa en `docs/adr/0002-enricher-scope.md`.

### Épica C — "Exploro y leo mi tebeoteca"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| C0 | ~~Como coleccionista, quiero buscar una serie que NO tengo todavía (por título, en fuentes externas) y darla de alta en un clic, en vez de necesitar que ya exista una `Series` local~~ | ~~`/ui/descubrir`: busca en Tebeosfera/Comic Vine/AniList (mismos clientes que el enricher, B4) y da de alta la `Series` local con tradición/año/portada/descripción; "Añadir a deseados" reutiliza `/ui/wishlist/anadir` tal cual~~ | ✅ Hecho | L |
| C1 | ~~Como coleccionista, quiero ver mi biblioteca en una web bonita desde el móvil o el sofá, ordenada por serie, autor o nacionalidad~~ | ~~Kavita cubre lectura; ZascArr aporta el *catálogo enriquecido*: UI propia con filtros por tradición, editorial, personaje, saga~~ | ✅ Hecho | L |
| C2 | ~~Como coleccionista, quiero saber de un vistazo qué números me faltan de cada serie~~ | ~~Vista "huecos" por serie: `missing` ya existe en API; corregir el bug de `sort_order` truncado detectado en el review~~ | ✅ Hecho | M |
| C3 | Como coleccionista, quiero marcar un tebeo como leído y puntuarlo | `reading_progress` ya está en el modelo; falta exponerlo + UI | P1 | M |
| C4 | Como coleccionista, quiero listas como "Court of Owls en orden" aunque crucen varias series | `story_arc_issues.reading_order` ya soporta crossovers; falta UI de arcos | P1 | M |
| C5 | Como coleccionista, quiero leer mi catálogo enriquecido desde cualquier lector (tablet, e-reader) sin pasar por Kavita | Endpoint OPDS de solo catálogo (no de contenido) sobre los datos ya enriquecidos | P2 | M |
| C6 | Como coleccionista, quiero un botón en cada serie que detecte los números que me faltan y los ponga todos en búsqueda, para completar sagas sin ir número a número | Desde la ficha de serie (`/ui/series/{id}`, ya existe desde C2), "Completar" crea los items de wishlist correspondientes a `missing`, visibles con su estado en `/ui/wishlist` | P1 | M |
| C7 | Como coleccionista curioso, quiero que cada carpeta de serie lleve un fichero que describa su estado, para que otras herramientas lo lean sin hablar con la API | `series.json` por carpeta de serie, regenerado tras cada cambio relevante | P2 | S |

**Notas de implementación (B11, 2026-09-25):**

- **`_triage_and_match` compartido:** la lógica de dedupe por SHA256 + matcher que antes vivía solo dentro de `Importer._import_file` se extrajo a una función de módulo en `services/importer.py`, devolviendo un `_Outcome` (duplicado o `MatchResult`). `LibraryAdopter._adopt_file` la reutiliza tal cual — evita duplicar la única fuente de verdad del negocio (CLAUDE.md §3.1) entre "traer archivos nuevos" y "reconocer archivos que ya estaban".
- **Diferencia real con `Importer`:** `LibraryAdopter` nunca llama a `safe_move_async` — registra el `File` con `file_path` apuntando a donde el coleccionista lo tenía. Coherente con el mismo principio que ya protege el instalador y H5 ("nunca se re-propietan los tebeos que el usuario ya tenía").
- **Disparo único:** corre como tarea de fondo en `main.py` en cada arranque, pero `should_run()` corta enseguida si ya hay alguna `Series` en BD o si el marcador `_library_adoption_done` (fila JSONB de `runtime_settings`, fuera de la lista blanca de `/ui/ajustes` — nuevos `get_flag`/`set_flag` en `RuntimeSettingsService`) ya está puesto. Se marca hecho SIEMPRE al terminar, aunque todo quede sin clasificar — el objetivo es no repetir el escaneo completo, no garantizar matches.
- **Bug real encontrado en verificación en vivo, no en el plan original:** `ReviewService.pending_files()` filtraba por `File.file_path` empezando por `_Unsorted/` — un proxy que solo es cierto para `Importer` (que SÍ mueve ahí lo que no reconoce). Un archivo adoptado por `LibraryAdopter` se queda en su sitio real, así que con ese filtro no aparecía NUNCA en Pendientes pese a tener `issue_id IS NULL`. Se cambió el filtro a `File.metadata_["match_status"].astext == "unsorted"` (primer uso de query JSONB en el proyecto), que además es más correcto semánticamente: excluye el caso de una serie ya identificada pero sin el número exacto todavía (también `issue_id IS NULL`, pero se resuelve solo con el enricher — D1 — y no debe aparecer en Pendientes).
- **Verificación en vivo (Postgres+Redis reales, no solo los ~220 tests con FakeSession):** un CBZ colocado directamente en `library_path` se registra sin moverse; reiniciar la app no repite el escaneo; el archivo sin match aparece en `/ui/pendientes`, se asigna a mano a una serie de prueba desde la UI, y `ReviewService.assign_to_series` — sin ningún cambio — lo mueve correctamente desde su ubicación arbitraria a la ruta canónica de biblioteca.

**Notas de implementación (B12, 2026-09-25):**

- **Sin lógica de negocio nueva, solo superficie:** `SeriesMatcher.decide()` ya adjuntaba `candidates` a `MatchResult` en el caso `unsorted` (empate ambiguo o mejor candidato por debajo de `FUZZY_THRESHOLD`) — no había forma de que el coleccionista los viera. `serialize_candidates()` (nuevo, en `services/importer.py`, ordena por score descendente) los vuelca a JSON plano dentro de `File.metadata_["candidates"]`, guardado tanto por `Importer` como por `LibraryAdopter` (mismo helper, coherente con `_triage_and_match` ya compartido — B11).
- **La confirmación reutiliza el formulario de asignación ya existente**, no un endpoint nuevo: la tarjeta de `/ui/pendientes` pinta un bloque "¿Es esta serie?" con el mismo `hx-post .../asignar` que ya usaba la búsqueda manual, solo que con `series_id` precargado del candidato y `issue_number` precargado del propio `parse_comic_filename` del nombre de archivo (si lo detectó). El coleccionista sigue teniendo que pulsar "Sí, es esta" — cero autoasignación.
- **Bug de CSS encontrado en vivo:** `.btn-sugerencia { --btn-bg: var(--ok) }` no se aplicaba — perdía la cascada contra `button[type="submit"] { --btn-bg: var(--yellow) }` por especificidad (un selector de atributo pesa más que una clase sola), así que el botón salía amarillo en vez de verde pese al orden de aparición en el CSS. Corregido subiendo la especificidad (`button[type="submit"].btn-sugerencia`), verificado visualmente en el navegador antes y después.
- **Verificación en vivo (Postgres real):** serie y archivo pendiente con un candidato al 62% insertados a mano; la tarjeta mostró la sugerencia con el nombre, año, score y número precargado; un clic en "Sí, es esta" movió el archivo a la ruta canónica de biblioteca (`.../La Patrulla-X (1985)/La Patrulla-X #012.cbz`) y creó el `Issue` correspondiente — mismo camino que la asignación manual, sin código nuevo en `ReviewService`.

**Hallazgos del segundo lote de rutas reales (2026-09-25, v1.5.1):**

Una segunda biblioteca del mismo coleccionista, organizada de forma
COMPLETAMENTE distinta a la primera (jerárquica por género → editorial →
autor → obra, hasta 5 niveles, en vez de plana por tradición). Confirma
que no hay una sola manera de ordenar una tebeoteca y refuerza B14/B15:

- **La carpeta padre casi nunca es la serie en esta estructura**:
  `Cómic Español/Isaac Sanchez` (autor), `Cómic Europeo/Moebius-Giraud/
  El Incal` (autor → obra), `Superhéroes/Marvel/Avengers` (franquicia),
  `Otros Superhéroes/Arrowsmith (COMPLETO)(CRG)` (serie + tags de
  release). B14 tendrá que subir por el árbol y limpiar la carpeta, no
  quedarse con el `parent.name` a secas.
- **Duplicación masiva con sufijo `(1)`**: ~20 pares "archivo" y
  "archivo(1)", de descargar dos veces. B16 los agrupa por SHA256; se
  verificó además que el `(1)` no se cuela como número de tebeo.
- **Archivo invisible para todo el sistema**: `Las guerras silenciosas…
  CRG.cbr.zip` (doble extensión). No está en `COMIC_EXTS`, así que ni el
  importador, ni la adopción, ni la auditoría lo miran — el coleccionista
  no tiene forma de enterarse de que ese tebeo no existe para ZascArr.
  **Pendiente de decidir**: lo honesto es que la auditoría (B16) lo
  reporte como "parece un tebeo pero no lo reconozco", no ampliar
  `COMIC_EXTS` a `.zip` (metería cualquier zip de la biblioteca) ni
  abrir archivos dentro de archivos.

**Notas de implementación (B21, 2026-09-26):**

- **El origen fue una medición honesta, no una corazonada**: un banco
  estratificado de 81 rutas reales (62 de contenido único tras
  deduplicar por SHA256) mostró que 6 de 7 errores del estrato
  dominante compartían la MISMA causa — un prefijo numérico suelto sin
  punto ni guion ("42 Dreadstar...", "65 Dreadstar..."), estructuralmente
  idéntico a un título que empieza por cifra ("100 Balas..."). Ninguna
  regla local del parser puede distinguir esa forma sin inventar — es
  el mismo problema que resolvió B13 para alias, pero a nivel de
  patrón en vez de a nivel de serie concreta.
- **Contratos de producto, fijados antes de escribir código** (decisión
  explícita, no implícita en el diseño): (1) el módulo nunca crea una
  serie, solo decide si un token es o no parte del título — la serie
  la decide el matcher contra el catálogo real; (2) umbral explícito
  (`UMBRAL_EVIDENCIA = 3`) y cada pista lleva su explicación legible,
  guardada en `File.metadata_["cohorte"]` (alimenta B12); (3) no
  aprende alias de B13 por su cuenta — eso solo lo hace el humano en
  `ReviewService.assign_to_series`, y `core/cohort.py` no toca esa vía
  en absoluto; (4) determinista por ciclo — la cohorte se calcula UNA
  VEZ sobre la foto fija de `scan_and_import`/`adopt`, antes del bucle
  por archivo, así que un archivo que llega a mitad de ciclo no puede
  cambiar la clasificación de los anteriores.
- **Bug real encontrado verificando contra la biblioteca real antes de
  integrar**: la primera versión de `_firma()` convertía `[` y `]` en
  espacios pero dejaba el CONTENIDO del corchete (el crédito del
  traductor) como texto suelto. Como el crédito varía de archivo a
  archivo dentro de la misma cohorte real ("Trad por Skullpirates" vs
  "Traducido porke yo lo valgo"), fragmentaba una cohorte real de ~70
  Dreadstar en decenas de grupos de 1-2, todos por debajo del umbral.
  Corregido quitando el CONTENIDO entero de los corchetes (y los
  créditos sueltos sin corchetes, reutilizando `CREDITS_PATTERN` de
  naming.py) antes de calcular la firma.
- **Verificación en vivo (Postgres real)**: 4 archivos sintéticos con
  el patrón "NN Dreadstar (First Comics) NN USA [crédito distinto]"
  contra una serie `Dreadstar` ya creada — los 4 se registraron contra
  la serie correcta (antes habrían ido a Pendientes con 4 "series"
  `"39 Dreadstar"`/`"42 Dreadstar"`/... distintas), cada uno con su
  propio prefijo y la evidencia (4 archivos) en `metadata_["cohorte"]`.
- **Medido sobre la muestra oficial de medición (contenido único, n=62,
  cohorte calculada sobre la población completa de 762 archivos, tal
  como correría un ciclo real)**: 73%→83% clasifica solo, 76%→86%
  veraz. Detalle completo en `scripts/medicion/README.md`.

**Cobertura de `REQUISITOS_PARSER.md` (2026-09-25, v1.5.2) — 20 RF, aportados
por el coleccionista tras dos lotes de ejemplos reales:**

El documento describe un contrato de salida más rico que el actual
(`collection_number`, `subtitle`, `covered_range`, `is_pack`,
`host_issue`, `reading_order`, `arc_position`, `confidence`/
`explanation` como campos propios). No se ha adoptado ese contrato
entero — se ha implementado el efecto CORRECTO de cada RF sobre
`series`/`issue_number`/`volume`/`year` (los únicos campos que hoy
consume el matcher), añadiendo campos nuevos solo donde salían gratis
y sin ambigüedad (RF-12). Ampliar el contrato de verdad es una
decisión de arquitectura aparte, no algo a colar dentro de un lote de
fixes de regex.

| RF | Estado | Nota |
|---|---|---|
| RF-01 | 🟡 Parcial | Mojibake `nº`/`n║` y `&amp;`→`&` hechos. La expansión "Avras→Aventuras" del ejemplo depende de alias/carpeta (B14), no es parseable del nombre solo. |
| RF-02 | ✅ Hecho | `.rar`/`.7z` y doble extensión (`.cbr.zip`) reportados en `/ui/auditoria` con motivo — nunca parseados como cómic, nunca se amplía `COMIC_EXTS`. |
| RF-03 | ✅ Hecho | Dominios (`blogspot.com`, `GetComics.INFO`, `comicrel.tk`) ya se descartaban al cortar el título antes del número; verificado explícitamente con los ejemplos del RF. |
| RF-04 | ✅ Hecho | Créditos con y sin corchetes, con y sin preposición reconocida. El caso "crédito desnudo sin preposición" (`shadowdrago + lukarda` al final) no tiene marcador textual que lo distinga de un título real — queda sin resolver a propósito, mejor un título con ruido que descartar texto a ciegas. |
| RF-05 | 🟡 Parcial | El prefijo nunca contamina el número (con y sin punto, con sufijo de letra). No se guarda en un campo `reading_order` propio — se descarta, como antes; añadirlo es un cambio de contrato, ver arriba. |
| RF-06 | ⛔ No implementado | Mapeo "(Epic 01)"/"(Dreadstar 27 Ed.Forum)" a una serie/edición anfitriona — la serie real y su "host issue" son dos cosas relacionadas pero distintas que el modelo actual no tiene dónde guardar por separado. Baja frecuencia (una saga, Metamorphosis Odyssey/Dreadstar). Los archivos afectados van a Pendientes hoy — no se afirma nada falso. |
| RF-07 | ✅ Hecho — decisión tomada, ver nota abajo | |
| RF-08 | ✅ Hecho | Las 5 prohibiciones (fecha, orden de lectura, rango, número-abre-título, contador `(N)`) ya cumplidas desde v1.5.0/v1.5.1. |
| RF-09 | ✅ Hecho | Rangos con guion Y con palabra (`al`/`a`) — el segundo era un hueco real, corregido en v1.5.2. `is_pack`/`covered_range` como campos propios no implementados (ver nota de contrato). |
| RF-10 | ✅ Hecho, por otra vía | El contador `(N)` de descarga duplicada ya no se cuela como número (va dentro de un paréntesis, se limpia antes de buscar). No se guarda un flag `duplicate_download` — B16 ya detecta el duplicado real por SHA256, que es más fiable que adivinar por nombre (pilla también copias renombradas). |
| RF-11 | ✅ Hecho | `The Wicked + The Divine - 1373 IC` / `- 455 AD` ya daban el número correcto antes de este documento (verificado, no requirió cambios). |
| RF-12 | ✅ Hecho | `[P{n}N{m}]` → volumen=parte, número=n, tal cual pide el RF (sin combinarlo en un decimal, que fue mi primer instinto antes de leer el documento). |
| RF-13 | ✅ Hecho | `N de M` nunca sustituye al número real; se descarta antes de la búsqueda para que tampoco pueda colarse en un archivo futuro que no tenga "#" delante. |
| RF-14 | 🟡 Parcial | Sufijo de letra en mayúscula Y minúscula (hueco real, corregido). Sub-series con numeración propia (`Annual`, `Secret Files & Origins`, `Bonus Book`) NO se separan de la numeración madre — siguen compartiendo el campo `issue_number`; separarlas es el mismo cambio de contrato que RF-06/RF-07. `(Extras)` se limpia como ruido genérico (ya no se lee como número), sin marcarlo como variante propia. |
| RF-15 | ✅ Hecho, ya de antes | `2.0`, `[v2]`, `CORREGIDO`, `Actualizado` ya se limpiaban como ruido/tags; no aportan ni contaminan el número. |
| RF-16 | ✅ Satisfecho por diseño, sin cambio de código | "Hiroaki Samura - La Espada del Inmortal 01" sigue extrayendo `series="Hiroaki Samura"` (ambiguo, imposible de resolver solo con el nombre — ver sesión anterior). Pero el matcher NUNCA crea una serie nueva a partir de un string: solo asigna contra series YA EXISTENTES en el catálogo, así que "Hiroaki Samura" nunca aparecerá como serie real — el archivo va a Pendientes de forma segura. La garantía de RF-16 la da la arquitectura del matcher, no el parser. |
| RF-17 | ✅ Hecho, ya de antes | Símbolos (`+`, `&`) dentro del título nunca se han tratado como separador; solo `" - "` (con espacio) lo es. Crossover de doble numeración va a Pendientes (no se fusionan series) desde v1.5.0. |
| RF-18 | ⛔ No implementado | `confidence`/`explanation` como campos estructurados de salida. `ParsedComicName.confidence` existe pero es una heurística simple (v1.0), no la explicación legible que pide el RF. Cambio de contrato — ver nota arriba. |
| RF-19 | ✅ Hecho | Es el principio que ha guiado TODO este trabajo desde v1.4.8 — "preferir Pendientes a afirmar un dato falso" ya estaba en CLAUDE.md antes de este documento. |
| RF-20 | ✅ Cumplido | `parse_comic_filename` es una función pura, sin estado oculto; mismo input → mismo output siempre. |

**RF-07 — conflicto real resuelto por decisión explícita del PO
(2026-09-25):** el RF pedía que `La Patrulla X Omnigold 5` diera
`series="La Patrulla X Omnigold"`, `issue_number` vacío — el 5 es el
tomo de la recopilación, no la grapa original, y afirmar lo segundo es
mentir. Esto chocaba con `test_parse_filename_real_world_crg` (anterior
a este documento), que fijaba justo lo contrario para que el archivo
clasificara solo. Se preguntó al coleccionista con el argumento
completo de ambos lados (incluida la consecuencia real: el cálculo de
huecos/faltantes creería tener una grapa que en realidad es una
recopilación) — **decisión: adoptar RF-07**. `EDITION_NUMBER_PATTERN`
(nuevo en `naming.py`) quita el tomo de `Omnigold N`/`Integral N`/
`Edición Integral N` SIN capturarlo como `issue_number`, conservando la
palabra de la edición en el título (`"La Patrulla X Omnigold"` en vez
de solo `"La Patrulla X"` — un candidato más preciso para cuando el
coleccionista lo resuelva a mano en Pendientes). Coste medido: el ratio
del banco de 41 rutas bajó de 28/41 a 26/41 aciertos, pero **los errores
bajaron de 1 a 0** — el resultado que se buscaba. `test_parse_filename_real_world_crg`
y el test de puntos-como-separador de `La Mazmorra Integral` se
actualizaron para reflejar el nuevo comportamiento honesto. B15 (arriba)
sube a P0 porque es la pieza que revierte el aumento de Pendientes.

**Medición del ratio de acierto (2026-09-25, v1.5.0):**

Banco de 41 rutas reales del disco del coleccionista, contra PostgreSQL
real y con el catálogo de series ya creado (el mejor caso posible hoy).
Veredicto por caso: acierta / va a revisión / se equivoca.

| | antes de v1.5.0 | después |
|---|---|---|
| Acierta | 13/41 | **28/41** |
| A revisión | 27/41 | 12/41 |
| Se equivoca | 1/41 | 1/41 |

- **El único "error" resultó ser una expectativa mal puesta, no un fallo
  del código:** `La Patrulla X Omnigold 5` se asigna a la serie
  `Patrulla-X`, y la posición del proyecto (fijada en
  `test_parse_filename_real_world_crg` desde antes) es que *Omnigold es
  una edición, no una serie aparte*. Se deja como está.
- **La causa dominante de los fallos NO era el matcher, era el parser:**
  en 20 de los 27 casos que iban a revisión, el número estaba en el
  nombre pero en una forma no reconocida (`nº`, el mojibake `n║`, `123a`,
  `Especial N`, número seguido de subtítulo sin guion, separadores por
  puntos, créditos del uploader tapando el número, ruido entre
  paréntesis tras el número). Todos corregidos.
- **Lo que queda pendiente está acotado y es honesto:** packs con rango,
  listas de lectura editoriales, crossovers de doble numeración y obras
  unitarias de carpetas de autor van a Pendientes A PROPÓSITO (B15). Los
  `Tomo N` de las recopilaciones españolas esperan al campo de número de
  colección que el propio PO acotó a B15.
- El banco de medición vive fuera del repo (es un script de
  scratchpad); lo que sí queda versionado es un test de regresión por
  cada patrón, nombrado por el mecanismo del fallo.

**Notas de implementación (B16, 2026-09-25):**

- **Solo lectura, y se dice en la pantalla.** `LibraryAudit` no borra, no mueve, no renombra y no registra nada en el catálogo; `/ui/auditoria` tampoco ofrece borrar. Enseñar las rutas repetidas y dejar que el coleccionista actúe en su disco es deliberado: sugerir un borrado desde aquí sería justo la decisión irreversible que la historia existe para no tomar sola. Hay un test (`test_no_toca_ni_un_archivo_del_disco`) que compara mtimes antes y después.
- **La adopción (B11) deja de ser automática.** Hasta v1.4.8 saltaba sola en el primer arranque y el dedupe por SHA256 se quedaba con una copia **eligiendo por orden alfabético**, sin que el coleccionista supiera que había una decisión. Ahora el primer arranque AUDITA, y adoptar es un botón con el informe delante.
- **Coste en la Pi:** solo se hashean los archivos que comparten tamaño con algún otro (dos ficheros de distinto tamaño no pueden ser idénticos), y el hash va en streaming (`sha256_streaming`, extraído y compartido con el triage) en vez del `_hash_and_buffer` que carga el fichero entero en RAM. En la verificación, 19 de 21 archivos necesitaron lectura; en una biblioteca sana la proporción es mucho menor.
- **Bug grave encontrado verificando en vivo, no planificado: ningún `.cbr` tenía SHA256.** `triage()` salía antes de hashear para todo lo que no fuera `.cbz`/`.zip`, confundiendo "no se puede abrir el RAR sin unrar" (cierto) con "no se puede hashear" (falso: son los bytes del fichero). Consecuencia: **la deduplicación de B3 no funcionaba en una tebeoteca española típica**, que es mayoritariamente CBR, y lo hacía en silencio. Medido en el sandbox: antes del fix, 21 archivos registrados y 0 duplicados detectados; después, 13 registrados y 8 duplicados. El test que existía (`test_cbr_pasa_a_capa_1`) **afirmaba el bug como comportamiento correcto** — su propio comentario mostraba la confusión, y se corrigió separando las dos afirmaciones.

**Medición contra la biblioteca real (2026-09-25, origen de B14-B16):**

Se midió `parse_comic_filename` contra 44 rutas reales del disco del
coleccionista (`/media/WDElements/Tebeos`, ~2000 archivos) en vez de
contra fixtures. El resultado corrigió la hipótesis de partida, que era
"sin catálogo, casi todo caerá a Pendientes":

- **El fallo real no era quedarse corto, sino acertar en falso.** Tres
  patrones producían `(serie, número)` confiados y equivocados —
  fecha de publicación leída como grapa (`JSA (2004-08) 62` → #2004),
  prefijo de orden de lectura leído como grapa (`247.- Wonder Woman v2
  214` → #247) y rangos que se quedaban con el primero (`(144-158)` →
  #144). Corregido en v1.4.8 con tests de regresión nombrados por
  mecanismo.
- **B12 y B13 amplificaban el daño**, y eso cambió la prioridad: la
  sugerencia de un clic presentaba el número inventado como si fuera
  bueno, y el alias local aprendía el patrón. Una heurística floja se
  convertía en un dato persistente. Regla que queda de aquí: **antes de
  añadir automatismo sobre una heurística, medir la heurística contra
  datos reales** — el automatismo no crea el error, lo fija.
- **La carpeta es la señal desaprovechada** (B14): en esta biblioteca el
  coleccionista YA declaró la serie al ordenarla, y el parser trabaja
  como si no existiera.

**Registrar una biblioteca existente aunque ya haya catálogo (B11, 2026-10-05):** una instalación real quedó bloqueada antes de clasificar nada: 1.542 CBZ/CBR en la carpeta, 14 archivos registrados sin Issue, **5 series dadas de alta** y sin marcador de adopción. Con la condición de entonces (`catálogo vacío`) el estado era `CATALOGO_PREVIO` y la adopción **no se ofrecía**, así que crear unas pocas series antes de registrar impedía incorporar los archivos existentes (y no se debía borrar nada para sortearlo). Decisión **cambiada a propósito** respecto a V4 («con catálogo previo no se ofrece»): ahora es una acción **consciente**. Mecanismo: (1) `should_run()` —el disparo AUTOMÁTICO del arranque— **no cambia** (catálogo vacío); `puede_registrar()` ofrece el registro con catálogo previo, nada arranca ni escribe solo al reiniciar; (2) `inventario()` previsualiza **sin leer contenido**: archivos en disco (CBZ/CBR/otros), ya registrados, nuevos —cruzando RUTAS, no restando totales— y filas registradas cuyo archivo ya no está; (3) `adopt()` es **idempotente por ruta** (repetirlo no duplica y continúa donde se quedó), un **savepoint por archivo** (un error de BD ya no inutiliza la sesión para los siguientes), **commit por lotes** (un corte conserva lo hecho) y **el marcador solo se pone si no hubo errores** —antes se ponía «pase lo que pase» y escondía lo pendiente—; (4) corre en **segundo plano** (`services/registro_biblioteca.py`: una ejecución a la vez, progreso consultable, sin reanudarse sola, causa del fallo saneada) y la pantalla `/ui/auditoria` muestra inventario → progreso → resultado, sin anunciar éxito si hay errores y ofreciendo «Continuar»; (5) no toca series ni enlaces existentes ni mueve/renombra nada; los que no se reconocen quedan registrados en Por revisar. Verificado con Postgres y ficheros reales (CBZ y CBR, repetidos, fallo en un archivo, corte a mitad, error de BD) y en navegador real (progreso 125/335 → 286/335 → «Biblioteca registrada»). **Sigue sin resolver:** crear series a partir de las carpetas (ver `docs/design/auditoria-b14-carpetas.md`); el registro deja los archivos sin serie.

**Primer registro real (2026-10-05, instalación de producción):** el registro procesó **1.542** archivos (308 CBZ, 1.234 CBR) sin mover ni renombrar ninguno, con **0 errores, 0 «de otra ejecución», 0 «no guardados», 0 «por comprobar»** y marcador puesto. Resultado: **1.325 filas añadidas** (17 con serie sugerida pero sin `Issue` + **1.308 sin identificar**), **217 repetidos** (mismo contenido que otro ya registrado; no se registran dos veces, no se ha borrado ninguno) y **0 reenlazados**: ningún archivo coincide por contenido con las 14 filas obsoletas previas, que siguen sin tocar apuntando a rutas que ya no existen. BD tras el registro: 5 series (las mismas), 1.339 filas (14 previas + 1.325), **0 filas con `Issue`**. «Por revisar» muestra 1.308 + 14 = **1.322**. Respaldo previo hecho por el operador (el de las 18:20, no verificado aquí). **Hallazgos:**
- **Los 17 «reconocidos» NO están clasificados.** Son resultados de matching de serie (`direct`, 1,0) guardados en metadatos, sin `Issue` (`con_issue = 0`), y **no aparecen en «Por revisar»**: la bandeja filtra por `match_status = unsorted` (decisión de B11: una serie identificada sin número «se resuelve sola con el enriquecedor»). Esa decisión se **revisa**: el enriquecedor depende de fuentes externas opcionales (no hay nada que lo resuelva si no están activas) y deja a estos archivos sin ninguna superficie de revisión. En la interfaz y la documentación ya no se les llama «reconocidos y colocados» sino **«serie sugerida, falta confirmar número y edición»**.
- **Una coincidencia exacta de título no basta si la carpeta o la edición la contradicen.** Los 9 `Batman - Saga Scott Snyder 01…09` emparejaron a 1,0 con `BATMAN (tebeo, 2025)` solo porque el título extraído es «Batman» y esa es la única serie con ese nombre; la carpeta (`Batman - Saga de Scott Snyder (2019)`) apunta a otra edición. Los 8 `Absolute Batman 01…09` con `Absolute Batman` parecen correctos. No hubo daño (ningún `Issue` enlazado, ningún archivo movido), pero es un fallo de seguridad semántica: requería confirmación humana y quedó fuera de la bandeja.
- **Las 5 series existentes** (`Absolute Batman`, `BATMAN`, `BPRD`, `Far Sector`, `The DC Universe by Mike Mignola`) no incluyen ninguna de las familias grandes de la colección (Superman, Patrulla-X, Nuevos Mutantes, The Boys, Carlos Giménez): **«Por revisar» no tiene destino local al que asignarlas**. Falta el flujo guiado de alta de series (ficha en PR aparte: `docs/design/ficha-propuestas-desde-carpetas.md`).
- **Pendiente de política** (sin tocar nada): las 14 referencias obsoletas, los ~200 grupos de copias idénticas (se registró la ruta que sale primera por orden de carpeta) y las 22 piezas `.rar`/92 carpetas vacías que la auditoría ya listaba.

**Referencias obsoletas al registrar (2026-10-05, tras ver el inventario real):** en la instalación real, el inventario dio 0 registrados por ruta y «14 registrados cuyo archivo ya no está». Esas 14 filas tenían `is_missing = false` pero su ruta ya no existía (p. ej. un archivo movido con la BD sin actualizar: el defecto de la auditoría de V6a). El cotejo por hash (`_triage_and_match`, compartido por el registro y el importador de descargas) trataba toda fila **no marcada como desaparecida** como «copia presente» y descartaba como REPETIDO el archivo real: la fila seguía apuntando a la nada y el archivo quedaba sin registrar. Corrección: una copia solo cuenta como presente si **su fichero existe de verdad** (`_fichero_de_la_fila_existe`); si ninguna coincidencia tiene su fichero, se recupera (reenlaza) la fila —conserva id, Issue/serie y decisiones; cambia ruta, nombre, tamaño y hash— en lugar de descartar. **Guarda del disco:** solo se afirma que falta si el primer ancestro existente de la ruta vieja está en el MISMO sistema de ficheros que el archivo leído; si cuelga de otro disco (puede estar desmontado) o no se puede consultar, se conserva el comportamiento de siempre. La acreditación de un commit incierto reconoce ahora el estado previo completo (ruta e `is_missing`) de una fila reenlazada. No se borra ni se toca a mano ninguna fila de producción.

**Notas de implementación (B13, 2026-09-25):**

- **Tabla `local_aliases`** (migración `0012`): `pattern_norm` (único) → `series_id` (FK `ON DELETE CASCADE` — si se borra la serie, sus alias mueren con ella, sin fila huérfana). `pattern_norm` es `core.matcher.normalize_title()` del título que `naming.py` extrajo del NOMBRE DE ARCHIVO ORIGINAL, no un regex ni texto libre — mismo criterio de normalización que ya usa `find_series` para el exacto, así que un alias aprendido de "La Patrulla X Omnigold 12" también dispara para "LA PATRULLA X OMNIGOLD 15" sin trabajo extra.
- **Quién aprende y cuándo:** `ReviewService._learn_alias()`, llamado al final de `assign_to_series()` — toda asignación manual desde Pendientes es por construcción una corrección (el archivo solo llega a esa bandeja porque el matcher YA falló solo), así que no hace falta distinguir "esto era una corrección real" de "esto era obvio": se aprende siempre. Una corrección posterior sobre el mismo patrón hacia otra serie **sustituye** el alias existente (upsert), no lo duplica — el criterio es "la corrección más reciente del coleccionista manda".
- **Quién consulta y cuándo:** `SeriesMatcher.decide()`, justo tras extraer título+número (capas 0/1) y ANTES de `find_series()` (capa 2, fuzzy/pg_trgm) — si hay alias, ni se ejecuta la query de fuzzy. La cola común (buscar el `Issue` exacto y componer el `MatchResult`) se extrajo a `SeriesMatcher._resolve()`, compartida entre el camino normal y el de alias para no duplicar la lógica de "issue no encontrado: nota para el enricher".
- **Test de la trampa real:** capturar `file.file_name` ANTES de que `assign_to_series` lo reescriba con el nombre canónico (`final_dest.name`) — si se lee después, `naming.py` intentaría reparsear "La Patrulla-X #012.cbz" (ya renombrado y limpio) en vez del nombre sucio original que de verdad causó el fallo del matcher, y el alias aprendido sería inútil para el PRÓXIMO archivo con el patrón sucio real.
- **Verificación en vivo (Postgres real):** serie "X-Men Omnigold" sin ningún alias — `decide()` sobre "la patrulla x omnigold 12" da `unsorted` (el fuzzy no la encuentra, como se espera: son títulos distintos a propósito para la prueba). Tras insertar el alias `patrulla x omnigold → X-Men Omnigold` (equivalente a lo que haría `_learn_alias`), el mismo `decide()` da `direct` sobre la serie correcta, sin tocar `find_series()`.

**Notas de implementación (C0, 2026-09-25):**

- **`DiscoveryService` (`services/discovery.py`) reutiliza los tres clientes del enricher tal cual** (`ComicVineClient`/`AniListClient`/`TebeosferaClient`) — solo para BUSCAR, nunca para descargar contenido; ninguno de los tres se modificó. Búsqueda concurrente (`asyncio.gather`) con tolerancia a fallos: si una fuente cae (probado con Tebeosfera lanzando una excepción real en el test), las otras dos siguen devolviendo resultados — mismo criterio que ya documenta enricher.py.
- **Comic Vine se salta la petición entera si `comicvine_api_key` está vacío** (el caso por defecto, integración opt-in como todas las demás) en vez de lanzar una petición condenada al 401.
- **`get_or_create_series` nunca duplica**: busca primero por la columna de identidad externa (`comic_vine_id`/`anilist_id`/`tebeosfera_slug`, UNIQUE en el esquema) y reutiliza la fila si ya existe — cubre tanto "buscar dos veces lo mismo" como "esta serie ya se dio de alta por otra vía". `tebeosfera_slug` se trata como texto siempre (nunca `int()`), a diferencia de los IDs numéricos de Comic Vine/AniList.
- **La tradición que devuelve cada fuente es solo un punto de partida editable**, nunca una asignación definitiva: Comic Vine también indexa `BRITISH`, Tebeosfera también indexa `FRANCO_BELGIAN` — el `<select>` en `/ui/descubrir` viene preseleccionado con la mejor suposición pero el coleccionista lo corrige antes de confirmar.
- **Dar de alta una serie NO exige aceptación legal** (`/ui/descubrir/crear` no lleva `require_legal_acknowledgment`, con test explícito de regresión): catalogar metadatos no es una acción de riesgo. "Añadir a deseados" desde la confirmación reutiliza **tal cual** el endpoint `/ui/wishlist/anadir` ya existente (con su gate legal intacto) — cero lógica nueva duplicada para esa parte.
- **Sin hotlinking en los resultados de búsqueda** (regla permanente, §3.1.4): las tarjetas de candidatos son solo texto (fuente/título/año), sin `<img>` a la portada externa — sería un proxy de imagen arbitrario antes de que exista una `Series`, superficie nueva no justificada. En cuanto se crea la serie, la portada se sirve por el cascade ya existente (`/ui/series/{id}/portada`, cachea `cover_url` localmente en la primera petición) sin código nuevo.
- **Verificado en vivo, no solo con fixtures**: Postgres + Redis reales, búsqueda real contra Tebeosfera (sin API key) devolviendo 10 ediciones reales de "Thorgal"; alta de una serie confirmada en la fila de `series` de Postgres; la misma serie visible de inmediato en la búsqueda LOCAL de `/ui/wishlist` (cierra el círculo D1↔C0); "Añadir a deseados" redirige correctamente a `/ui/legal` sin aceptación previa.

**Notas de implementación (ampliación de C0, 2026-09-25 — enlace a la fuente + GCD):**

- **Enlace a la ficha original en cada resultado** (`DiscoveryResult.site_url`): reportado tras la primera prueba en vivo — 10 ediciones de "Thorgal" sin forma de saber cuál era cuál. Enlace de texto de salida (pestaña nueva), nunca hotlinking de imagen. Comic Vine añade `site_detail_url` al `field_list`; AniList se construye con su patrón estable; Tebeosfera reutiliza el `href` ya extraído del HTML del buscador.
- **GCD (Grand Comics Database) añadida como cuarta fuente**, solo para descubrimiento (C0) — **reabre parcialmente ADR-0002** (ver actualización fechada en `docs/adr/0002-enricher-scope.md`): su premisa de 2026-09-23 ("no existe API pública de GCD") ya no es cierta, verificado en vivo el 2026-09-25 — GCD publica una API REST anónima en `/api/`, con los datos bajo CC BY-SA 4.0 (atribución + enlace de vuelta, ya cumplido por `site_url`). No cambia el alcance del enricher (B4 sigue cerrado tal cual: la API de búsqueda de GCD no trae sinopsis ni portada a nivel de serie, solo datos bibliográficos). Nueva columna `series.gcd_id` (migración `0010`), `services/gcd.py`, fila añadida a la tabla de fuentes de `LEGAL.md`.
  - **Bug real encontrado y corregido antes de dar por bueno el cliente**: sin la cabecera `Accept: application/json`, Django REST Framework (lo que usa GCD) devuelve su interfaz HTML navegable en vez de JSON — `r.json()` reventaba con `Expecting value: line 5 column 1`. Confirmado con `curl` real contra `comics.org/api/` reproduciendo el fallo antes de aplicar el fix. Parseo envuelto en su propio `try/except ValueError` además del de red, mismo criterio que Tebeosfera.
  - GCD indexa por país/idioma, no por tradición ZascArr: mapeo best-effort (`GCDResult.tradition_guess`) igual de editable que las otras tres fuentes — nunca una asignación definitiva.

**Notas de implementación (ampliación de C0, 2026-09-25 — tarjetas con portada):**

- **Portadas reales en los resultados de búsqueda**, pedido con una captura de referencia estilo Sonarr: nuevo proxy `/ui/descubrir/portada`, nunca hotlinking directo — valida el host contra una lista blanca por fuente (sin ella sería un proxy abierto de imágenes arbitrarias, SSRF real) y cachea en disco por hash de la URL (`utils/cover.py::fetch_and_cache_cover` reutilizado tal cual, sin código de descarga/resize nuevo). Tras crear la serie, la confirmación pasa a usar el cascade de portadas ya existente (`/ui/series/{id}/portada`) en vez de este proxy.
- **Bug de entorno de prueba, no de la app** encontrado verificando en vivo: las portadas fallaban con `cover.resize_failed` porque `COVERS_CACHE_PATH` por defecto es `/config/covers`, una ruta que solo existe DENTRO del contenedor Docker real — al correr la app directamente en el sandbox (fuera de Docker) para verificar, hacía falta apuntar esa variable a una carpeta real. Documentado aquí para no repetir la confusión.
- **Bug real encontrado de paso**: AniList deja `<br>` literal en la sinopsis pese a pedir `description(asHtml: false)` — visible en la propia captura que motivó este cambio. Limpiado en el origen (`services/anilist.py::_clean_description`), con test de regresión.

**Notas de implementación (Fase 6 / UI web):**

- **Decisión de arquitectura:** ver [`docs/adr/0001-ui-stack.md`](adr/0001-ui-stack.md) — Jinja2 servido por el propio FastAPI + HTMX vendorizado (no CDN), sin SPA ni build de Node. Primer ADR del repo; las decisiones previas (PostgreSQL, enrutado del enricher) no quedaron documentadas como ADR retroactivamente.
- **Esqueleto:** `src/zascarr/web/` (router `/ui`, `Jinja2Templates`, layout `base.html` con nav), `src/zascarr/static/vendor/htmx.min.js` (v4.0.0, verificado en un navegador real antes de vendorizarlo), `src/zascarr/static/web.css`. El dashboard de E1 se queda como está por ahora (página autocontenida que funciona); se migra a este layout cuando exista otra pantalla más con la que compartir cabecera.
- **B2 (hecho), primera pantalla real:** `src/zascarr/web/pendientes.py` — bandeja en `/ui/pendientes` sobre `ReviewService` (`src/zascarr/services/review.py`). Dos acciones, no tres: "es esta serie" (busca y asigna, creando el `Issue` al vuelo si el número no existe — marcado `metadata_source='manual'`, igual que el `File`, así el enricher nunca lo toca) e "ignorar" (nueva columna `files.review_dismissed`, migración `0005`). "Ninguna" se fusionó con "ignorar" — sin candidatos del matcher persistidos en BD, mantenerlas separadas no aportaba distinción real (ver hilo de decisión). Miniaturas extraídas bajo demanda de la primera página del CBZ y redimensionadas con Pillow (`src/zascarr/utils/cover.py`); CBR se queda sin miniatura a propósito (necesitaría unrar). Verificado en un navegador real de principio a fin: listar, buscar, asignar (con movimiento de archivo real a disco, confirmado con `find`), ignorar, y que ambas acciones persisten tras recargar. Nota de la propia verificación: el disparo `hx-trigger="keyup changed"` no siempre reaccionaba a la escritura simulada por la herramienta de automatización del navegador (sí a un evento `keyup` real) — probable limitación de la herramienta, no del código, pero queda anotado por si un usuario real reporta que la búsqueda no responde al teclear.
- **C2 (hecho):** el bug de `sort_order` truncado era real —
  `int(1.5) == 1` hacía que un Annual/especial "cubriera" el hueco del
  número entero adyacente aunque ese número no existiera de verdad.
  Extraído `compute_missing_issues()` (`api/series.py`) como función
  compartida: un hueco `i` solo se da por cubierto si existe un `Issue`
  cuyo `sort_order` es EXACTAMENTE `float(i)`, no su truncamiento. Usada
  tanto por `GET /api/series/{id}/missing` como por la nueva
  `GET /ui/series/{id}` (ficha de serie **mínima**: solo números
  presentes/ausentes, sin pósters/filtros/navegación — eso es trabajo de
  C1, que sigue sin construir; esta pantalla se ampliará o rehará
  cuando llegue, no es el diseño final, y por eso no tiene enlace en el
  topnav — no hay desde dónde navegar a ella todavía). Test de
  regresión con `sort_order=1.5` en `tests/test_api_series.py` y
  `tests/test_web_series.py`. Verificado en un navegador real contra
  Postgres real con el caso exacto del bug: una serie con SOLO un
  Annual `sort_order=1.5` (sin el `1.0`) muestra correctamente `#1` como
  pendiente — con el código anterior se habría dado por presente.
- **C1 (hecho):** `/ui/biblioteca` — primera pantalla de navegación real
  de la biblioteca (hasta ahora solo había pantallas de un único
  propósito). Filtros por tradición/editorial (dropdown) y
  personaje/saga (búsqueda-y-navegación, universo demasiado grande para
  un dropdown); clic en una tarjeta lleva a la ficha de C2, que por fin
  tiene desde dónde ser alcanzada (gana portada + editorial + géneros +
  enlace de vuelta). `SeriesService` (`services/series.py`) centraliza
  el listado/filtrado — usado tanto por la API JSON como por la UI, con
  JOIN explícito (no `.any()` anidado) para personaje/saga, verificado
  con Postgres real (no solo `FakeSession`, que no detecta un JOIN M:N
  mal construido): `Series → Issue → issue_characters`/`StoryArcIssue`.
  - **Portadas — cascada unificada de 3 niveles**: (1) primera página
    del CBZ ya importado más antiguo, (2) `cover_url` externo descargado
    y cacheado una sola vez, (3) placeholder si no hay ninguna — nunca
    se cachea una ausencia. Todo el resultado (venga de CBZ o de fuente
    externa) se escribe a un único fichero en disco
    (`covers_cache_path/{series_id}.jpg`), así que una segunda petición
    no vuelve a tocar ni el CBZ ni la red. **Cierra M4** de paso (el
    thumbnail de B2 nació sin cabeceras de caché): `cached_image_response`
    compartida entre `pendientes.py` y `series.py` (304 con `If-None-Match`,
    `Cache-Control: private, max-age=86400`).
  - **Bug real encontrado probando en vivo** (no algo que un mock hubiera
    revelado): `httpx.AsyncClient` no sigue redirecciones por defecto, y
    tanto `picsum.photos` (usado para verificar esto) como CDNs reales de
    portadas devuelven 302 con normalidad — sin `follow_redirects=True`,
    `raise_for_status()` trataba el redirect como fallo y ninguna portada
    externa se descargaba nunca. Corregido y reverificado en vivo.
  - **Bug real encontrado probando en un navegador real**: los campos
    ocultos del formulario de filtros (`publisher_id`/`character_id`/
    `story_arc_id`) llegan como `""` cuando no hay selección, no
    ausentes de la query string — un parámetro `UUID | None` de FastAPI
    no acepta `""` y daba 422 en cuanto se tocaba cualquier otro filtro.
    Corregido convirtiendo a mano (`_uuid_or_none`) y añadido como test
    de regresión explícito (ningún test con query string vacía lo había
    cubierto hasta entonces).
  - Trabajo bloqueante (zipfile, Pillow, descarga, disco) siempre en
    `asyncio.to_thread`/`httpx.AsyncClient`, con un semáforo
    (`asyncio.Semaphore(2)`) limitando descargas externas concurrentes —
    no disparar una ráfaga al CDN cuando una rejilla entera carga en frío.
  - **Deuda registrada, no resuelta aquí**: la caché de portada en disco
    no se invalida nunca automáticamente — si una serie cachea primero
    la externa y más tarde llega un archivo real, o si el enricher
    cambia de fuente, el fichero viejo se sirve indefinidamente hasta
    que alguien lo borre a mano. Aceptable para una biblioteca personal
    de un solo usuario; revisar si algún día se vuelve confuso en la
    práctica.
  - Nuevo volumen Docker + `mkdir` en `bootstrap.sh` para
    `covers_cache_path` (`/mnt/nvme/tebeoteca/config/covers`, mismo
    patrón que `config/{postgres,redis}`).

### Épica D — "El sistema busca lo que me falta"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| D1 | ~~Como coleccionista, quiero marcar "quiero esta serie" y olvidarme: el sistema la encuentra y la añade~~ | ~~Wishlist → orchestrator → Transmission/aMule → import; visible como "Buscando... Descargando... En tu biblioteca" en la UI, con reintento automático de candidato y de búsqueda~~ | ✅ Hecho | L |
| D2 | Como coleccionista, quiero elegir "solo CBZ de calidad" o "acepto escaneos" sin entender qué es un quality profile | Selector de 3 opciones legibles ("solo lo mejor / equilibrado / lo que haya"); mapea a `quality_tier` interno | P1 | M |
| D3 | Como coleccionista, quiero que si sale una edición mejor de algo que ya tengo, el sistema me la ofrezca | Lógica de upgrade sobre `quality_tier`; la UI propone, no sustituye sin confirmar | P1 | M |
| D4 | ~~Como coleccionista, quiero que el sistema me avise si está descargando sin VPN sin que se pare todo~~ | ~~Warning del healthcheck visible como aviso en UI + log del orchestrator (decisión ya acordada, ver fix C2)~~ | ✅ Hecho (vía E1) | S |
| D5 | Como coleccionista, quiero ver lo que sale esta semana —tanto grapa americana como novedades de Norma/ECC/Panini España— de las series que sigo, para no perderme lanzamientos | Vista de novedades agrupada por semana y filtrable por editorial; doble track por tradición (Comic Vine para fechas futuras USA, scrapers editoriales españoles para el resto); cada novedad se cruza contra wishlist/series monitorizadas y queda marcada "Te interesa" | P2 | L |
| D6 | Como coleccionista, quiero agrupar series en colecciones ("grapas en curso", "clásicos Bruguera") y que cada colección decida si se busca, con qué fuentes y con qué calidad | Tabla `collections` con políticas tri-estado (include/exclude/unset) de auto-búsqueda aplicadas en el orquestador; una serie sin colección conserva el comportamiento actual | P1 | M |
| D7 | Como coleccionista, quiero pedir un arco argumental entero aunque cruce varias series, en orden de lectura | Wishlist por `story_arc` que genera items por issue respetando `reading_order` | P2 | L |
| D8 | ~~Como coleccionista, quiero decidir por serie si quiero todos los números, solo los que me faltan o solo los futuros, para no pedir contenido que no quiero~~ | ~~Campo `wishlist_policy` (`ninguno`/`faltantes`/`futuros`/`todos`) por serie, leído por `Orchestrator.process_wishlist` antes de generar candidatos a buscar; migración deja `ninguno` como valor seguro en series existentes. Requiere C0.~~ **Cómo se cerró (2026-09-30):** migración `0015` (`Series.wishlist_policy`, `Wishlist.origen`/`numero`, estado `retirado` y índice único parcial `(series_id, numero)` solo para items de política). El predicado único es `services/politica.py::querer_de_serie` («números que la política quiere ahora») y lo consumen la generación, la retirada y la ficha de serie, así que no pueden divergir. La generación está acotada por ciclo (`orchestrator_politica_lote`) y repartida en rondas entre series; usa `INSERT ... ON CONFLICT ... DO UPDATE` porque el índice no mira el estado, y **solo reactiva `retirado`/`imported`** (un `FAILED` conserva su motivo de D9 y lo reintenta `process_wishlist`; un `DOWNLOADED` espera al importador). La retirada es un `UPDATE` atómico por serie, solo `WANTED`/`FAILED` y solo `origen='politica'`, y cubre la política que pasa a `ninguno`, el número que llega a disco y el item manual de serie que aparece después; se aplica al guardar (la generación espera al ciclo). `futuros`/`todos`/`null` se rechazan con 422 y el selector los oculta o los deshabilita con su motivo. **Límites abiertos, a medir con la biblioteca real en la primera instalación:** arranque en frío de los alias (B13), hipótesis de series catalogadas en inglés con releases en español, y rango `1..total_issues` cuando una serie arranca en el #0. Reservado para más adelante: `todos` espera a D3 (criterio de cierre) y `futuros` a que la fuente publique números no salidos. | ✅ Hecho | M |
| D9 | ~~Como coleccionista, quiero ver POR QUÉ una búsqueda no se ejecutó o falló, en vez de un wishlist que simplemente no avanza~~ | ~~Migración `0013`: `Wishlist.last_error` (texto en español, sin timestamp propio — se correlaciona con `last_searched_at`, ya existente). El orquestador distingue: sin fuente activa, fuente inaccesible (Prowlarr con error/timeout), sin resultados, candidato encontrado pero ningún backend de descarga activo, cliente de descarga inaccesible, error inesperado. El aviso legal pendiente es aparte, un banner GLOBAL en `/ui/wishlist` (no un `last_error` por fila, ya que el gate es un estado del sistema, no de un item concreto). Nunca expone excepciones/URLs/cuerpos HTTP — solo la causa en español y la acción posible~~ | ✅ Hecho | S |
| D10 | ~~Como coleccionista, quiero lanzar una búsqueda manual y elegir yo el candidato antes de que se envíe a descargar, para mantener el control~~ | ~~Botón "Buscar ahora" en cada fila de la wishlist (gateado por aceptación legal): reutiliza el mismo pipeline de búsqueda/ranking/filtro-por-backend del ciclo automático (`Orchestrator._search_and_rank`, extraído de `_process_item`), pero se detiene ANTES de enviar nada — muestra fuente/formato/tamaño/seeders de cada candidato con un botón "Descargar este" por fila. El candidato viaja firmado por el servidor (token HMAC ligado al `item_id`, caduca a los 10 minutos — `crear_token_candidato`/`verificar_token_candidato`), nunca reconstruido desde campos sueltos del formulario; solo se envía desde un estado accionable (`WANTED`/`FAILED`), reclamado con un `UPDATE` atómico antes de tocar la red, así que ni un token reenviado tras confirmar ni dos confirmaciones concurrentes duplican el envío. Cancelar no deja nada a medias: no se toca Transmission/aMule hasta confirmar uno concreto~~ | ✅ Hecho | M |
| D11 | ~~Como coleccionista, quiero configurar Comic Vine/Prowlarr/Transmission/aMule desde la UI con un botón de "probar conexión", en vez de editar `.env` a mano~~ | ~~`/ui/ajustes`: un formulario por integración, con "Guardar" (aplica al instante, sin reiniciar) y "Probar conexión" (petición real con lo que hay en el formulario, guardado o no); secretos nunca se devuelven en claro~~ | ✅ Hecho | M |

### Épica E — "Confío en el sistema"

| ID | Historia | Aceptación | P | Est |
|---|---|---|---|---|
| E1 | ~~Como coleccionista, quiero una pantalla de estado con semáforos ("todo bien / atención: sin VPN / error: disco lleno")~~ | ~~Dashboard sobre `/api/health` con iconos y textos en español, no JSON~~ | ✅ Hecho | M |
| E2 | ~~Como coleccionista, quiero que haya copias de seguridad automáticas sin configurar nada por mi parte~~ | ~~Cron de `pg_dump` a segundo disco (el backup actual al mismo disco del dato era hallazgo del review)~~ | ✅ Hecho | S |
| E3 | ~~Como coleccionista, quiero un botón "restaurar copia" si algo sale mal~~ | ~~Script de restore documentado y probado (el test del backup no es hacerlo, es restaurarlo)~~ | ✅ Hecho | M |
| E4 | Como coleccionista, quiero un aviso al móvil cuando una descarga se importa, para no estar mirando el dashboard | Webhook configurable (Gotify/ntfy/Telegram/URL genérica) al completar descarga+import; desactivado por defecto | ✅ Hecho | S |

- **E4 (2026-09-28, hecho):** webhook de importación con **entrega de mejor esfuerzo** (decisión explícita de la ficha: sin cola ni reintentos persistentes, que exigirían otro alcance). `services/notifier.py` soporta `generic`/`gotify`/`ntfy`/`telegram`, apagado por defecto (`webhook_enabled`), configurable desde `/ui/ajustes` reutilizando D11 (grupo `avisos`; `webhook_token` en `SECRET_FIELDS`). `main.py::_ejecutar_ciclo_y_avisar` avisa **después del `commit`** y solo con `report.imported` (nunca adopción ni duplicados); un fallo del webhook se registra sin URL ni token y no revierte la importación. Ficha en `docs/design/benchmark-E4-avisos.md`. Regresión: `tests/test_notifier.py` (receptor falso + orden commit/rollback).
| E5 | Como coleccionista que reporta un fallo, quiero un botón en el dashboard que genere un fichero con los logs recientes, sin tocar la terminal | Botón "Descargar logs" en el dashboard, sin acceso a shell | P2 | S |
| E6 | Como administrador, quiero que `/api/health` distinga "sin conexión con Postgres" de "conectado pero sin migrar" de "esquema incompatible" de "listo", en vez de un `database: ok/error` binario, para resolver una instalación rota sin leer tracebacks | Nuevos valores de `checks.database`: `unreachable` (no conecta), `migration_required` (conecta pero `alembic_version` no está en `head` — comparar revisión actual contra `head` de `alembic/versions`), `schema_incompatible` (conecta, migrado, pero falta una tabla de dominio esperada — señal de una restauración/rollback a medias), `ok`. Cada estado con su texto y acción en español en `/estado`; ninguna vista de `/ui/*` debe devolver un 500 crudo por tabla ausente — degradar con el mismo diagnóstico en vez de reventar | ✅ Hecho | S |
| E7 | Como coleccionista, quiero saber si GCD puede **enriquecer** (no solo buscar) mis tebeos españoles, con datos reales de sus fichas, antes de conectar el enricher | **Evaluación, no implementación.** Con un caso real (Absolute Batman 2025, Panini España): contrastar ficha de serie, resumen de serie y ficha de número contra las **respuestas reales de la API** de GCD (endpoints separados; no inferirlas de la página web) — qué campos de la edición española (editorial, fechas, formato, créditos) se pueden incorporar, si la **portada es recuperable como URL de la API** y con qué rate limit. **Criterio de parada:** si no hay portada ni datos por número aprovechables, GCD **no** entra para portadas ni números; la evaluación puede recomendar igualmente usar sus campos **de serie** de la edición española (editorial, fechas, formato), que son valor propio. No añade GCD a `EnrichmentService`. | ✅ Hecho | S |

- **E7 (2026-09-28, abierta):** corrección de B8 — GCD **sí** faltaba en el control de fuentes. Se añadió el interruptor `gcd_enabled` (default `True`, grupo `fuentes` de D11), aplicado a `DiscoveryService.search` (apagado = cero consultas a GCD), etiquetado en Ajustes como «GCD — solo Descubrir» y reflejado en `/api/health`. La ampliación al **enricher** es esta evaluación aparte: el cliente actual solo documenta búsqueda de series y la portada vista en la web no prueba que la API devuelva una URL de imagen (ver ADR-0002, que se revisará con el resultado).
- **E7 — método y casos de prueba (2026-09-28):** investigar con el **buscador avanzado** de GCD (<https://www.comics.org/search/advanced/> — nombre, editorial, país, idioma, año, número, ISBN/código de barras; incluye «Covers for Issues») para **identificar la edición española**, y después **verificar paridad con la API** (<https://www.comics.org/api/schema/swagger-ui/>) en vez de automatizar el formulario HTML. Casos: **(1) serie** *Absolute Batman*, inicio 2025, país Spain, idioma Spanish, editorial Panini España, contrastada con la edición USA (¿los filtros identifican la edición correcta de forma fiable?); **(2) número** #8 de esa serie — fecha, créditos, edición original relacionada y portada; **(3) paridad API** — tomar los IDs de serie/número hallados en la web y consultar sus endpoints, **midiendo qué campos e imágenes devuelven de verdad** (que la web muestre portada no prueba que la API entregue una URL utilizable). El buscador avanzado es experimental; una herramienta de terceros señala que la búsqueda **por API** no filtra por idioma — **verificar esa limitación contra la API actual** antes de adoptarla como conclusión.
- **E7 — modelo de datos a estudiar (2026-09-28, aportado en revisión):** lo más valioso de GCD no es la portada, es su **modelo**: representa una *edición concreta* y sus números catalogados, y **distingue variantes de portada**. Un solo contador mezcla cuatro conceptos que hay que separar: **(1) edición identificada** (¿la serie de BOOM! 2026 o una edición española posterior?); **(2) números catalogados/publicados** (¿qué números conoce la fuente y de qué edición?); **(3) total previsto** (¿evidencia de que acaba en el #4, o solo cuatro publicados hasta hoy?); **(4) ejemplares poseídos** (los del usuario con archivo disponible, sin contar variantes como números extra). Estudiar en [gcd-django](https://github.com/GrandComicsDatabase/gcd-django): `apps/gcd/models/series.py`, `apps/gcd/models/issue.py`, `scripts/reset_stats.py` y `apps/api/serializers.py` (los mantenedores indican que los modelos Django son la referencia del esquema). **Dos matices que corrigen lo dicho antes:** `Series.issue_count` es un recuento **mantenido por GCD** (su recálculo excluye variantes normales de la misma serie, pero contempla variantes ligadas a otra serie — hay una incidencia sobre inconsistencias al mover variantes), así que **no es por sí mismo un «total previsto»**; y el serializador de `Issue` declara `variant_of` y `cover`, lo que hace **más prometedor** el estudio de portadas que sugería el cliente de búsqueda actual, aunque ver el campo no confirma qué devuelve el endpoint público. **Prueba decisiva:** consultar respuestas **reales** de la serie `236622` y de un número — comparar `issue_count`, la lista de **números base**, las **variantes** y el campo `cover`, sin equiparar «catalogados» con «planificados» ni trasladar el contador a los huecos de ZascArr (fuente, edición, unidad del recuento y fecha de observación explícitas antes de tocar C6). Compararlo con los #1–#4 de la miniserie sería una ficha §13 de modelo de datos, no solo de portada.
- **E7 (2026-09-28, evaluación hecha):** ficha en `docs/design/benchmark-E7-gcd-api.md`, con respuestas **reales** de la API (`Accept: application/json`), no del serializador ni de la web. Resultado por capacidad: **edición ✅** (`language`/`country`/`publisher`/`publishing_format` distinguen Panini España `224764` de DC `216143`); **números ⚠️** (`active_issues` lista registros y `variant_of` distingue base de variante, pero **no existe `issue_count`** en la API y las descripciones no son fiables — la miniserie de 4 tiene **37 registros**, y el truco de «sin corchete» da 3/14/**0** según la serie); **portadas ❌** (el campo `cover` trae URL real, pero devuelve **HTTP 403 tanto en `GET` como en `HEAD`**, con `Content-Type: text/html`, UA normal, UA de navegador, `Referer` y URL sin doble barra; el CC BY-SA 4.0 cubre los **datos**, no las imágenes, cuyos derechos GCD reserva a sus titulares); **huecos ❌** (sin recuento acreditado y con metadatos de número vacíos en la edición española). **Conclusión acotada al resultado:** **no** usar GCD para **portadas ni huecos**, **no** integrarlo ahora en el enricher existente, y **conservar como candidata separada** la identificación/enriquecimiento de **edición** (punto 1), que sí queda acreditado; ningún recuento pasa a `Series.total_issues` ni habilita C6.

- **E6 (2026-09-28, hecho):** `checks.database` pasa de `ok/error` binario a cuatro estados — `unreachable` / `migration_required` / `schema_incompatible` / `ok` — con detalle y acción en español en `/estado`. El `head` se calcula leyendo `alembic/versions` **sin importar el paquete `alembic`** (el directorio `alembic/` del repo sombrea al paquete instalado). Un `undefined_table` (SQLSTATE 42P01) en `/ui/*` degrada a 503 con enlace a `/estado`, no a un 500 crudo. Regresión: `tests/test_health_db_pg.py` (5 casos contra Postgres real, esquema temporal no destructivo) + `tests/test_health.py` (handler anti-500 y head).

**Nota (A8, 2026-09-26):** al retomar el backlog tras D9, A8 ya estaba resuelto desde antes — cerrado el 2026-09-25 (commit `26da7bc`, un día antes del arco B15/B20/D9 de esta sesión) y la fila del backlog simplemente no se había actualizado a "Hecho". Sin código nuevo: solo se verificó que ni `bootstrap.sh` ni `scripts/update.sh` tocan pip/Python en el host en ningún punto (ambos usan `docker compose run --rm zascarr alembic upgrade head`) y se cerró la fila con la nota del mecanismo, tal como pide CLAUDE.md §9.

**Notas de implementación (A4, 2026-09-26):**

- **La biblioteca nunca se toca, con o sin `--purge`** — a propósito no hay ninguna opción para borrarla, ni siquiera "borrar todo de verdad": quien quiera hacer eso lo hace él mismo a mano. Mismo principio A3 del instalador, aplicado del lado de salida.
- **Bug real encontrado verificando en vivo (Docker real, no solo lectura del script)**: el directorio de datos de Postgres lo crea el propio proceso del contenedor con permisos `700` (buena práctica de Postgres, no un descuido), propiedad de su usuario interno — un `rm -rf` del usuario del host no puede tocarlo aunque sea dueño del resto de `ZASCARR_DATA_DIR`. La primera versión del script silenciaba el error (`|| true`) y reportaba "datos borrados" sin haberlo estado de verdad para Postgres en concreto. Corregido borrando desde DENTRO de un contenedor con la misma imagen `postgres:15-alpine` que ya usa `docker-compose.yml` (nunca hace falta descargar nada nuevo: ya está en caché de cualquier instalación real) — root dentro del contenedor sí puede borrar sus propios ficheros. Verificado el ciclo completo dos veces (con y sin `--purge`) contra contenedores Docker reales, con datos reales escritos por Postgres/Redis, confirmando en cada paso qué sobrevivió y qué no.
- **`docker compose down --rmi local`**: borra solo la imagen que este repo CONSTRUYÓ (sin `image:` propio en el compose, así que Compose le da un tag local) — las imágenes oficiales `postgres:15-alpine`/`redis:7-alpine` (con `image:` explícito, pueden estar en uso por otra cosa en la misma máquina) nunca se tocan.
- **Tolerante a un `.env` ya ausente** (instalación rota a medias, o alguien que ya empezó a desmontar a mano): a diferencia de `update.sh`/`backup.sh`, no aborta si falta — avisa y sigue, usando los valores por defecto del propio `docker-compose.yml` para poder parar los contenedores igualmente.

**Endurecimiento de A4 tras revisión de PR (2026-09-26):**

- **Bug real encontrado en esta misma revisión, antes incluso de tocar la validación**: ninguna versión anterior leía `ZASCARR_DATA_DIR`/`HOST_DOWNLOADS_DIR`/`HOST_AMULE_INCOMING_DIR` del `.env` — `"${ZASCARR_DATA_DIR:?}"` dependía por completo de que alguien lo hubiera exportado a mano en la shell antes de llamar al script. En una instalación real (solo el `.env`, nunca exportado a la shell), `--purge` habría abortado con "parameter null or not set" sin borrar nada, y los mensajes informativos de "esto va a hacer" habrían mostrado una ruta vacía. Corregido leyéndolos igual que ya se leía `HOST_LIBRARY_DIR` (grep+cut sobre el `.env`, sin tocar la app Python), con los mismos valores por defecto que ya usa `docker-compose.yml`.
- **`"${VAR:?}"` solo protegía contra una variable VACÍA, no contra una ruta PELIGROSA** — la raíz, una carpeta del sistema, o la propia biblioteca/descargas por una mala edición manual del `.env`. Ahora cada ruta relevante (`ZASCARR_DATA_DIR`, `HOST_LIBRARY_DIR`, `HOST_DOWNLOADS_DIR`, `HOST_AMULE_INCOMING_DIR`) se resuelve con `readlink -f` (symlinks, `..`, relativas) ANTES de construir ningún `rm -rf`, y con `--purge` se rechaza si `ZASCARR_DATA_DIR` resuelve a `/` o a una carpeta del sistema (`/root`, `/home`, `/etc`, `/var`, `/usr`, `/bin`, `/sbin`, `/boot`, `/proc`, `/sys`, `/dev`, `/lib`, `/lib64`, `/opt`, `/tmp`), o si se solapa (misma ruta, o una dentro de la otra, en cualquier sentido) con la biblioteca, las descargas o la carpeta de aMule. Las rutas resueltas se muestran en el resumen ANTES de pedir confirmación, no solo la cadena cruda del `.env`.
- **Ya no se afirma "borrado" sin comprobar el resultado real**: tras el intento de purga (contenedor con la imagen `postgres:15-alpine`, root dentro del contenedor), se comprueba desde el HOST que cada subcarpeta (`postgres`/`redis`/`covers`/`vpn-state`) de verdad ha desaparecido — listar la entrada no necesita permisos sobre su contenido, solo sobre la carpeta padre, de la que el usuario del host es dueño. Si algo sigue ahí (fichero con atributo inmutable, punto de montaje de solo lectura, cualquier fallo que el código de salida por sí solo no habría delatado), el resumen final dice "Desinstalación completada **con avisos**" en vez de "completada" a secas, y nombra exactamente qué falta por borrar.
- **Verificado en vivo, con `.env`/rutas de prueba reales (no solo lectura del script)**: `ZASCARR_DATA_DIR` igual a la biblioteca → rechazado antes de la confirmación; `ZASCARR_DATA_DIR=/` → rechazado; `ZASCARR_DATA_DIR=/home` → rechazado; `ZASCARR_DATA_DIR` como padre de la biblioteca → rechazado; purga normal → las cuatro subcarpetas desaparecen de verdad, verificado desde el host; purga con un fichero marcado `chattr +i` dentro de `postgres/` (ni siquiera root dentro del contenedor puede borrarlo) → detectado, reportado como aviso con el nombre exacto de lo que quedó, resumen final ajustado.
- Timers systemd opcionales (`zascarr-backup.timer`, `zascarr-vpn-state.timer`, instalados a mano por quien los quiera): el script solo AVISA si siguen activos tras desinstalar, nunca los toca — no es su decisión desactivarlos.

**Notas de implementación (A6, 2026-09-26):**

- **Sin dependencias nuevas.** Ni `itsdangerous` (cookies firmadas de Starlette) ni `passlib`/`bcrypt` (hash de contraseña) — `hmac`+`hashlib` de la stdlib bastan para las dos cosas (HMAC-SHA256 para firmar la cookie, PBKDF2-SHA256 para la contraseña, 260.000 iteraciones entonces y **600.000 desde el 2026-10-01**, por medición en la Pi; ver la nota de más abajo). Coherente con CLAUDE.md §2: cada dependencia es RAM y superficie de vulnerabilidad en la Pi.
- **Dos caminos de acceso, mismas credenciales**: cookie de sesión (30 días, `HttpOnly`, `SameSite=Lax`) para la UI HTMX/Jinja2, HTTP Basic Auth por cabecera para `/api/*` (así `curl`/scripts siguen funcionando sin sesión de navegador). `AuthMiddleware` (Starlette, global) decide cuál aplica según el prefijo de la ruta.
- **`secret_key` se autogenera y persiste sola** (`RuntimeSettingsService.ensure_secret_key()`, llamado una vez en el lifespan de `main.py`) — nunca hardcodeada, nunca hace falta ponerla en `.env` a mano. Solo se genera si no existe ya; regenerarla en cada arranque habría invalidado toda sesión activa en cada reinicio/deploy.
- **`base_url` implementado de forma deliberadamente mínima**: es un dato guardado, sin ningún efecto en el enrutado ni en la sesión hoy. La lectura original del backlog ("que funcione tras un reverse proxy") se resolvió por el lado de la autenticación en sí (cookie + Basic Auth funcionan igual detrás de cualquier proxy que reenvíe la cabecera `Authorization`/las cookies sin tocarlas, que es el comportamiento por defecto de Caddy/nginx/Traefik) — intentar que `base_url` reescribiera las URLs absolutas hardcodeadas en plantillas y `RedirectResponse` habría sido una historia bastante más grande (`root_path` de FastAPI/Starlette, auditar cada redirect del código), fuera de la estimación M de A6. Queda reservado para cuando haga falta un enlace absoluto real (webhooks de E4).
- **Guardarraíl explícito en `/ui/ajustes`**: activar `password`/`user_password` sin ninguna contraseña (ni recién escrita ni ya guardada) se rechaza con un mensaje claro en vez de guardarse — la alternativa (dejar que se guarde) habría podido encerrar al propio coleccionista fuera de su instalación sin ninguna forma de deshacerlo desde la UI. Mismo guardarraíl para `user_password` sin nombre de usuario.
- **Open redirect cerrado en el propio desarrollo**: el parámetro `next` de `/login` viene del query string (lo controla quien construye el enlace, no el servidor) — sin filtro, `/login?next=https://sitio-falso.example` habría redirigido tras un login correcto a un dominio ajeno. Se acepta solo una ruta relativa de este mismo sitio (`next.startswith("/") and not next.startswith("//")`), con test de regresión explícito.
- **11 routers web repetían `Jinja2Templates(directory=str(TEMPLATES_DIR))` cada uno con su propio `Environment`** — necesario centralizarlo en una fábrica (`web/routes.py::crear_templates()`) para que `base.html` pudiera preguntar `auth_activo()` (mostrar/ocultar "Cerrar sesión" en el nav) sin tener que colar `auth_mode` en el contexto de cada una de las decenas de `TemplateResponse(...)` ya existentes en el código. Cambio mecánico de una línea por fichero, mismo comportamiento.
- **Verificado en vivo**: Postgres real, `/ui/ajustes` → Seguridad activa "Solo contraseña" al instante (sin reiniciar); visitar cualquier ruta protegida redirige a `/login` en la misma petición; contraseña incorrecta rechazada con mensaje en español; contraseña correcta pone la cookie y devuelve a la página que la pidió; "Cerrar sesión" borra la cookie; `curl -u usuario:clave` valida contra `/api/*` (401 sin credenciales o con credenciales malas, 200 con las correctas); `/api/health` sigue respondiendo sin credenciales.

**Notas de implementación (lote de seguridad sobre A6, 2026-09-30):**

- **Deuda de A6 cerrada: la sesión SÍ se invalida al cambiar la contraseña.** La
  cookie lleva ahora firmada una `auth_session_version` (campo interno de
  `runtime_settings`, sin migración) que sube al cambiar contraseña, usuario o
  modo. Las cookies emitidas antes dejan de valer; el rehasheo por iteraciones
  **no** sube la versión (no cierra sesiones a quien ya está dentro).
- **Fuerza bruta:** los fallos se cuentan **por cuenta** (no por IP — OWASP),
  con retraso progresivo (tope 8 s) **serializado** por un candado, cola acotada
  (3 en vuelo → 429, que no cuenta como fallo) y caché de aciertos de Basic.
  Longitud mínima de contraseña: 12 caracteres. Límite honesto: un ataque
  sostenido puede dejar nuevos logins en 429; se corta en el cortafuegos/proxy.
- **CSRF / Origen / Host:** middleware que rechaza con 403 el `Origin`/`Referer`
  que no cuadre, `Origin: null`, `Sec-Fetch-Site: cross-site` y (con
  `auth_mode="none"`) un `Host` ajeno — en todos los métodos. `BASE_URL` y
  `ALLOWED_HOSTS` dan salida tras un proxy.
- **Iteraciones de PBKDF2: 600.000 desde el 2026-10-01**, decidido por medición
  en una Raspberry Pi 5 real (mediana individual 0,172 s; mediana de dos
  verificaciones simultáneas 0,175 s; umbral de decisión 0,8 s). Sin migración: el
  hash guarda su contador y los antiguos se regeneran al iniciar sesión. Detalle
  en la ficha `benchmark-seguridad-auth-origen-host`.
- **`pip-audit` en CI** (informativo): primera señal real de dependencias.
  Primer resultado: `setuptools` 79.0.1 (`PYSEC-2026-3447`, arreglado en 83.0.0),
  **solo de build y específico de macOS/APFS** (bypass de `MANIFEST.in` al
  construir un sdist) — ZascArr no publica en PyPI y construye en Linux, así que
  no es explotable aquí; se sube el suelo de build igualmente.

**Acceso y orientación (2026-10-05, tras el MVP definido por la revisión):** no se toca la exposición —la hipótesis de que `update.sh` cerrara la LAN **no se confirmó**: el incidente fue usar `127.0.0.1` desde otro dispositivo—. Se añade orientación: (1) `update.sh` termina diciendo **cómo se entra** a partir de `estado_de_publicacion` (lo que Docker tiene de verdad, no el `.env`) y, solo si está abierto, de la contraseña efectiva; abierto y sin contraseña avisa; ante la duda no afirma nada y siempre aclara que actualizar no lo cambia; es informativo y no puede romper una actualización hecha; (2) la URL de la LAN **solo se afirma si se acredita** (la ruta por defecto sale por una interfaz de red local —no un puente de Docker ni una VPN— y su dirección es privada); si no, se ofrecen **candidatas por interfaz** (privadas, de interfaces no virtuales) diciendo que no se pudo confirmar, o se declara que no se pudo determinar. **Nunca** se toma la primera de `hostname -I` (lista los puentes, p. ej. `172.17.0.1`) y la dirección de salida a internet es solo una candidata (con una VPN como ruta por defecto sería la del túnel); (3) README explica que `127.0.0.1` solo vale en la propia máquina; (4) el contador de «Por revisar» **no era estático** (el menú lo recalcula cada 30 s desde la BD); ahora además se recalcula **al instante** cuando asignar o ignorar dejan un archivo de ser pendiente (un elemento inerte con `hx-get="/ui/_nav/estado" hx-trigger="load"` dentro de la respuesta que sustituye a la tarjeta), pidiendo la cuenta a la BD y no restando uno; `ignorar` confirma antes de responder para que el recuento no se adelante al `commit` de `get_db`. **No se usa la cabecera `HX-Trigger`**: htmx 4 la despacha sobre el elemento que hizo la petición, que ya no está en el DOM cuando la tarjeta se reemplaza, y el evento no llega a `body` (una primera versión con cabecera «funcionó» al probarla con `htmx.ajax` sin elemento origen y **no funcionaba con un clic real**). **Rectificación y evidencia:** la comprobación anterior (con `htmx.ajax`) **no acreditaba** el funcionamiento con un clic real. La evidencia nueva es el cambio **340 → 339** en < 0,5 s tras un clic real sobre «Ignorar», con el número **consultado a la BD** por el menú. Para automatizar el ensayo se **anuló el diálogo `confirm`** (`window.confirm = () => true`): esa prueba **no valida** el diálogo de confirmación.

**Notas de implementación (A11, 2026-10-01):**

- **La elección vive en el instalador, no en Ajustes** (el backlog decía «o en Ajustes»). El puerto publicado es propiedad de Docker en el host: la aplicación **no puede abrir ni cerrar el suyo**, así que Ajustes solo podría informar. Se descartó una pantalla que prometiera algo que no puede hacer.
- **Una variable manda: `ZASCARR_BIND_ADDRESS`** (`127.0.0.1` por defecto). La usa el compose para publicar el puerto **de la aplicación** y la lee la app para saber si está expuesta, de modo que no pueden contradecirse. Postgres y Redis siguen literales en `127.0.0.1` (prueba en `tests/test_exposicion.py`: ningún puerto del compose queda en `0.0.0.0` por defecto).
- **Las tres opciones**: «solo esta máquina» (127.0.0.1), «mi red local» (0.0.0.0 + contraseña), «proxy inverso» (127.0.0.1 + `BASE_URL=https://…` + contraseña; lo expuesto es el proxy, que el instalador **no** instala).
- **La invariante de seguridad es el ORDEN** (ampliado tras la revisión de la PR #59, que pedía cerrar las transiciones de una instalación existente, no solo la nueva): **parar la app si existe, publique donde publique** (`docker inspect`, no el `.env`; también con proxy, porque el puerto en localhost no la hace inaccesible; cuatro estados `ausente|local|abierta|indeterminada`, y `indeterminada` aborta en vez de contar como cerrado) → migrar → fijar contraseña → reconciliar `BASE_URL` → escribir `ZASCARR_BIND_ADDRESS` → comprobar lo **efectivo** → `up -d --force-recreate`. Hay una sola escritura de la dirección y es posterior al paso de contraseña (prueba sobre el propio `bootstrap.sh`), más pruebas de transición con un `docker` de pega con estado y verificación en vivo (contenedor abierto que se para; contraseña antigua que deja de valer solo con `--force-recreate`; `BASE_URL` localhost→proxy, proxy→localhost, A→B con override previo en Ajustes y pública solo en Ajustes). Ante cualquier duda —`estado` falla, contraseña rechazada, sin terminal— se vuelve a «solo esta máquina» y se avisa; nunca se abre por error. El modal sin cierre de Sonarr deja una ventana abierta (gana el primero que llega); aquí no existe.
- **Un comando dentro de la imagen** (`python -m zascarr.cli.seguridad estado|fijar-contrasena`), porque en la Pi no hay Python en el host. La contraseña entra **por stdin**, nunca por argumentos ni entorno, y nunca se imprime ni se guarda en claro (pruebas con la frase como centinela). Usa el **mismo servicio que Ajustes** (`services/seguridad.py`): la regla de contraseña vivía dentro del router y se extrajo para no tener dos mínimos que divergieran.
- **Encaje con A1 («3 preguntas, nada más»)**: se añade una cuarta pregunta, pero **con valor por defecto seguro** (instalación nueva: Intro = solo esta máquina; al reejecutar, Intro mantiene la opción actual, que puede ser la LAN); las de contraseña y dominio solo aparecen si se opta por abrir. Sin terminal (`curl | sudo bash` sin tty) no se pregunta: se mantiene lo que hubiera y, si no hay nada, solo esta máquina.
- **Segunda revisión de la PR #59**: (1) `docker port … || return 1` reducía «no existe» y «no se pudo consultar» a un mismo «no abierto» (y un test lo fijaba): ahora son estados distintos y el indeterminado aborta; (2) la parada solo cubría el puerto publicado fuera de localhost, y con proxy la app antigua seguía atendiendo si algo fallaba antes de recrearla: se para siempre que exista contenedor; (3) qué dirección pública se limpia lo decide `base_url_publica` (criterio de la app) y no el validador estricto de entradas nuevas, para no dejar `http://…` o subrutas históricas. Retirar `BASE_URL` no desactiva un proxy ya configurado por el operador.
- **Otros ajustes de la revisión**: URL del proxy limitada a `https://host[:puerto]` con puerto 1–65535 y nombre DNS/IPv4 válido (Python y Bash con la misma regla, probada por paridad); la subred del cortafuegos se lee de `ip route` en vez de deducir un `/24`; `read -rsp` con `IFS=` para no recortar espacios de la contraseña (probado hasta el comando); `/api/health` separa la salud técnica del aviso de seguridad (`seguridad.atencion`).
- **Cuatro hallazgos por el camino**, el primero independiente de A11 y ya en producción:
  1. **`BASE_URL` y `ALLOWED_HOSTS` del `.env` no llegaban al contenedor** (el compose no las pasaba y el contenedor no monta el `.env`), aunque `SECURITY.md` y el changelog de 1.15.0 dicen que se definen ahí. `ALLOWED_HOSTS` no está en Ajustes, así que era un callejón sin salida real. Arreglado en su propia PR, con una prueba que compara `.env.example`, el compose y `Settings`.
  2. **`docker compose run -T` se traga la entrada estándar** aunque el comando no la use: `estado` consumía las líneas de la contraseña y los `read` siguientes recibían vacío. **Solo lo vio la verificación en vivo**; el `docker` de pega de las pruebas no lo hacía, así que ahora lo imita. `estado` va con `</dev/null`.
  3. **La validación de URL de Python aceptaba `https://a b.org`** (`urlsplit` es permisivo). Lo cazó la prueba de paridad con la versión de Bash; las dos usan ahora la misma expresión estricta.
  4. `CONTRASENA_ACCESO` quedaba sin definir en las salidas tempranas y el instalador corre con `set -u`.
- **Verificado en vivo (Docker y Postgres reales)**: por defecto solo escuchan `127.0.0.1:{8000,5432,6379}` y desde la IP de la LAN no hay conexión; con `0.0.0.0` escucha **solo** la app, Postgres y Redis siguen en localhost, y una petición a `/ui/` sin credenciales desde la IP de la LAN recibe `303 → /login`. `estado` pasa de 3 a 0 tras fijar la contraseña (hash PBKDF2 de 600.000, la frase no aparece en la BD). El aviso de `/api/health` sale con el puerto abierto sin contraseña y con una `BASE_URL` pública sin contraseña, y no sale ni en el caso por defecto ni con contraseña.
- **No cubierto, a propósito**: no se ejecutó `bootstrap.sh` entero (exige root y toca el sistema); se verificó cada pieza real —las funciones, el comando por `docker compose run -T`, el compose— y el orden sobre el texto del script. **Deuda declarada**: TLS y proxy son del operador; la cookie sigue sin `Secure` (`SECURITY.md`) y debería activarse con `BASE_URL` en `https://`; el instalador no detecta si el router reenvía el puerto; con `0.0.0.0` publica en **todas** las interfaces (una IP concreta rompería el arranque si el DHCP la cambia).

**Notas de implementación (E1/A1/E2/D4):**

- **E1 (dashboard):** `src/zascarr/static/dashboard.html`, servido en `GET /` (antes esa ruta no existía; la API vivía solo bajo `/api/*`). Página única sin build tooling, sondea `/api/health` cada 10s. Verificado visualmente en el navegador en los 4 estados (todo bien / atención / error / sin conexión) y en viewport móvil. Al mostrar el array `warnings` del healthcheck (VPN sin proteger, etc.) como un aviso visible, esta misma pieza cierra también **D4**.
- **E1 (empaquetado):** `pyproject.toml` no incluía datos no-Python en `pip install .` (no editable, el que usa el Dockerfile) — sin `[tool.setuptools.package-data]`, `dashboard.html` no habría llegado a la imagen. Verificado con una instalación real no-editable en un venv limpio.
- **A1 (bootstrap.sh):** 3 preguntas (biblioteca, raíz de descargas, idioma), escritas en `.env` de forma idempotente (`set_env_var`, no duplica al re-ejecutar). `docker-compose.yml` parametriza el lado HOST de los 3 volúmenes correspondientes (`HOST_LIBRARY_DIR`, `HOST_DOWNLOADS_DIR`, `HOST_AMULE_INCOMING_DIR`) manteniendo el lado del contenedor fijo, así que `config.py` no necesitó cambios. El idioma se guarda en `APP_LOCALE` para cuando exista i18n real — hoy no traduce nada. Probado en aislamiento (sin Docker) con respuestas por defecto y personalizadas, incluyendo idempotencia.
- **E2 (backup):** `scripts/backup.sh` (mismo patrón que `vpn-state.sh`: script host + timer systemd embebido), escribe en `BACKUP_DIR` (por defecto `/var/backups/zascarr/postgres`, configurable con la variable de entorno; debe ser un disco distinto al de los datos) con retención automática de 14 días. `make backup` ahora lo invoca en vez de duplicar la lógica.
- **E3 (restaurar copia — parcial, no cerrada):** `scripts/rollback.sh` es el "script de restore" que la nota de E2 dejaba apuntado como historia aparte. Hace el rollback completo: empareja el commit y el dump por la referencia de rescate `refs/zascarr/update/<TS>` que deja `update.sh`, hace **su propia** copia de seguridad de la BD actual antes de destruir nada, restaura con `psql -v ON_ERROR_STOP=1`, verifica que la BD restaurada tiene tablas, resetea el código, vacía Redis, reconstruye y comprueba el healthcheck. Se niega a adivinar: **no** usa "el backup más reciente" (backup.sh corre a diario a las 04:00, así que el más reciente puede tener ya el esquema nuevo y el rollback no revertiría nada) ni `HEAD@{1}` (cambia con cualquier operación intermedia y caduca). **Le falta para cerrar E3:** el botón en el dashboard, y probarlo una vez contra Docker + PostgreSQL reales (aquí solo se ha verificado en simulación con dobles de `docker`/`curl`, con `bash -n` limpio). El rollback tampoco está cubierto por el runbook de `docs/TESTING_E2E.md`.

**Notas de implementación (D11, 2026-09-25):**

- **Diseño de mínimo impacto, a propósito**: `config.py`/`.env` siguen siendo la ÚNICA declaración de campos/tipos/defaults (CLAUDE.md §2) — nueva tabla `runtime_settings` (migración `0011`, fila única JSONB) con `services/runtime_settings.py` que aplica los overrides MUTANDO el `Settings` ya cacheado por `@lru_cache get_settings()`. Como la app corre con `--workers 1` (un solo proceso), mutar sus atributos es visible al instante para `ComicVineClient`/`ProwlarrClient`/`TransmissionClient`/`AMuleClient`/`Orchestrator`/`DiscoveryService` **sin tocar una sola línea de esos ficheros**. Overrides cargados también al arrancar (`main.py::lifespan`), para que sobrevivan a un reinicio real.
- **"Probar conexión" usa los valores DEL FORMULARIO**, no solo lo ya guardado — para poder probar antes de confirmar. Un campo de secreto enviado vacío cae al valor ya guardado (mismo criterio que "guardar campo vacío = no cambiar"), nunca a una petición sin credenciales por error.
- **Bug de aislamiento de tests encontrado y corregido en el propio desarrollo**: un test que mutaba el `Settings` real (vía `apply_overrides`) sin restaurarlo después dejaba `comicvine_api_key` con un valor filtrado para el siguiente test — solo visible corriendo la suite completa, no en aislamiento. Confirma por qué cada test que ejercita `apply_overrides`/`save()` necesita su propio fixture de restauración.
- **Verificado en vivo contra Postgres real**: guardar la URL de Prowlarr y activarlo se refleja al instante (mismo proceso, sin reiniciar), confirmado tanto en la fila de `runtime_settings` como en el HTML servido por una petición `curl` posterior (no solo en el navegador — un artefacto de autocompletado del propio navegador del sandbox estaba enmascarando el valor correcto, detectado y descartado comparando contra la respuesta cruda del servidor). "Probar conexión" sin clave de Prowlarr configurada responde con un mensaje claro en español, sin excepción ni petición a la red.
- **Bug real de producción, reportado y diagnosticado con datos reales del usuario en tres rondas sucesivas (2026-09-25, post-release)**: Prowlarr/Transmission/aMule fallaban con "no se pudo conectar" en una instalación real, con URL/credenciales correctas.
  1. Primera hipótesis (servicio atado a `127.0.0.1`) **descartada con evidencia real**: `ss -tlnp` mostró los tres escuchando en `0.0.0.0`/`*`.
  2. Segunda hipótesis, `ufw` con reglas "solo LAN" — **confirmada y corregida** por el usuario (`ufw allow from 172.17.0.0/16 ...`), pero el fallo **persistió** tras aplicarla.
  3. Causa real, encontrada comparando `docker exec zascarr-orquestador getent hosts host.docker.internal` (`172.17.0.1`) contra `docker inspect ... Networks.*.Gateway` (`172.18.0.1`, la red real `zascarr_zascarr-internal` que crea `docker-compose`): **el valor mágico `host-gateway` de Docker resolvía a la puerta de enlace del puente POR DEFECTO (`docker0`), no a la de la red personalizada que el contenedor usa de verdad** — dos redes Docker distintas con gateways distintos, la regla de `ufw` (correcta en sí) apuntaba a una red que el contenedor ni usaba. Reproducido y verificado en sandbox de forma aislada (red Docker personalizada + `--add-host=host.docker.internal:host-gateway`, mismo resultado que en la Pi real) antes de escribir el fix.
  Corregido en `docker-entrypoint.sh`: detecta la puerta de enlace REAL de la propia interfaz del contenedor (`/proc/net/route`, sin depender de `ip`/iproute2 — python3 ya es una dependencia de la propia app) y reescribe `/etc/hosts` en el arranque. Bug encontrado a su vez en la propia verificación de este fix: `sed -i` sobre `/etc/hosts` falla con "Device or resource busy" porque Docker lo monta como bind especial y no se puede renombrar encima — corregido con truncar-y-escribir (`cat > /etc/hosts`) en vez de edición in-place por renombrado.
  Mensaje de "Probar conexión" y README ampliados para cubrir las tres causas, con `172.16.0.0/12` (todo el rango que usa Docker) en vez de una subred exacta para la regla de `ufw`, más robusto ante una futura reasignación de red.
  **Lección del propio proceso**: cada hipótesis fue razonable y estaba bien fundamentada, y las dos primeras eran sencillamente incorrectas o incompletas — solo pedir el diagnóstico exacto en cada ronda, y no conformarse con "ya debería estar arreglado", permitió llegar a la causa real.

**Notas de implementación (D9, 2026-09-26):**

- **Sin timestamp propio**: la migración `0013` solo añade `Wishlist.last_error` (Text). Un `last_error_at` habría sido redundante — `last_searched_at` (ya existente desde D1) se marca en el mismo punto exacto de `_process_item` donde se decide la causa, así que ya sirve como su timestamp.
- **El aviso legal pendiente NO es un `last_error` de fila.** Es un estado global del sistema (todas las filas están igual de paradas por el mismo motivo), así que escribirlo en cada item de la wishlist en cada ciclo saltado habría sido una query y una escritura de más por ciclo sin aportar nada por fila. En su lugar, `web/wishlist.py::index` comprueba `is_acknowledged(db)` una vez y muestra un banner aparte en `/ui/wishlist` — mismo patrón que ya usa `_legal_disclaimer.html` para el aviso de "uso responsable".
- **Causas distinguidas realmente, no una lista de aspiración**: sin fuente activa (ni Prowlarr ni foro configurados — ni se llama a Prowlarr), fuente inaccesible (Prowlarr lanza una excepción real, capturada con `try/except` alrededor de la llamada — antes se colaba hasta el `except` genérico de `process_wishlist` y quedaba indistinguible de cualquier otro fallo), sin resultados, candidato encontrado pero ningún backend de descarga activo (se distingue guardando el pool de candidatos ANTES del filtro de opt-in, para saber si el filtro fue el que vació la lista), cliente de descarga inaccesible (todos los candidatos fallan al enviarse), error inesperado (el `except` genérico de `process_wishlist`). Cada mensaje en español llano, nunca una excepción/URL/cuerpo HTTP tal cual (CLAUDE.md §5.4 sobre logs sin datos sensibles, aplicado aquí también al campo visible en UI).
- `last_error` se limpia (`None`) en cuanto un envío tiene éxito — un motivo de un ciclo anterior no se queda pegado en la fila una vez que la búsqueda se recupera sola.
- **Verificado en vivo**: migración `0013` aplicada sobre Postgres real tras `0012`; `/ui/wishlist` muestra el banner de aviso legal pendiente sin aceptar, y el motivo concreto junto al badge de estado tras insertar una fila con `last_error` a mano.

**Notas de implementación (D10, 2026-09-26):**

- **Sin estado de servidor nuevo**: entre "ver los candidatos" y "confirmar uno", los datos del `SearchResult` elegido (título, indexer, URL, tamaño, seeders, categoría) viajan en campos ocultos dentro del propio `<form>` de cada candidato — el navegador es quien los recuerda. Se descartó una caché por token (Redis/diccionario en memoria) por no aportar nada que el propio HTML no resuelva ya, y por evitar el enésimo sitio con estado a limpiar.
- **`Orchestrator._search_and_rank` es la pieza compartida**: se extrajo de `_process_item` (mismo comportamiento exacto, mismos tests existentes en verde sin tocarlos) para que el ciclo automático y "Buscar ahora" nunca diverjan en qué cuenta como candidato válido — mismo ranking, mismo filtro de backends activos (blindaje legal), mismos motivos de D9 cuando no hay nada que mostrar.
- **Bug real encontrado en el propio desarrollo, antes de dar la historia por cerrada**: `preview_candidates` reusaba `_search_and_rank` tal cual, que deja el item en estado `SEARCHING` a media búsqueda esperando que quien llama continúe enseguida con el envío (como sí hace `_process_item`). Al detenerse ahí para que el coleccionista mire, un `SEARCHING` sin revertir dejaba el item invisible PARA SIEMPRE al ciclo automático (que solo selecciona `WANTED`/`FAILED`) si el coleccionista cancelaba o cerraba la pestaña. Corregido revirtiendo a `WANTED` en `preview_candidates` en cuanto hay candidatos que mostrar.
- **Segundo bug real, encontrado verificando en vivo con un Transmission caído a propósito**: `Orchestrator._send` no capturaba errores de conexión (`httpx.ConnectError` y similares) — en el ciclo automático quedaba enmascarado por el `except` genérico de `process_wishlist` (funcionaba, pero con el motivo impreciso "error inesperado"); en la confirmación manual de D10, al no existir ningún `try/except` en el router, se colaba como un 500 crudo sin ninguna explicación en pantalla. Se capturó en `_send` (el único punto que ambos caminos comparten) devolviendo `None` como cualquier otro rechazo — ahora ambos caminos dan `MOTIVO_CLIENTE_INACCESIBLE`, ninguno revienta. Confirmado en vivo con un Prowlarr de mentira (servidor HTTP mínimo) devolviendo candidatos reales y un Transmission deliberadamente inalcanzable.
- **`hx-confirm` en el botón "Descargar este"**: mismo patrón ya usado en "Quitar" — un diálogo nativo del navegador que la automatización de pruebas no puede resolver sola (limitación ya documentada en el proyecto, B2). Verificado en su lugar con una petición HTTP directa al endpoint.

**Endurecimiento de D10 tras revisión externa (2026-09-26):** D10 figuraba como hecho, pero esta garantía nunca se especificó — la primera versión reenviaba los campos del candidato (título, `download_url`, tamaño...) en claro dentro de campos ocultos del formulario, y el servidor los recogía sin comprobar que vinieran de verdad de una búsqueda hecha para ESE item. Un formulario manipulado a mano podía colar cualquier `download_url` para cualquier item de la wishlist, saltándose por completo `preview_candidates()`.

- **Token firmado por el servidor, no datos sueltos del formulario**: `web/wishlist.py::buscar_ahora` firma cada candidato entero junto con el `item_id` y una caducidad de 600s (`services/orchestrator.py::crear_token_candidato`, HMAC-SHA256 vía las mismas primitivas `sign_token`/`verify_token` que ya firman la cookie de sesión de A6 — sin dependencias nuevas, CLAUDE.md §2). El formulario solo reenvía ese token — firmado, no cifrado: legible en base64, no secreto, pero cualquier alteración invalida la firma; `enviar_candidato` nunca vuelve a construir un `SearchResult` a mano, solo lo que puede extraer de un token que el propio servidor firmó (`verificar_token_candidato`). Cualquier cambio en cualquier campo, usarlo para otro item, o usarlo pasada su caducidad, invalida la firma → 400.
- **Guardarraíl de reenvío/doble confirmación**: `send_manual_candidate` ahora exige `item.status in (WANTED, FAILED)` antes de hacer nada — el mismo criterio accionable que ya decide si se ofrece "Buscar ahora" en la fila (`puede_buscar_ahora`). Un token válido reenviado (doble clic, pestaña duplicada) sobre un item que ya pasó a `DOWNLOADING`/`IMPORTED` no reencola nada.
- **Verificado en vivo contra Postgres real**: token válido para el item → aceptado; token válido pero acuñado para OTRO item → 400; token con la firma manipulada (último carácter alterado) → 400; mismo token válido reenviado tras marcar el item como `DOWNLOADING` a mano → 200 pero sin tocar nada (queda `last_error="Ese candidato ya no es válido..."`, estado sin cambiar).
- **Tests añadidos**: `tests/test_orchestrator.py::TestTokenCandidato` (6, incluye caducidad y secreto distinto) + `TestBusquedaManual::test_no_reenvia_si_el_item_ya_no_esta_en_estado_accionable`; `tests/test_web_wishlist.py::TestEnviarCandidato` reescrita con casos de token de otro item, token manipulado, token de otro secreto y doble confirmación.

**Segundo endurecimiento de D10, revisión de PR (2026-09-26) — reclamación atómica contra confirmaciones concurrentes:** firmado no es lo mismo que de un solo uso. El guardarraíl de estado (`item.status in (WANTED, FAILED)`) detiene un reenvío SECUENCIAL tras completar el primero, pero no dos peticiones CONCURRENTES: ambas pueden leer `WANTED`/`FAILED` en su propia sesión de BD antes de que ninguna termine `_send()` (I/O de red real, con `await` de por medio) — la descripción original de "doble confirmación resuelta" era imprecisa en ese caso.

- **Reclamación atómica antes de tocar la red**: `send_manual_candidate` ejecuta `UPDATE wishlist SET status='searching' WHERE id=... AND status IN ('wanted','failed')` (vía SQLAlchemy Core, no ORM) antes de llamar a `_send()`. Postgres serializa los `UPDATE` contra la misma fila: la segunda petición concurrente bloquea hasta que la primera confirma, y entonces reevalúa el `WHERE` contra el estado ya cambiado — 0 filas afectadas, no llega a mirar el backend. Si la reclamación falla al enviar (backend desactivado), el item vuelve a `FAILED` con su motivo — no se queda "colgado" en `SEARCHING` (mismo bug ya corregido una vez en `preview_candidates`).
- **Bug real encontrado verificando en vivo, no en desarrollo**: la primera versión de este parche SÍ hacía la reclamación atómica correctamente (verificado: de dos confirmaciones disparadas a la vez, exactamente una llama al backend), pero la petición perdedora escribía `last_error="candidato inválido"` incondicionalmente — como esa escritura ocurre DESPUÉS de que la ganadora ya confirmó la suya (la ganadora pasa por `_send()`, más lento), pisaba con un mensaje de error un resultado que en realidad había tenido éxito (`last_error` volvía a quedar con el texto de "inválido" en vez de `None`). Corregido: la rama de "perdió la reclamación" ya no escribe nada — la fila que ve esa petición se refresca aparte (`_get_row` en el router) con el estado real y actual, que es más útil que un mensaje falso.
- **Verificado en vivo contra Postgres real**: dos llamadas a `send_manual_candidate` disparadas a la vez (`asyncio.gather`) sobre el mismo item, con un `_send` deliberadamente lento (simula la latencia de red real) — exactamente una llama al backend, la otra pierde la reclamación; estado final consistente (`downloading`, `last_error` vacío, `download_ref` de la ganadora, sin restos del "candidato inválido" de la perdedora).
- **Precisión de vocabulario**: el token es firmado (íntegro, ligado al item, con caducidad), no cifrado — su contenido es legible en base64, nunca secreto. "Opaco" describía mal esa propiedad; la documentación y el código ya no usan ese término.
- **Tests añadidos**: `tests/test_orchestrator.py::TestBusquedaManual::test_pierde_la_reclamacion_atomica_no_envia_nada` y `test_perder_la_reclamacion_no_pisa_el_resultado_del_ganador`.

**Notas de implementación (D1):**

- **El backend de búsqueda/descarga ya existía y era sustancial**
  (`orchestrator.py`, `transmission.py`, `amule.py`, `prowlarr.py`,
  `forum_scraper.py`) pero D1 no funcionaba en absoluto: tenía tres huecos
  sin documentar, encontrados al explorar el repo para esta historia.
  - **El orquestador nunca se ejecutaba solo** — mismo bug de fondo que
    B1/B3 encontraron en el importador antes de arreglarlo:
    `scan_interval_minutes`/`max_concurrent_downloads` eran ajustes que
    nadie leía, ningún código llamaba `process_wishlist()` jamás. Fijado
    con un `_orchestrator_loop` en `main.py`, calcado de
    `_import_loop`/`_enrichment_loop`.
  - **Un item sin resultados o cuya descarga fallaba se abandonaba para
    siempre** — mismo bug que H2 del enricher (peer review v2), aplicado
    aquí: `process_wishlist` solo seleccionaba `status == WANTED`, así que
    un `FAILED` no se reintentaba nunca, y uno sin resultados se
    reintentaba en CADA ciclo sin límite. Fijado con un cooldown de
    `orchestrator_retry_cooldown_hours` (6h por defecto, config.py) sobre
    `last_searched_at` — mismo patrón que `enrichment_attempted_at`.
  - **Nada cerraba el círculo "descargado → en tu biblioteca"**: cero
    referencias a `WishlistStatus.DOWNLOADED`/`IMPORTED` en todo el código
    aparte de su propia definición. En vez de scrapear el estado de
    Transmission/aMule (aMule no da nombre/hash del completado hoy, solo
    un % global), `Orchestrator.check_completions()` comprueba si ya
    existe un `File` enlazado al `Issue`/`Series` que el item pedía — el
    import loop periódico ya existente es quien de verdad clasifica el
    archivo, esto solo refleja ese hecho en la wishlist. Agnóstico de
    backend, sin scraping frágil de HTML de aMule.
- **Reintento con el siguiente candidato del pool (idea de Mylar3,
  benchmarking anterior):** si el mejor resultado falla al enviarse al
  backend de descarga, se prueba el siguiente en vez de rendirse a la
  primera. `_select_best` pasó a `_ranked_candidates` (devuelve todo el
  pool rankeado, no solo el ganador).
- **M1 cerrado de raíz** (no en otra pasada): `Wishlist(**data)` y
  `setattr(item, field, value)` sobre el body crudo en `api/wishlist.py`
  sustituidos por `WishlistCreate`/`WishlistUpdate` (Pydantic, campos
  explícitos) delegando en el nuevo `WishlistService`
  (`src/zascarr/services/wishlist.py`) — misma fuente de verdad para
  la API JSON y la nueva UI, sin lógica duplicada.
- **UI**: `/ui/wishlist` (`src/zascarr/web/wishlist.py`), mismo patrón
  HTMX que `pendientes.py` — buscar una serie ya catalogada, añadirla,
  ver su badge de estado ("Buscando…"/"Descargando…"/"En tu
  biblioteca"/"Sin resultados"), reintentar manualmente o quitarla.
  Verificado en un navegador real de principio a fin contra Postgres real
  (no solo con FakeSession): buscar, añadir, recargar y comprobar que
  persiste, quitar, recargar y comprobar que desaparece. El botón
  "Quitar" usa `hx-confirm` (diálogo nativo del navegador) — la
  herramienta de automatización no lo acepta sola (mismo tipo de
  limitación que el `hx-trigger="keyup changed"` de B2, confirmado
  disparando la petición directamente por fetch: el backend responde
  bien, es la herramienta la que no interactúa con el diálogo nativo).
- **Verificación end-to-end contra Postgres real**, no solo con dobles:
  migración 0001→0007 aplicada de cero; un ciclo completo simulado
  (`Series` + `Wishlist` WANTED → `Orchestrator` con Prowlarr/Transmission
  simulados → `DOWNLOADING` con `download_ref`/`download_backend`
  correctos → insertar el `File` que el import loop habría creado →
  `check_completions` → `IMPORTED` con `downloaded_at`); y un segundo
  ciclo confirmando que un `FAILED` reciente NO se reintenta antes del
  cooldown (Prowlarr no se vuelve a llamar).
- **Fuera de alcance deliberado**: tabla `OrchestratorRun` estilo
  `ImportRun` para historial (no la pide el criterio de aceptación);
  ampliar `AMuleClient`/`TransmissionClient` (no hace falta, ver arriba);
  cancelar/pausar una descarga en curso desde la UI (solo "quitar" antes
  de que empiece a descargar, vía el `DELETE` ya existente).
**Notas de implementación (D5 — módulo Novedades, spec recibida
2026-09-22, NO implementado todavía):**

- Spec completa en `/mnt/Datos/Descargas/SPEC_MODULO_NOVEDADES.md` (fuera
  del repo — copiar a `docs/` si se decide construir, para que no se
  pierda): tabla `novedades` nueva, scrapers Comic Vine (reutiliza
  `ComicVineClient`) + Norma/Panini/ECC (HTML nuevo) + Whakoom opcional,
  `NovedadItem` como contrato Pydantic entre scrapers y core, matching
  contra `series.title_norm` (exacto, luego fuzzy pg_trgm ≥0.60), job
  semanal, endpoint `/api/novedades`, pantalla `/ui/novedades`.
- **Dos correcciones antes de dar la spec por buena:**
  - **La migración que propone es `0007`, pero ese número ya existe**
    (`20260921_0007_wishlist_download_ref.py`, de D1). La tabla
    `novedades` sería `0008`. Revisar el resto de la spec por si asume
    algo más sobre el estado de las migraciones que ya no es cierto.
  - **La spec asume que ya existe un patrón `optional=True` en los
    scrapers ("mismo patrón que el scraper del foro CRG") — no existe.**
    Verificado de nuevo contra el código (tercera vez que un documento
    externo da esto por hecho): ningún scraper del repo tiene un
    parámetro `optional`; `forum_enabled` es un booleano de config para
    activar/desactivar la fuente del foro, no un mecanismo genérico
    reutilizable. Este mecanismo es exactamente **F15/B8** (toggle por
    proveedor), que sigue sin construir — la spec de Novedades lo da por
    prerequisito sin serlo todavía.
- **Dependencias reales, no las que asume el orden sugerido de la spec**
  ("tras H1-H3 y F1/F2"): H1-H3 sí están hechos. F1 (reintento) también,
  pero solo la parte de reintento — el "motivo de fallo legible" que F1
  también pedía sigue pendiente (ver nota de D1 arriba). **F2 NO está
  hecho** (ni el fix de `sort_order` ni el botón "Completar", C6) — la
  propia spec depende de un estado que todavía no existe. F4 (webhooks),
  F15/B8 (toggle por proveedor) y C1/C2 (ficha de serie) tampoco existen,
  y la spec los da por disponibles en varios puntos (notificación al
  casar novedad, ficha de serie con insignia "próximo número").
- **No verificado en vivo todavía**: a diferencia de Tebeosfera (scrapeado
  y confirmado contra el sitio real antes de construir el cliente), no se
  ha comprobado la estructura HTML real de Norma/Panini/ECC/Whakoom. Antes
  de escribir un solo scraper nuevo, tocaría repetir esa disciplina —
  visitar los sitios reales, confirmar que la cadencia semanal/rate limit
  propuestos son viables, y que el HTML no cambia tan rápido como para
  que el diseño "un WARNING silencioso si rompe" sea suficiente en la
  práctica.
- **Fuera de alcance de la v1 (según la propia spec, razonable):**
  disparar descargas automáticas desde novedades, precios históricos,
  novedades de tiendas/quiosco.

- **Hueco confirmado por el benchmarking de ronda 2 (F1):** el reintento
  con el siguiente candidato ya está (ver arriba), pero un `FAILED` no
  guarda ningún motivo legible en ningún sitio — solo hay un
  `logger.exception` sin persistir. La UI de `/ui/wishlist` muestra "Sin
  resultados" para cualquier fallo, sin distinguir "nada encontrado" de
  "Transmission no responde". Pendiente: columna `Wishlist.last_error`
  (texto corto) rellenada en el `except` de `process_wishlist` y en la
  rama "todos los candidatos fallaron" de `_process_item`, mostrada en
  la fila de la wishlist.

### Épica U — "La interfaz me guía" (usabilidad)

**Origen:** revisión heurística de UX del 2026-10-01 sobre siete capturas de la UI (dashboard, Descubrir, Pendientes, Deseados, Revisión de mi biblioteca, Ajustes y Estado), con los 14 archivos reales de `_Unsorted` y 5 filas «BPRD» en Deseados. **Alcance honesto:** es una evaluación heurística sobre capturas estáticas, **no** una prueba con usuarios; no cubre estados de carga, errores reales ni móvil. Por eso U10 (validar con coleccionistas) va **antes** de dar por buenos los rediseños de U1 y U2. Marco: heurísticas de Nielsen (visibilidad del estado, lenguaje del usuario, control y libertad, prevención y recuperación de errores) y WCAG 2.2 AA.

**Medido, no opinado** (script sobre los tokens de `static/web.css`, razón de contraste WCAG): `--ink-faint` (#8b8b92) sobre `--paper` (#f6f3ec) da **3,05:1**, sobre `--paper-2` **2,82:1** y sobre `--caption-bg` **3,05:1**; WCAG 2.2 AA exige **4,5:1** para texto normal. `--cyan` sobre `--paper` da 2,84:1 y `--ok` 3,83:1. En modo oscuro `--ink-faint` da 4,47:1 sobre `--paper` (a 0,03 del umbral) y 4,14:1 sobre `--paper-2`. `--ink-soft` pasa con 7,94:1. Varios tamaños de la hoja están entre `.72rem` y `.8rem` (11,5–12,8 px). Qué textos usan realmente esos tokens **hay que verificarlo en las plantillas**: el cálculo prueba el par de colores, no su uso.

| ID | Historia | Aceptación clave | P | Est |
|---|---|---|---|---|
| U1 | Como coleccionista con decenas de archivos sin clasificar, quiero revisar Pendientes de forma compacta, con el nombre completo, la sugerencia a la vista y acciones por lotes, para resolver 14 archivos sin repetir 14 veces el mismo ritual | Tarjeta/fila compacta con nombre íntegro; selección múltiple; «asignar a esta serie» sobre la selección; «Ignorar» reversible; nada se asigna sin confirmación explícita | P0 | L |
| U2 | Como coleccionista recién instalado, quiero que el panel de inicio me diga qué hacer primero en vez de enseñarme ceros contradictorios | Checklist de 3 pasos derivado del estado real; **una** acción principal; sin «0 %» ni «5 series» cuando no hay catálogo; un solo buscador | P0 | M |
| U3 | Como coleccionista, quiero que Deseados distinga «buscando» de «sin resultados», agrupe duplicados y me diga qué hacer cuando no encuentra nada | Estados mutuamente excluyentes; aviso al añadir algo ya deseado; enlace a la causa (Ajustes/Fuentes) según el motivo de D9 | P1 | M |
| U4 | Como coleccionista con la vista cansada o en un móvil al sol, quiero textos legibles, para no tener que adivinar qué pone | Todo texto con ≥ 4,5:1 (3:1 solo texto grande); tamaño mínimo de texto informativo definido; prueba automática de contraste sobre `web.css` | P1 | S |
| U5 | Como coleccionista que no sabe qué es Prowlarr, quiero un asistente que me pregunte qué quiero conectar y esconda lo avanzado, para configurar sin leer párrafos técnicos | Entrada «¿Qué quieres conectar?»; modo básico/avanzado; «Probar conexión» guía al siguiente paso; `host.docker.internal` solo en avanzado | P1 | M |
| U6 | Como coleccionista, quiero que Estado diga la verdad en mi idioma, para saber si debo preocuparme | Semáforo global = peor de los parciales; avisos sin rutas internas; cada aviso con causa y acción | P1 | S |
| U7 | Como coleccionista, quiero una navegación con nombres inequívocos, para no confundir «Biblioteca» con «Mi biblioteca» | Un término por concepto; agrupación de las 8 entradas; glosario de vocabulario en `CLAUDE.md` | P2 | S |
| U8 | Como coleccionista con duplicados, quiero que la revisión de mi biblioteca me resuma y priorice, para atacar primero lo que más espacio recupera | Resumen arriba (GB recuperables, nº de grupos); orden por ahorro; progreso del escaneo; **sigue sin borrar ni sugerir borrar** | P2 | M |
| U9 | Como coleccionista que usa el móvil o la tablet en el sofá, quiero que la UI funcione en pantalla pequeña, para revisar Pendientes sin ampliar | Probado a 360–414 px y tablet; 1 columna; objetivos táctiles suficientes; sin desbordes | P1 | M |
| U10 | Como equipo, quiero validar Pendientes y el panel de inicio con 3–5 coleccionistas reales antes de implementarlos, para no rediseñar sobre una hipótesis | Guion de tareas, métricas y decisión adoptar/adaptar/descartar registrada en una ficha §13 | P1 | S |

#### Fichas detalladas de la Épica U

**U1 — Pendientes compacto, con sugerencia a la vista y acciones por lotes (P0, L)**

- **Historia.** Como coleccionista que acaba de importar su colección, quiero revisar los archivos sin clasificar en una vista compacta que me muestre el nombre completo, lo que el sistema detectó y su mejor sugerencia, y que me deje resolver varios a la vez, para clasificar 14 archivos en minutos y no en una tarde.
- **Problema (evidencia).** En la captura de `/ui/pendientes` cada tarjeta mide unos 340 px de alto y casi toda es un hueco vacío donde iría la portada (CBR no tiene miniatura, ver B2); el título sale truncado («La Imposible Patrulla X (144-1…»); los 14 archivos repiten el mismo campo de búsqueda y el mismo «Ignorar». Con los nombres reales hay claros patrones («La Patrulla X Omnigold N», «Marvel Gold - La Patrulla-X Original N») que el humano reconoce de un vistazo.
- **Criterios de aceptación.**
  1. Dado un archivo sin portada, cuando se lista, entonces la tarjeta **no reserva** el hueco de la miniatura: ocupa solo lo necesario y muestra el **nombre completo** (con salto de línea o `title`/expandible, nunca recortado sin remedio).
  2. Dada una sugerencia del matcher (B12), cuando existe, entonces se ve **sin interacción previa**, con serie, año, puntuación y número precargado, y un botón «Sí, es esta».
  3. Dados varios archivos seleccionados, cuando el usuario elige una serie, entonces se asignan **todos** con una sola confirmación que muestra la lista de lo que va a pasar («3 archivos → La Patrulla-X»). **Nunca** se asigna a una serie por inferencia automática (B12).
  4. Dado un archivo ignorado, cuando el usuario se equivoca, entonces existe **Deshacer** inmediato y una vista «Ignorados» desde la que recuperarlo (`files.review_dismissed` ya existe: **sin migración**).
  5. «Ignorar» tiene un peso visual claramente **menor** que la acción principal y no está pegado a ella.
  6. La asignación por lotes reutiliza `ReviewService.assign_to_series` tal cual, archivo a archivo: conserva las defensas de B15 (`ColisionDeEdicion`, 409 en español) y el aprendizaje de alias de B13. Si un archivo del lote falla, **los demás se procesan** y el resultado lo dice por archivo.
  7. Agrupar sugiere, no decide: la agrupación por patrón de nombre es **ayuda visual**; asignar sigue siendo una decisión del usuario.
- **Fuera de alcance.** Autoasignación, crear series desde Pendientes (es C0/Descubrir), ampliar el parser (B14/RF-06).
- **Pruebas.** Unitarias sobre la plantilla (nombre íntegro, sin hueco sin portada); API del lote con éxito parcial; regresión de «Ignorar → Deshacer»; verificación en navegador con los 14 archivos reales de `_Unsorted`.
- **Dependencias y riesgos.** B2, B12, B13, B15. Riesgo: un lote que aprende un alias incorrecto lo fija (lección del propio backlog: «el automatismo no crea el error, lo fija»), así que el aprendizaje de alias en lote debe mostrar qué patrón se va a recordar antes de confirmar.

**U2 — Panel de inicio con primeros pasos y contadores honestos (P0, M)**

- **Historia.** Como coleccionista recién instalado, quiero que la pantalla de inicio me diga qué hacer primero y no me enseñe cifras contradictorias, para llegar a ver mi colección organizada sin saber nada de la arquitectura.
- **Problema (evidencia).** El panel muestra «5 series en la biblioteca», «0 % completitud estimada» y «0 números pendientes» y debajo «Aún no hay series importadas». Hay dos buscadores casi idénticos («Descubre tu próxima serie» y el de Deseados). Un 0 % en un sistema recién instalado desmotiva y no es una medida válida (el propio backlog advierte que el porcentaje mezcla formatos y fuentes).
- **Criterios de aceptación.**
  1. Si no hay catálogo, los contadores de completitud **no se pintan** (ni 0 %): se sustituyen por el estado vacío.
  2. El estado vacío muestra un **checklist de pasos derivados del estado real** (no marcados a mano): (1) dar de alta una serie, (2) revisar los N archivos pendientes, (3) conectar una fuente de descarga, (4) aceptar el aviso legal si hay descargas. Cada paso se tacha solo cuando la condición se cumple.
  3. Hay **una** acción principal visible (el siguiente paso pendiente) y las demás son secundarias.
  4. Un único buscador en la pantalla, con la etiqueta de lo que hace («Buscar para dar de alta» o «Buscar para añadir a deseados», no ambas).
  5. Si hay archivos en Pendientes, el panel lo dice con el número real y enlaza a ellos.
  6. Los números que se muestren cuentan lo mismo que el resto de pantallas (una sola fuente de verdad en el servicio, no un cálculo paralelo en la plantilla).
- **Fuera de alcance.** Rediseñar el cálculo de huecos (C6/B22) o arreglar la mezcla de formatos del porcentaje global.
- **Pruebas.** Servicio con BD vacía, con series sin archivos, con pendientes y con todo configurado; cada paso del checklist por separado.
- **Dependencias.** C1, E1, B2, D11. Se valida con U10 antes de pulir el diseño.

**U3 — Deseados con estados honestos y duplicados controlados (P1, M)**

- **Historia.** Como coleccionista, quiero que la lista de deseos me diga con claridad si se está buscando, si no hay nada o si algo falla, y que no me deje acumular filas idénticas, para confiar en que «marcar y olvidarme» funciona.
- **Problema (evidencia).** Cinco filas «BPRD» y una «The DC Universe by Mike Mignola» aparecen con el badge «BUSCANDO…» y el texto «No se encontró nada en las fuentes activas»: dos mensajes incompatibles a la vez. No hay indicación de duplicado ni de qué hacer. (No se ha podido ver si son números distintos de una misma serie o añadidos repetidos; la ficha debe empezar comprobándolo en la BD.)
- **Criterios de aceptación.**
  1. Estados mutuamente excluyentes y legibles: «En cola», «Buscando ahora», «Sin resultados (último intento: fecha)», «Descargando», «En tu biblioteca», «Falló: causa». «Buscando» no coexiste con «sin resultados».
  2. Cada motivo de D9 trae su **siguiente paso** con enlace (p. ej. «No hay ninguna fuente activa» → `/ui/ajustes`; «Cliente de descarga inaccesible» → Ajustes + diagnóstico de red A10).
  3. Al añadir algo ya presente, el sistema lo **dice** («Ya lo tienes en deseados») en vez de crear otra fila. La wishlist no tiene `UNIQUE` hoy: decidir en la ficha si se resuelve en el servicio o con una restricción, siguiendo la regla del backlog de «reconciliación amable, no excepción cruda».
  4. Las filas de una misma serie se **agrupan** con un recuento y se pueden expandir.
  5. «Buscar ahora» (D10) sigue gateado por el aviso legal y conserva el token firmado.
- **Fuera de alcance.** Cambiar la lógica de búsqueda del orquestador.
- **Pruebas.** Matriz estado × motivo → texto y enlace; alta repetida; agrupación con y sin duplicados.
- **Dependencias.** D1, D9, D10, A10.

**U4 — Legibilidad: contraste y tamaño mínimos (P1, S)**

- **Historia.** Como coleccionista que usa la UI en una tablet con reflejos o con poca vista, quiero que todo texto sea legible, para no perderme la información secundaria.
- **Problema (medido).** Ver la cabecera de la épica: `--ink-faint` no llega a 4,5:1 en modo claro (3,05 y 2,82:1) y roza el límite en oscuro (4,47 y 4,14:1); `--cyan` (2,84:1) y `--ok` (3,83:1) fallan como texto sobre `--paper`. La hoja usa tamaños de `.72rem` a `.8rem` (≈ 11,5–12,8 px) en varios sitios.
- **Criterios de aceptación.**
  1. Todo texto normal cumple **≥ 4,5:1** y el texto grande **≥ 3:1** en **ambos** temas, calculado sobre el fondo real en que se pinta. Los elementos de interfaz no textuales relevantes (bordes de campos, iconos de estado) cumplen **≥ 3:1**.
  2. Se define un **tamaño mínimo** para el texto informativo (propuesta del equipo: 14 px; WCAG no fija un tamaño mínimo, es una decisión de producto, a validar con U10).
  3. El estado nunca se transmite **solo por color** (los semáforos llevan texto).
  4. Hay una prueba automática (sin navegador) que lee las variables de `web.css` y falla si un par texto/fondo declarado baja del umbral.
- **Fuera de alcance.** Rediseño de la paleta; solo se ajustan los tonos que fallan, conservando la identidad.
- **Pruebas.** El test de contraste descrito; revisión manual con las capturas actuales como línea base.
- **Dependencias.** Ninguna. Es barata y desbloquea el resto.

**U5 — Ajustes guiados con modo básico y avanzado (P1, M)**

- **Historia.** Como coleccionista que no sabe qué es Prowlarr ni `host.docker.internal`, quiero que Ajustes me pregunte qué quiero conectar y me lleve de la mano, para configurar mis fuentes sin leer párrafos técnicos.
- **Problema (evidencia).** `/ui/ajustes` es una cuadrícula de siete tarjetas con párrafos largos en letra pequeña (fuentes, Comic Vine, Prowlarr, Transmission, aMule, Seguridad, Avisos) y todas al mismo nivel; las URL por defecto con `host.docker.internal` aparecen en primer plano.
- **Criterios de aceptación.**
  1. Entrada de inicio con objetivos en lenguaje del usuario («Quiero enriquecer mis tebeos», «Quiero que se descarguen solos», «Quiero un aviso al móvil», «Quiero protegerlo con contraseña»), cada uno abre solo lo necesario.
  2. Lo técnico (URLs, puertos, `host.docker.internal`, tokens) vive en una sección **Avanzado** plegada por defecto.
  3. «Probar conexión» devuelve una causa y un paso siguiente en español (reutiliza D9/A10), sin excepciones ni URLs en crudo.
  4. Cada tarjeta dice **en una línea** para qué sirve y si es opcional.
  5. Se mantiene el comportamiento de D11: guardar aplica al instante, los secretos nunca se devuelven en claro, y activar contraseña sin credencial sigue rechazándose (A6).
- **Fuera de alcance.** Cambiar el mecanismo de overrides en caliente.
- **Pruebas.** Cada objetivo abre los campos correctos; el modo avanzado conserva todos los campos; regresión de secretos y del guardarraíl de A6.
- **Dependencias.** D11, A6, A10, D9.

**U6 — Estado que dice la verdad, en llano (P1, S)**

- **Historia.** Como coleccionista, quiero que la pantalla de Estado me diga si debo preocuparme y qué hacer, sin términos internos, para fiarme de ella.
- **Problema (evidencia).** Aparece «Todo bien» en verde junto a un aviso «fichero /run/vpn-state/wg0.json ausente — el host aún no ha escrito el estado (o el timer no corre)» y una fila «VPN: Sin datos». El semáforo global contradice los parciales y el aviso usa una ruta interna.
- **Criterios de aceptación.**
  1. El semáforo global es el **peor** de los parciales: con «VPN: sin datos» no puede decir «Todo bien»; muestra «Atención».
  2. Cada aviso tiene tres partes: qué pasa, por qué importa y qué hacer, sin rutas internas en el texto principal (la ruta puede ir en un detalle plegado «Ver detalle técnico»).
  3. «Sin datos» se distingue de «sin protección»: el primero no implica riesgo, el segundo sí; los textos lo dicen.
  4. Se conserva la distinción de E6 (`unreachable` / `migration_required` / `schema_incompatible` / `ok`).
- **Fuera de alcance.** Cambiar cómo se calcula el healthcheck.
- **Pruebas.** Tabla de combinaciones de estados → semáforo y texto.
- **Dependencias.** E1, E6, D4.

**U7 — Navegación y vocabulario coherentes (P2, S)**

- **Historia.** Como coleccionista, quiero que cada nombre del menú signifique una sola cosa, para encontrar lo que busco sin probar a ciegas.
- **Problema (evidencia).** Hay ocho entradas planas; «Biblioteca» y «Mi biblioteca» suenan igual y la segunda es en realidad la auditoría (la página se titula «Revisión de mi biblioteca»). «Deseados», «Pendientes» y «Descubrir» no explican su relación.
- **Criterios de aceptación.**
  1. Un término por concepto en toda la UI y la documentación; «Mi biblioteca» pasa a un nombre que diga lo que hace (p. ej. «Revisión»).
  2. Las entradas se agrupan por tarea (Mi colección · Añadir · Sistema) o se justifica por escrito por qué siguen planas.
  3. El título de cada página coincide con su entrada de menú.
  4. Glosario de vocabulario de producto en `CLAUDE.md`.
- **Pruebas.** Test de plantillas: el título de cada ruta coincide con su enlace de menú.
- **Dependencias.** Ninguna.

**U8 — Revisión de biblioteca con resumen y prioridad (P2, M)**

- **Historia.** Como coleccionista con duplicados, quiero que la revisión de mi biblioteca me dé un resumen y ordene lo que más espacio recupera, para saber por dónde empezar.
- **Problema (evidencia).** La pantalla muestra 1.542 tebeos, 432 comparados a fondo, 6 carpetas repetidas y **200** duplicados exactos que liberarían 7,5 GB, pero en una lista larga sin resumen ni orden por ahorro, y el aviso «puede tardar un rato» no va acompañado de progreso.
- **Criterios de aceptación.**
  1. Un **resumen arriba**: GB recuperables, nº de grupos por tipo y fecha de la última revisión.
  2. Los grupos se ordenan por ahorro (mayor primero) y se pueden filtrar por tipo.
  3. Mientras se revisa hay un **progreso real** (archivos leídos / total), no solo un aviso.
  4. **Invariante de B16 intacta:** solo lectura. No hay botón de borrar ni de mover, ni se sugiere qué borrar; solo se ordena por ahorro, que es información, no una recomendación de acción.
  5. Las rutas largas se muestran legibles (nombre destacado, carpeta secundaria) y se pueden copiar.
- **Pruebas.** Servicio con grupos de distinto tamaño; test de que no se toca el disco (el de mtimes de B16 se mantiene).
- **Dependencias.** B16.

**U9 — UI utilizable en móvil y tablet (P1, M)**

- **Historia.** Como coleccionista que usa el móvil o la tablet en el sofá, quiero que la UI se adapte a pantalla pequeña, para revisar y aprobar sin ampliar ni desplazarme de lado.
- **Problema.** La visión del producto («desde el móvil o el sofá», C1) no está comprobada: todas las capturas son de escritorio ancho, con una columna central estrecha y mucho espacio lateral vacío.
- **Criterios de aceptación.**
  1. Probado a 360, 390 y 414 px de ancho y en tablet (768 px), en vertical y horizontal.
  2. Pendientes y Biblioteca en **una columna** en móvil, sin desbordes horizontales.
  3. Los objetivos táctiles cumplen el mínimo de WCAG 2.2 AA (24×24 px CSS) y, como objetivo de diseño del equipo, un tamaño cómodo mayor para los botones principales.
  4. El menú se pliega a un patrón móvil legible.
  5. Navegador de referencia incluido el Chromium de la propia Pi.
- **Pruebas.** Capturas por ancho como regresión visual manual; test de plantillas con `<meta viewport>` y sin anchos fijos en los componentes críticos.
- **Dependencias.** U1 (la parte más afectada), U4.

**U10 — Validar con coleccionistas antes de rediseñar (P1, S)**

- **Historia.** Como equipo, quiero observar a 3–5 coleccionistas reales resolviendo tareas en Pendientes y en el primer arranque, para decidir con datos qué rediseñar.
- **Por qué.** Este análisis es una revisión de expertos sobre capturas; encuentra problemas probables, no mide su gravedad real. El propio backlog ya aprendió que «antes de añadir automatismo sobre una heurística hay que medirla contra datos reales».
- **Criterios de aceptación.**
  1. Guion de tareas: «clasifica estos 14 archivos», «encuentra por qué no se descarga X», «di si tu sistema está bien».
  2. Métricas: tiempo por tarea, errores, abandonos y qué dicen en voz alta; muestra pequeña, sin pretensión estadística.
  3. Participantes con el perfil de «El Coleccionista» (no técnico, miles de CBZ/CBR), no desarrolladores.
  4. Resultado registrado como ficha §13 en `docs/design/` con decisión adoptar/adaptar/descartar por cada hallazgo de U1–U9 y su versión de la UI evaluada.
  5. Se hace **antes** de implementar U1 y U2 y no bloquea U4 y U6, que son correcciones objetivas.
- **Dependencias.** Ninguna.

#### Orden de ataque sugerido

1. **U4** (contraste, S) y **U6** (Estado, S): correcciones objetivas, baratas y sin riesgo de producto.
2. **U10** en paralelo: validar antes de invertir en U1 y U2.
3. **U1** y **U2** (P0): la mayor fricción y la primera impresión.
4. **U3**, **U5**, **U9** (P1).
5. **U7** y **U8** (P2).

**Regla de la épica:** ninguna historia de la U cambia la lógica de negocio. Reutilizan los servicios existentes (`ReviewService`, `Orchestrator`, `RuntimeSettingsService`, `LibraryAudit`); si una necesita lógica nueva, se registra aparte.

### Épica V — "La UI nueva llega a casa" (migración a la maqueta)

**Origen:** la maqueta `zascarr_maqueta_ui.html` (propuesta de UI del 2026-10-01, derivada de la revisión de UX que originó la Épica U). Esta épica es el **plan de migración** desde la UI actual (Jinja2 + HTMX + `web.css`) hasta esa propuesta, **sin big-bang**: cada historia es una PR que deja `main` desplegable y reversible.

**Punto de partida verificado** (listado del repo en `main`): 11 routers en `src/zascarr/web/` (`ajustes`, `auditoria`, `auth`, `dashboard`, `discovery`, `estado`, `legal`, `library`, `pendientes`, `series`, `wishlist`, más la fábrica `routes.py`) y **28 plantillas** en `web/templates/` (15 parciales HTMX y 13 páginas, `base.html` incluida). Los pesos relativos dan la medida del trabajo: `ajustes.html` (≈12,5 KB) es de largo la mayor; `auditoria`+`_auditoria_informe` (≈6 KB), `estado` (≈4,7 KB), `dashboard` (≈3 KB) y `pendientes` (≈2,5 KB) son medianas; `wishlist` y `base` son pequeñas. La épica se redactó **sin leer el contenido** de esas plantillas; **V0 (2026-10-01) lo ha inventariado** en `docs/design/ui-migracion.md` y ha corregido lo que no coincidía (ver «Notas de implementación de V0» más abajo). Las cifras y clases CSS concretas de las fichas se han confirmado o corregido allí.

**Restricciones que condicionan el diseño** (del propio repo): ADR-0001 (Jinja2 servido por FastAPI + HTMX vendorizado, sin SPA ni build de Node), `web.css` declara «sin JS nuevo» y «sin CDN», `AuthMiddleware` (A6) protege todo `/ui/*`, `crear_templates()` centraliza el entorno Jinja2 (lección de A6: no tocar decenas de `TemplateResponse`), y el patrón de pruebas es `FakeSession` + Postgres real cuando hay SQL.

#### Decisiones de la épica (a ratificar en el ADR 0005 de V0)

1. **Migración incremental por capas, sin interruptor de «UI vieja/nueva».** Dos UIs en paralelo duplicarían plantillas y pruebas en una app de un solo operador. Como **11 de las 13 «páginas» heredan de `base.html`** (las otras dos son la propia `base.html` y `login.html`, **autónoma**, que se trata aparte en V12), **primero cambian los cimientos** (tokens → componentes → shell) y **después, pantalla a pantalla**, el contenido. Cada PR mejora o deja igual; la vuelta atrás es `git revert` de esa PR o `scripts/rollback.sh`.
2. **Las URL no cambian.** `/ui/pendientes`, `/ui/wishlist`, `/ui/auditoria`… siguen igual; solo cambian las etiquetas («Por revisar», «Duplicados») y qué etiqueta cuelga de qué ruta. Evita romper marcadores, tests y enlaces del README. **`/estado` se queda en `/estado`** (no es `/ui/estado`: es una ruta de diagnóstico que se sirve con la BD caída, E6) y `/` sigue redirigiendo a `/ui/`.
3. **No se añade JavaScript propio nuevo.** Todo lo que la maqueta resuelve con JS se traduce a HTMX o CSS (tabla siguiente). Si algo no es traducible, se retira de la UI o se difiere; no se introduce JS. **El JS propio que ya existe** (el sondeo de `estado.html`, ~100 líneas, y el `onerror` de la portada en `pendientes.html`) **se retira cuando su pantalla se migra** (V9 y V5). *(La redacción original decía «cero JS propio» como si ya lo fuera.)*
4. **Cero lógica de negocio nueva en las plantillas.** La lógica de presentación (agrupar, mapear estados, derivar pasos) vive en funciones **puras** en `services/` con pruebas, no en Jinja.
5. **Sin migración de BD dentro de las historias de UI.** Ninguna historia de la épica añade tablas ni columnas. Si una necesita persistir algo trivial (p. ej. silenciar un aviso), usa las banderas de `runtime_settings` (`get_flag`/`set_flag`). **Si una garantía de integridad exige esquema** —p. ej. que la auditoría de V6a concluya que hace falta registrar los movimientos para reconciliarlos tras un fallo, o un `UNIQUE` en `wishlist`— **esa dependencia se separa** en su propia historia y PR previa, con su migración, su ficha y su definición de hecho, **y la historia de UI espera a ella**. Lo que no se hace es rebajar la garantía de integridad para que la historia «quepa» sin migración, ni meter esquema dentro de una PR de interfaz.
6. **Puerta de validación (G1).** U10 (probar con 3–5 coleccionistas) debe haberse hecho **antes de fusionar V5 y V6b**: son los dos rediseños con más riesgo de haber acertado el problema pero no la solución.

7. **Decisiones de producto cerradas (2026-10-01).** **(a) Un solo buscador:** el Inicio tiene **una** entrada principal «Buscar una serie» que lleva a **Descubrir**; **no se unifican** todavía la búsqueda en tu biblioteca y la externa. **Deseados conserva su búsqueda local**, claramente etiquetada («Añadir de las series que ya tienes»). **(b) Unir duplicadas:** **fuera de esta migración**. V8 agrupa **visualmente** por serie y muestra número, edición y estado para distinguir las peticiones; **no borra ni fusiona filas** automáticamente. **(c) Archivos sin número en un lote:** V6b permite **dejarlos pendientes y explica por qué**; **nunca** se rellena un `1` ni se convierte un rango (`144-158`) en un número para satisfacer el formulario.

#### De la maqueta a la implementación (qué se traduce y qué no)

| En la maqueta (JS) | En producción (sin JS propio) | Observación |
|---|---|---|
| Contadores del menú (`14`, `6`, punto de atención) | Fragmento HTMX `/ui/_nav/estado` cargado con `hx-trigger="load, every 30s"` | La base no consulta la BD. **Con la BD degradada (E6) `/ui/*` devuelve un 503 HTML y htmx 4 intercambia por defecto todo salvo 204/304**: el fragmento debe devolver vacío (no 503) y esa excepción se declara junto a `_RUTAS_DIAGNOSTICO`. Necesita un `contar_pendientes()` nuevo (hoy `pending_files` tiene tope 50 y no hay recuento) |
| Selección múltiple y barra de acciones | `<form>` con casillas + `hx-post` a `/ui/pendientes/seleccion` que devuelve la barra con el recuento | El servidor es la fuente de verdad del recuento |
| «Seleccionar grupo / todo» | `hx-post` que re-renderiza la lista con las casillas marcadas | Sin estado en el navegador |
| Diálogo de confirmación | Paso 2 server-side: `previsualizar` devuelve el fragmento de confirmación; `confirmar` ejecuta | La lista que ves es la que se ejecuta |
| «Deshacer» tras **ignorar** | Enlace `hx-post` a `recuperar` en la fila + pestaña «Ignorados» | Posible: `review_dismissed` es un indicador |
| «Deshacer» tras **asignar** | **No se ofrece** | Asignar mueve el fichero (`safe_move`) y crea el `Issue`; deshacerlo exige una operación inversa que hoy no existe. La salvaguarda es la confirmación previa. **La maqueta lo simula y no es fiel en esto** |
| Conmutador manual claro/oscuro | **Se difiere** | `web.css` ya respeta `prefers-color-scheme`; un conmutador exige JS y persistencia |
| Pestañas, objetivos de Ajustes | Enlaces/`hx-get` con parámetro (`?objetivo=`) | Estado en la URL: se puede enlazar y recargar |
| Barra de progreso de la revisión | Sondeo `hx-trigger="every 2s"` a un endpoint de progreso | **Requiere backend nuevo** (V11b) |
| Barra inferior móvil | Mismo HTML del menú, distinta maquetación por `@media` | Una sola fuente de navegación |
| Notificaciones temporales (toast) | Fragmento de aviso con desvanecimiento por animación CSS | El estado definitivo siempre es visible en la propia página |
| «Copiar comando» (Estado/VPN) | Comando en un bloque `<code>` con `user-select: all` | El portapapeles exige JS: se muestra seleccionable y no se copia solo |
| Selector «Quién puede entrar» (Ajustes → contraseña) | **No se ofrece**: Ajustes **informa** de la exposición efectiva (`seguridad` de `/api/health`) y dice «vuelve a ejecutar el instalador» | La app no puede cambiar su puerto (ADR 0004 / A11). **La maqueta lo simula y contradice la decisión** |
| «Unir duplicadas» (Deseados) | **Fuera de la migración** (decisión 7b): V8 solo **agrupa visualmente** | en `wishlist` los items manuales no tienen unicidad a propósito (solo `uq_wishlist_politica_numero`, parcial, para `origen='politica'`): unir exige borrar filas o más esquema (decisión 5) |
| «Silenciar aviso de VPN» | Indicador en `runtime_settings` (`get_flag`/`set_flag`) | Backend nuevo, sin migración |

| ID | Historia | Aceptación clave | P | Est |
|---|---|---|---|---|
| V0 | Como equipo, quiero un inventario de la UI actual y un ADR de migración, para migrar sabiendo qué se toca | Inventario plantilla→componentes, **línea base reproducible de capturas**, lista de contratos HTMX a conservar, ADR 0005 *(✅ Hecho, PR #60, `a81aae1`)* | P0 | S |
| V1 | Como coleccionista, quiero textos legibles en cualquier pantalla, para no forzar la vista (cimiento visual) | Tokens con contraste ≥ 4,5:1, alias que no rompen plantillas, tamaño mínimo y objetivo táctil, prueba automática *(✅ Hecho, PR #63, `741781d`)* | P0 | M |
| V2 | Como desarrollador, quiero una biblioteca de componentes CSS y macros Jinja, para que todas las pantallas se vean y se comporten igual | Botones, chips de estado, tarjetas, grupos, estado vacío, progreso, aviso; macros con pruebas *(✅ Hecho, PR #65, `b818e87`)* | P0 | M |
| V3 | Como coleccionista, quiero un menú claro y agrupado que funcione en móvil, para saber dónde estoy y dónde ir | Menú lateral + barra inferior, contadores por fragmento, `aria-current`, títulos coherentes *(✅ Hecho, PR #67, `fa858fe`)* | P0 | M |
| V4 | Como coleccionista recién instalado, quiero un Inicio que me guíe, para no ver ceros contradictorios | Servicio `PrimerosPasos` puro (**antes se extraen las 5 consultas de `web/dashboard.py` a `services/`**); checklist derivado del estado; una acción principal *(✅ Hecho: V4a PR #69, `266f490`; V4b PR #70, `03fb282`)* | P0 | **L** *(era M)* |
| V5 | Como coleccionista, quiero «Por revisar» compacto y agrupado, para revisar 14 archivos sin repetir el ritual | Lista compacta, nombre íntegro, sugerencia visible, agrupación, selección por HTMX | P0 | L |
| V6 | Como coleccionista, quiero asignar varios archivos de una vez con confirmación, para clasificar en minutos | **Dividida en V6a (servicio: lote con `commit` por archivo, número por fila, alias opcional —cambia B13—, auditoría previa de mover + sesión viva) y V6b (UI: previsualizar/confirmar, éxito parcial, sin «deshacer» engañoso, tras verificar htmx con 4xx)** | P0 | **L + L** *(era L)* |
| V7 | Como coleccionista, quiero ignorar con vuelta atrás, para no temer equivocarme | Pestaña «Ignorados», recuperar (**servicio y rutas nuevas: hoy `dismiss` no tiene inverso**), enlace «Deshacer» en la fila | P1 | **M** *(era S)* |
| V8 | Como coleccionista, quiero Deseados con estados honestos y duplicados agrupados | Función pura estado→(texto, paso), agrupado, aviso al duplicar, enlaces a la causa | P1 | M |
| V9 | Como coleccionista, quiero Estado que diga la verdad en llano | Semáforo = peor caso, textos «qué / por qué / qué hacer», detalle técnico plegado, silenciar VPN; **sustituye el JS de sondeo por HTMX sin depender de la BD (`/estado` es diagnóstico) y pinta `seguridad.atencion` (A11)** | P1 | **L** *(era M)* |
| V10 | Como coleccionista, quiero Ajustes por objetivos, para configurar sin leer jerga | `?objetivo=`, partes avanzadas plegadas, «probar conexión» con causa y paso, D11/A6 intactos | P1 | L |
| V11 | Como coleccionista, quiero Duplicados con resumen y orden por ahorro, para saber por dónde empezar | Presentación sobre el informe existente; progreso real como subhistoria V11b | P2 | M |
| V12 | Como coleccionista, quiero que Biblioteca, Descubrir, ficha de serie, login y aviso legal encajen con el resto | Restyle con los componentes de V2, sin rediseñar el flujo (**`login.html` no hereda de `base.html`; política de serie y candidatos tampoco tienen maqueta**) | P1 | **L** *(era M)* |
| V13 | Como coleccionista en móvil o tablet, quiero que todo funcione en pantalla pequeña | Verificación a 360/390/414/768 px, objetivos táctiles, foco y avisos tras cada intercambio HTMX | P1 | M |
| V14 | Como equipo, quiero cerrar la migración sin restos, para no arrastrar CSS ni plantillas huérfanas | Limpieza, docs, capturas nuevas, CHANGELOG/BACKLOG, comprobación de clases CSS sin uso | P2 | S |

#### Fichas detalladas de la Épica V

**V0 — Inventario y ADR 0005 de migración (P0, S)**

- **Historia.** Como equipo, quiero un inventario de la UI actual y una decisión escrita de cómo migrarla, para que ninguna historia posterior dependa de supuestos no comprobados.
- **Estado: ✅ Hecho (2026-10-02)** — PR #60, fusionada en `a81aae1` tras tres rondas de revisión (la última, del aislamiento del ensayo). ADR 0005 **Aceptado**.
- **Alcance.** Documentación y capturas; **no cambia código de la aplicación**.
- **Criterios de aceptación.**
  1. `docs/design/ui-migracion.md` con una fila por plantilla (28): ruta que la sirve, plantilla padre, parciales HTMX que usa, endpoints `hx-*` que dispara y clases de `web.css` que emplea. Se obtiene **leyendo** las plantillas, no de memoria.
  2. **Contratos HTMX a conservar**: por cada endpoint de `/ui/*` que devuelve un fragmento, su URL, método, campos del formulario y el fragmento esperado. Es la lista de lo que no se puede romper.
  3. **Línea base reproducible** de la UI actual en `docs/design/ui-baseline/`, sobre el commit inventariado y **sin modificar la UI**: entorno aislado con Postgres y datos de prueba (descargas y avisos externos desactivados); pantallas principales, ficha de serie, login y aviso legal, en escritorio y móvil, **indicando viewport, tema, zoom, navegador y commit**; un caso de **asignación con colisión (409)** que registre el cuerpo recibido, el intercambio HTMX y lo que queda visible en la tarjeta; y `/estado` con la BD disponible y caída, sin perder su función de diagnóstico. Incluye el procedimiento para repetirla.
  4. La maqueta se commitea como `docs/design/maqueta-ui.html`, con la nota explícita de que **simula** deshacer-tras-asignar y el conmutador de tema (ver la tabla de traducción).
  5. ADR 0005 en `docs/adr/` con las seis decisiones de la épica, estado «Propuesto» hasta que se apruebe (**aprobado el 2026-10-02**).
  6. **Resultado comprobado (no decisión pendiente):** la página estática de `/` ya no existe; `GET /` redirige con 307 a `/ui/` (`main.py`). No hay nada que unificar. Las dos pantallas existentes son `/ui/` (métricas) y `/estado` (salud, que **se conserva en `/estado`** y se sirve con la BD caída).
- **Pruebas.** No aplica. Revisión humana del inventario contra `grep` de `hx-` y de clases.
- **Riesgos.** Que el inventario descubra clases o parciales compartidos que obliguen a reordenar V2/V3.
- **Notas de implementación de V0 (2026-10-01):** inventario terminado; **línea base de capturas hecha** en `docs/design/ui-baseline/` (37 capturas + datos, reproducible con `README.md`; Chrome 154, datos sintéticos, escritorio 1280×800 y móvil 390×844, claro y oscuro). El inventario se hizo leyendo el código en `main` (`ab49c76`); las tablas de rutas y plantillas se **generaron del AST** de los routers y de las plantillas, no a mano. Entregables: `docs/design/ui-migracion.md` (28 plantillas, 48 rutas, contratos, maqueta frente a realidad, estimaciones), `docs/design/maqueta-ui.html` (copia sin modificar, con la lista de lo que **simula** en el inventario) y `docs/adr/0005-migracion-de-la-ui.md` (**Propuesto**). Lo que corrige de la épica: **(1)** Estado vive en `/estado`, no `/ui/estado`, y debe servirse con la BD caída; **(2)** la «página estática `/`» ya no existe (`/` redirige 307 a `/ui/`): **el criterio 6 queda resuelto sin unificar nada**; **(3)** `estado.html` ya lleva ~100 líneas de JS y `pendientes.html` un `onerror`: «cero JS propio» pasa a «sin JS propio nuevo»; **(4)** el menú actual no coincide con las pantallas (la rejilla `/ui/biblioteca` no está en el menú); **(5)** htmx 4.0.0 intercambia por defecto todo salvo 204/304 y **está verificado** en la línea base que un `409` de `asignar` **sustituye la tarjeta por el JSON en crudo** (defecto ya existente en producción; el estado real es correcto); **(6)** Pendientes tiene tope de 50 y ningún recuento; **(7)** asignar exige número por archivo y la maqueta no lo pide; **(8)** el alias se aprende siempre (B13) y la casilla de la maqueta lo haría opcional; **(9)** mover + `flush` con la sesión viva sigue sin auditar (`CLAUDE.md` §3.1.2) y un lote lo multiplica; **(10)** ignorar no tiene inverso; **(11)** la maqueta ofrece en Ajustes un selector de exposición de red que **contradice A11/ADR 0004** (Ajustes informa, no cambia puertos); **(12)** `seguridad.atencion` de `/api/health` es la señal para el Estado nuevo; **(13)** «un solo buscador» junta dos contratos (lo tuyo y fuentes externas); **(14)** el panel lleva su lógica en el router; **(15)** «hemos leído tu biblioteca» es la adopción, una acción explícita. Verificado por cálculo: las cifras de contraste de V1 son correctas, y **la propia maqueta falla en un par** (insignia `.badge.hot` en oscuro, 3,38:1).
- **Seguimiento separado de V0 (no son parte de la épica):** **(a)** el `409` de `asignar` que sustituye la tarjeta por JSON en crudo en la ruta *individual* (PR propia, con su test de regresión; V6b ya no depende de ello); **(b)** el defecto operativo de la BD caída con la app en marcha (sección «V0: la BD cae con la app en marcha»), con medición previa de qué rutas fallan; **(c)** el marcador de conflicto `>>>>>>> 2453d3b` heredado del commit `e7a92eb` (PR #48), en una limpieza independiente. El aislamiento del ensayo (`docs/design/ui-baseline/ensayo.sh`, `tests/test_ensayo_aislamiento.py`) quedó cubierto en la propia PR #60.

**V1 — Tokens, contraste y tamaños en `web.css` (P0, M)**

- **Historia.** Como coleccionista, quiero que cualquier texto de ZascArr se lea sin esfuerzo, para no perder información en una tablet o con poca luz.
- **Contexto medido.** `--ink-faint` da 3,05:1 sobre `--paper` y 2,82:1 sobre `--paper-2` (WCAG AA pide 4,5:1 para texto normal [web:967]); `--cyan` 2,84:1 y `--ok` 3,83:1 como texto; en oscuro `--ink-faint` roza el límite (4,47 y 4,14:1). La maqueta usa valores ya calculados: `--faint` #63636b (5,37:1), `--cyan-t` #0a6a96, `--ok-t` #1f6b43, `--warn-t` #a8321f, `--amber-t` #7a5a00, y en oscuro #9c9aa0, #5cc4f0, #5fd096, #f58a80, #ffd23f.
- **Criterios de aceptación.**
  1. Se **separan** colores de relleno y colores de texto: `--cyan`/`--ok`/`--warn` siguen para bordes y fondos; se añaden `--cyan-t`/`--ok-t`/`--warn-t`/`--amber-t`/`--mag-t` para texto, con valores para claro y oscuro.
  2. `--ink-faint` **conserva su nombre** (alias) y cambia de valor, para no tocar plantillas. Un `grep` documentado lista los usos de `color: var(--cyan|ok|warn)` sobre texto y se migran a las variantes `-t`.
  3. Todo texto normal ≥ 4,5:1 y texto grande ≥ 3:1 en ambos temas; bordes de campos e iconos de estado ≥ 3:1.
  4. Tamaño mínimo de texto informativo **14 px** (decisión de producto, validada con U10; WCAG no fija un mínimo). Las reglas `.72rem`–`.8rem` de la hoja se suben.
  5. Los controles interactivos tienen una altura mínima de 40 px y las casillas 24 px (mínimo de WCAG 2.2 AA).
  6. El estado no se transmite solo por color.
  7. **Prueba automática** sin navegador (`tests/test_web_css_contraste.py`): lee las variables de `web.css`, calcula la razón de contraste de los pares declarados (texto×fondo) en ambos temas y falla por debajo del umbral.
- **Fuera de alcance.** Cambiar la paleta o la tipografía de cartel.
- **Dependencias.** Ninguna. Es la primera por ser barata y no destructiva.
- **Verificación.** Capturas antes/después de las siete pantallas; revisión en navegador real contra Postgres real (práctica del repo).
- **Estado: ✅ Hecho (2026-10-02)** — PR #63, fusionada en `741781d` tras dos rondas de revisión (la regresión de Deseados en móvil y el alcance de la prueba de contraste). Desbordes preexistentes que **pasan a V13**: ficha de serie (413 px) y aviso legal en texto (409 px) a 390 px; medir además a 320 px CSS.
- **Notas de implementación de V1 (2026-10-02):** solo `web.css` + `tests/test_web_css_contraste.py` (77 casos); **ninguna plantilla**. **(1)** La prueba lee la hoja, resuelve `var()`, `#hex` y `color-mix()` y calcula el contraste de **todo par que la hoja determina** (550 pares entre claro y oscuro, incluidos los fondos de contexto `--paper`, `--paper-2`, `--caption-bg` y las dos mezclas de `color-mix`), exigiendo **4,5:1 a todo texto** (más estricto que el 3:1 del texto grande, a propósito); 3:1 para foco, bordes e iconos. Contra el CSS anterior **66 de 77 casos fallan**. **(2)** Lo que la medición destapó y la ficha no decía: en oscuro los botones amarillos llevaban **texto claro (1,23:1)** porque `--ink` es claro y el color venía de otra regla (`button` + `--btn-bg`): un recorrido regla a regla no lo veía, el par `--on-yellow` lo arregla; insignias verde/rojo en oscuro a 2,31:1 y 2,89:1; foco cyan a 2,84:1. **(3)** Añadidos más allá de la lista de la ficha, necesarios para cumplirla: `--on-yellow`, los pares sólidos `--ok-solid`/`--warn-solid` con su `--on-*`, el par `--hot`/`--on-hot` (el de la maqueta daba 3,38:1 en oscuro; aún sin clase que lo use, lo estrena V3), el color de `::placeholder`, `✓` y borde discontinuo para no depender solo del color, y borde de tinta en los puntos de estado. **(4)** La paleta y la tipografía de cartel no cambian: los cinco rellenos conservan su valor (lo comprueba la prueba). **(5)** Antes/después en `docs/design/ui-v1/` (9 capturas + tabla de contraste calculada). **(6)** **Regresión de V1, corregida en V1 (revisión de la PR #63):** el texto mínimo de 14 px empeoraba el desborde de Deseados en móvil (731 → 756 px). Causa medida: `.wishlist-row` era `flex` **sin `flex-wrap`**. Arreglo mínimo: `flex-wrap: wrap`, base del título y panel de candidatos en línea propia solo si tiene contenido; a 390 y 320 px la página ya no desborda (390 y 320 de ancho) y a 1280 px la captura es idéntica. Siguen desbordando la ficha de serie (413) y el aviso legal en texto (409), que ya lo hacían: V13. **(7)** **Alcance de la prueba:** es una heurística por reglas, no certifica el renderizado ni resuelve la cascada/herencia del DOM; ningún color que no sepa resolver se omite en silencio (falla salvo exclusión con motivo; la lista está vacía) y una regresión lo demuestra (mutando el comprobador fallan 6 casos).

**V2 — Componentes CSS y macros Jinja (P0, M)**

- **Historia.** Como desarrollador, quiero componentes reutilizables, para que Pendientes, Deseados, Estado y Duplicados compartan botones, chips y tarjetas en vez de reinventarlos.
- **Criterios de aceptación.**
  1. Componentes en `web.css` con los nombres de la maqueta: `.btn` (+`.primary`, `.ghost`, `.sm`), `.chip` (+`.ok`, `.warn`, `.amber`, `.info`), `.card`, `.group`/`.ghead`, `.caption`, `.progress`, `.empty`, `.hero-state`, `.toast`.
  2. Los nombres de clase actuales **siguen funcionando** durante la migración (alias o reglas compartidas); se retiran en V14, no antes.
  3. `templates/_componentes.html` con macros `chip(estado, texto)`, `estado_vacio(titulo, texto, accion)`, `grupo(titulo, recuento)` y `aviso(tipo, texto)`.
  4. `crear_templates()` registra las macros disponibles para todas las plantillas sin tocar los `TemplateResponse`.
  5. Los chips mapean **un estado → un aspecto**, definido una sola vez (tabla estado→clase en un módulo, no en cada plantilla).
  6. Accesibilidad: el foco visible se conserva; `:focus-visible` con contraste ≥ 3:1; `prefers-reduced-motion` desactiva transiciones.
  7. Los fragmentos que cambian tras una acción HTMX van en una región `aria-live="polite"`.
- **Pruebas.** Cada macro se renderiza con sus variantes y se comprueba el HTML (clase, texto, atributos ARIA).
- **Dependencias.** V1.
- **Estado: ✅ Hecho (2026-10-02)** — PR #65, fusionada en `b818e87` tras dos rondas de revisión (la segunda corrigió un fallo real: las macros como globales sueltas pintaban `<Macro 'aviso'>` en cada guardado de Ajustes; ahora van bajo `ui`). Nadie usa aún los componentes: los estrena V3.
- **Notas de implementación de V2 (2026-10-02):** CSS + `web/componentes.py` (estado→aspecto, una sola vez) + `templates/_componentes.html` (6 macros: `chip`, `aviso`, `grupo`, `estado_vacio`, `progreso`, `region_viva`) expuestas **bajo un único nombre, `ui`** (`ui.chip(...)`), registradas en `crear_templates()`; **ninguna pantalla migrada, ni router ni `TemplateResponse` tocados**. **(1)** `.empty-state` (ya existía) es el componente de estado vacío y `.empty` sigue siendo el texto en cursiva: la ficha pedía `.empty`, pero está en 7 plantillas con otro significado. **(2)** `.btn-primary` y `.btn.primary` comparten regla (alias); las 143 clases anteriores siguen existiendo (prueba). **(3)** Iconos con los chips y avisos para no depender solo del color; solo `warn` es `role="alert"`. **(4)** `<progress>` nativo, `role="group"`, `.toast` en el flujo con desvanecimiento por CSS. **(5)** Tokens nuevos `--ok-bg`/`--warn-bg`/`--amber-bg`/`--info-bg`. **(6)** **Fallo corregido en la revisión de la PR #65:** la primera versión registraba las macros como globales sueltas; un global `aviso` hacía verdadero el `{% if aviso %}` de `_ajustes_guardado.html` y **pintaba `<Macro 'aviso'>` en cada guardado de Ajustes** (reproducido). Lo vio la revisión, no las pruebas ni las capturas: la prueba de colisiones solo comparaba nombres y las capturas de páginas no pasan por los fragmentos. Arreglo: un único espacio de nombres `ui` y regresión que compara el HTML con el del entorno anterior a V2 (con la versión anterior fallan 10 casos); **no hace falta tocar Ajustes**. **(7)** Verificación: 109 casos de componentes + 112 de contraste; catálogo generado con las macros reales (`docs/design/ui-v2/`) en claro/oscuro y escritorio/móvil; no regresión: 25 de 30 capturas existentes idénticas píxel a píxel, las 5 restantes difieren solo en una hora. Límites: nadie usa aún los componentes (V3+ los estrena); la no regresión de **fragmentos** HTMX solo está probada para las dos plantillas de Ajustes; el desvanecimiento del toast solo se comprueba por prueba, no en captura.

**V3 — Shell nueva: menú agrupado, barra inferior y contadores (P0, M)**

- **Historia.** Como coleccionista, quiero un menú con nombres claros y agrupado por tarea que se adapte al móvil, para saber siempre dónde estoy.
- **Criterios de aceptación.**
  1. `base.html` se reescribe con menú lateral en escritorio y barra inferior en pantallas estrechas, **con el mismo marcado** (la diferencia es CSS por `@media`).
  2. Grupos: Mi colección (Inicio, Por revisar, Biblioteca, Duplicados), Añadir (Descubrir, Deseados), Sistema (Estado, Ajustes). Etiquetas según U7; **las URL no cambian**.
  3. Enlace «Saltar al contenido», `aria-current="page"` en la entrada activa y un `<h1>` por página.
  4. Los contadores (pendientes, deseados, punto de atención de Estado) se cargan con un fragmento `GET /ui/_nav/estado` vía `hx-trigger="load, every 30s"`. La plantilla base **no consulta la BD**.
  5. Con la BD degradada (E6) o ante cualquier fallo, el fragmento devuelve vacío y la página sigue funcionando; nunca 500.
  6. El fragmento queda protegido por `AuthMiddleware` como el resto de `/ui/*` (A6) y no filtra datos si no hay sesión.
  7. El título de cada página coincide con su entrada de menú (U7); lo comprueba un test que recorre las rutas.
  8. «Cerrar sesión» y el aviso legal conservan su comportamiento actual.
  9. **Fragmento con la BD degradada (E6):** hoy el middleware responde un **503 HTML** a cualquier `/ui/*` que no sea de diagnóstico, y **htmx 4.0.0 intercambia por defecto todo salvo 204/304**: sin tratamiento, ese HTML se pintaría dentro del menú. El fragmento debe declararse **junto a `_RUTAS_DIAGNOSTICO`** y, con la BD caída, responder **204** (que htmx no intercambia) o un fragmento vacío con 200 — se elige y se **verifica en el navegador**; nunca un 5xx con cuerpo HTML. **Medido en la línea base:** con la BD caída y la app **ya en marcha**, **`/ui/` (el panel)** responde un **`500` de texto plano**, no el `503` de E6 (que solo ocurre si la app arrancó sin BD); las demás rutas `/ui/*` **no se midieron** (se deduce que igual) y el fragmento debe cubrir, como requisito, **cualquier** excepción, no solo el modo degradado. Defecto operativo registrado aparte (sección «V0: la BD cae con la app en marcha»), no parte de esta historia.
  10. **Tratamiento HTMX del fragmento:** `hx-trigger="load, every 30s"` con `hx-swap="innerHTML"` sobre un contenedor propio; un fallo de red o un `4xx`/`5xx` no puede dejar el menú sin enlaces (los contadores son un añadido, la navegación está en el marcado de `base.html`).
  11. **Se actualizan las pruebas que fijan el menú actual** (no se esquivan): `tests/test_web_dashboard.py` (l. 109–110: `'<nav class="topnav">'` y `'href="/estado">Estado</a>'`) y `tests/test_web_discovery.py` (l. 62). La ficha deja constancia de que cambian a propósito y por qué.
  12. `/estado` **sigue en `/estado`** y su entrada de menú apunta ahí.
- **Pruebas.** Todas las páginas incluyen exactamente un `aria-current`; el fragmento con BD vacía, con datos y con BD degradada; auth con y sin sesión.
- **Riesgos.** `every 30s` en una Pi: el fragmento debe ser dos `COUNT` baratos o leer un caché de proceso. Medir antes de fusionar.
- **Dependencias.** V1, V2.
- **Estado: ✅ Hecho (2026-10-03)** — PR #67, fusionada en `fa858fe` tras una ronda de revisión con un único bloqueo (el `204` del fragmento solo cubría las consultas, no el ciclo completo de la sesión de BD; ver nota 3 y 6). **Límite que conviene no malinterpretar:** los cinco segundos acotan la **espera de la petición**, no la vida de la tarea ni la liberación de su conexión; con la BD congelada la tarea sigue en vuelo hasta que la conexión responda o el sistema operativo la cierre, limitada a **una** a la vez. No es una limpieza garantizada en cinco segundos. Pendiente: comprobación de accesibilidad con los dos `aria-current` del DOM en otros navegadores; coste del sondeo medido fuera de la Pi.
- **Notas de implementación de V3 (2026-10-03):** `web/menu.py` (datos puros: 8 entradas, 3 grupos, `entrada_activa`), macro `ui.menu`, fragmento `GET /ui/_nav/estado` (`web/navegacion.py`, plantilla `_nav_contadores.html` con intercambios fuera de banda), `services/navegacion.py` (`contadores`), `ReviewService.count_pending()` y `WishlistService.count_active()` con **el mismo filtro que las listas** (`_condiciones_pendientes`), `base.html` reescrito, CSS §3b, títulos y `<h1>` alineados con el menú. **(1)** **Cuatro entradas en la barra inferior + «Más»**, no las cinco de la maqueta: con 14 px mínimos (V1) seis columnas no caben a 320 px; «Más» es un `<details>` nativo y sus entradas salen **dos veces en el DOM** (dos `aria-current` en HTML, uno visible, comprobado). **(2)** **Los enlaces nunca vienen del fragmento:** marcadores `hidden` + `hx-swap="none"` + intercambios fuera de banda; ningún enlace cuelga de un elemento htmx (prueba). **(3)** **`204` ante cualquier fallo, en todo el ciclo de la sesión de BD** (crear, abrir, consultar, liberar, seguridad, renderizado y plazo; además de BD caída en marcha, arranque degradado y sesión caducada), con **sesión propia de solo lectura (no `get_db`) y sin `commit`**, y **no es ruta de diagnóstico**: en `services/auth.py`, `RUTAS_FRAGMENTO_SILENCIOSO` hace que el middleware responda `204` vacío sin sesión (no redirige) y en E6 (no `503` HTML), sin consultar la BD. **(4)** El punto de **Estado = solo `seguridad.atencion` (A11)**; V9 lo amplía. **(5)** Cambios de nombre: Pendientes → Por revisar, Lista de deseos → Deseados, Mi biblioteca → Duplicados, Dashboard → Inicio; **dos pruebas que fijaban `<nav class="topnav">` se actualizan a propósito**. **(6)** **BD congelada** (revisión de la PR #67; lo destapó la verificación real, no los falsos): un `asyncio.timeout` alrededor de todo **no respondía** porque la liberación de la sesión también se cuelga; ahora el trabajo va en **una tarea compartida** y la petición solo espera 5 s (`204`), sin apilar sondeos. **Medido:** fragmento **46 ms de mediana con 50.000 ficheros** (14 ms en el ensayo), `EXPLAIN` del recuento 26 ms; no medido en la Pi. **(7)** Verificación en navegador real (Chrome 154, `docs/design/ui-v3/`): menú y `aria-current` en 8 pantallas × escritorio/390/320 sin desborde, las 4 secciones de «Más» alcanzables, teclado (salto, orden, foco visible, Enter/Espacio), sondeo a los ~35 s, fallo de red, **BD caída tras cargar** (`204`, contadores y enlaces conservados), **arranque sin BD** (`/estado` 200 con menú, fragmento `204`), **sesión caducada** en mitad del uso (`204`, sin redirigir), login y logout. **(8)** Encontrado y corregido al verificar: el contenido se encogía en la rejilla (736 vs 1.036 px), el contador pisaba el icono, «Deseados» no cabía a 320 px; y dos fallos de la herramienta de captura (desplazamiento suave, teclado sintético). **(9)** Efecto colateral: Ajustes de escritorio pasa de 4 a 3 columnas de tarjetas (más alta). Límites: sin probar en la Pi ni en Firefox/Safari; el punto de Estado es solo seguridad; `/ui/*` con la BD caída en marcha sigue en `500` (defecto aparte).

**V4 — Inicio con primeros pasos y contadores honestos (P0, L)**

- **Historia.** Como coleccionista recién instalado, quiero que el Inicio me diga qué hacer primero, para llegar a ver mi colección ordenada sin saber nada de la arquitectura.
- **Criterios de aceptación.**
  1. Nuevo `services/primeros_pasos.py` con una función **pura** que recibe un resumen (nº de ficheros registrados, nº sin clasificar, nº de series, fuentes activas, aviso legal aceptado) y devuelve la lista de pasos con su estado (`hecho`, `siguiente`, `opcional`, `bloqueado`) y el paso principal.
  2. Si no hay catálogo, **no se muestra** el porcentaje de completitud ni «0 %»; se explica cuándo aparecerá.
  3. Los números salen de **un único servicio** compartido con el resto de pantallas; no se recalculan en la plantilla.
  4. La cifra «tebeos encontrados» procede del último informe de la revisión (B16) o, si nunca se ha ejecutado, del recuento de ficheros registrados, y la etiqueta lo dice. No se afirma que se haya escaneado el disco si no ha ocurrido.
  5. Una sola acción principal visible; los pasos opcionales están marcados como tales.
  6. **Una única entrada principal «Buscar una serie» que lleva a Descubrir** (decisión de producto 7a): el formulario hace `GET /ui/descubrir?q=…` y Descubrir **prellena la caja y lanza la búsqueda al cargar** (cambio mínimo y probado en `web/discovery.py`). **No** se unifica con la búsqueda local; su propósito va escrito en la pantalla.
  7. Si hay archivos por revisar, el paso lo cuenta con el número real (`contar_pendientes()`, que no depende del tope de 50 de `pending_files`) y enlaza a Por revisar.
  8. **Antes** de reutilizarlas, las cinco consultas de `web/dashboard.py` (series, series con archivos, números importados, huecos, últimas series) se **extraen a un servicio** compartido sin cambiar ninguna cifra (los tests de `test_web_dashboard.py` y `test_dashboard.py` siguen en verde). La plantilla no recalcula nada.
  9. El paso «Hemos leído tu biblioteca» se deriva de `LibraryAdopter.should_run()` (la adopción es una **acción explícita**, B11) y del último informe de duplicados guardado en `ImportRun` (`details.kind == "audit"`); sin informe no se afirma «432 comparados».
- **Pruebas.** Matriz de la función pura (vacío; sin series con pendientes; todo configurado; sin aviso legal; BD degradada); la plantilla con cada estado.
- **Riesgos.** Definir mal el origen de las cifras vuelve a producir contradicciones. La regla es una sola fuente de verdad.
- **Dependencias.** V2, V3.
- **Estado: ✅ Hecho (2026-10-03)** — en dos PR: V4a (#69, `266f490`, extracción sin cambiar cifras) y V4b (#70, `03fb282`, Inicio guiado), esta última tras tres rondas de revisión (series distintas en lugar de peticiones; la acción recomendada no puede quedar plegada y el botón «Buscar» heredaba el amarillo global; capturas del Inicio que eran de otra pantalla). **Pendiente, fuera de V4:** (1) los tres fallos de Postgres real anotados al cerrar V4 **se diagnosticaron y no eran defectos de producción** (ver `docs/design/diagnostico-postgres-pruebas.md`): una prueba incompatible con las demás sobre la misma BD y dos con una precondición no escrita (más un choque con `PYTHONPATH` que mi propia invocación provocaba, de modo que «tres fallos en `main`» sobrestimaba lo real: era uno de diseño de la prueba); corregidos solo en `tests/`; **cerrado** con PR #72 (`ab070cc`, ciclo de vida de las bases de pruebas) y PR #73 (`5595518`, job de CI): la CI las ejecuta en un job propio con Postgres real (`Pruebas con Postgres real`, 170 pruebas ejecutadas en `main`), que falla si se saltan o si hay menos de 150. **Distinciones que conviene no perder:** 1.795 es la suite completa con Postgres de la investigación local; 170 es la selección que ejecuta el job (los ficheros que mencionan `TEST_DATABASE_URL`); el mínimo de 150 es una salvaguarda contra una selección vacía o incompleta, **no** garantiza que una prueba de integración futura quede incluida (si no menciona `TEST_DATABASE_URL`, no entra). **Pendiente, fuera de las PR:** hacer el check `Pruebas con Postgres real` **obligatorio** en las protecciones de `main` (lo recomienda la revisión; requiere a quien tenga permisos; hasta entonces es condición de revisión en cada PR pertinente); (2) el coste del recorrido de disco de `LibraryAdopter.estado()` (solo en instalación nueva, hasta el primer cómic) **sin medir** en la Pi ni en un montaje de red; (3) sin Firefox/Safari. **Puerta G1:** V5 y V6b no se fusionan antes de U10; V6a (auditoría y servicio de lotes) puede avanzar por separado.
- **Partición (2026-10-03):** V4 se entrega en dos PR, como pide el criterio 8 («antes de reutilizarlas»). **V4a** extrae las consultas **sin cambiar ninguna cifra**; **V4b** añade `PrimerosPasos` y el Inicio guiado.
- **Notas de implementación de V4a (2026-10-03):** `services/resumen.py` (`resumen_biblioteca(db) → ResumenBiblioteca`, dataclass inmutable) con las cinco consultas movidas tal cual, **en el mismo orden** (los tests de `test_web_dashboard.py` fijan la cola y siguen **sin tocarse**); `web/dashboard.py` pasa a router fino. `porcentaje_completitud` sigue siendo `0` sin catálogo (idéntico a hoy): **distinguirlo de un 0 % real es V4b** (criterio 2). **No-regresión comprobada contra el router anterior:** 300 escenarios aleatorios (0-6 series, fuentes mezcladas, huecos, últimas) dan el mismo contexto de plantilla, campo a campo. Pruebas nuevas: `tests/test_resumen.py` (7). Sin cambios de plantilla, de CSS ni de HTML.
- **Notas de implementación de V4b (2026-10-03):** `services/primeros_pasos.py` (función **pura** `calcular_primeros_pasos(EstadoInicio) → PrimerosPasos`), `services/inicio.py` (reúne el estado; **una fuente por dato**), `services/resumen.py` corregido, `LibraryAdopter.estado()`, `orchestrator.hay_fuente_de_busqueda()` (la definición de «fuente activa» de D9, reutilizada y no reinventada), `?q=` en Descubrir, plantilla y CSS §15b. Ficha: `docs/design/benchmark-V4-inicio.md`. **(1)** Cuatro pasos —*Registra tu biblioteca*, *Revisa N sin clasificar*, *Elige series* (opcional), *Conecta cómo descargar* (opcional)— con estados `hecho / siguiente / pendiente / opcional / bloqueado`. **`pendiente` es un quinto estado respecto a la ficha**: sin él, dos pasos obligatorios por hacer a la vez obligarían a elegir entre dos «siguiente» o a llamar «bloqueado» a algo que sí se puede hacer. **(2)** **Auditoría ≠ adopción:** el informe de duplicados (`ImportRun.details.kind == "audit"`) solo aporta fecha y cifras (`files_scanned`, `files_hashed`) al texto; el estado del paso sale de `LibraryAdopter.estado()` (marcador explícito de B11). Un informe sin adopción **no** marca hecho (prueba exhaustiva sobre todas las combinaciones). **(3)** **Completitud:** ya no es `números que hay / suma de total_issues de todas las fuentes`. Solo cuenta series con recuento de **grapas** acreditado (`UNIDAD_DE_GRAPA`); **sin ninguna, no hay cifra** (no «0 %») y se explica cuándo aparecerá. «0 huecos» siempre va con cuántas series no se pudieron calcular. Se retiran las consultas de `total_issues` y de `issues_importados` y la tarjeta «Actualizadas recientemente» (era `len(lista topada a 10)`). **(4)** Cada cifra dice su procedencia: «encontrados al mirar tu disco el …» (informe) o «registrados · no hemos mirado el disco»; nunca se afirma un escaneo que no ocurrió. Sin nada registrado no hay tarjetas (14 encontrados junto a «0 por revisar» eran ceros contradictorios; lo vio la verificación en navegador, no las pruebas). **(5)** Una sola acción principal: el primer paso `siguiente` o, si no queda ninguno obligatorio, el primer opcional con enlace; la caja «Buscar una serie» (`GET /ui/descubrir?q=`, prellena y lanza la búsqueda al cargar; su propósito va escrito) no es un segundo botón principal. Con lo obligatorio hecho, la lista se pliega. **(6)** Verificación en navegador real (`docs/design/ui-v4/`): recorrido completo de instalación nueva con la interfaz (sin registrar → informe → registrada → todo clasificado → vacía), claro/oscuro, 390 y 320 px sin desborde, un botón primario en cada estado, búsqueda de extremo a extremo. **(7)** Pruebas: `test_primeros_pasos` (31, matriz + invariantes), `test_inicio` (11), `test_resumen` (8), `test_web_dashboard` (30), `test_wishlist_series_pg` (4), `LibraryAdopter.estado` (5) y `?q=` (5). **(8) Revisión de la PR #70:** (a) «Sigues N series» contaba **peticiones** de Deseados (5 para 3 series): ahora `WishlistService.count_active_series()` (DISTINCT sobre `coalesce(series_id, issue.series_id)`, sin retiradas) con regresión en Postgres real (`test_wishlist_series_pg.py`: duplicada, por número, retiradas) y el contador del menú **no cambia de significado**. (b) Con lo obligatorio hecho la lista se plegaba **con la acción recomendada dentro**: existía en el HTML pero no se veía ni se alcanzaba con el teclado; ahora queda fuera del bloque plegado y la verificación en navegador comprueba **visibilidad, Tab y destino**, no `.btn.primary`. (c) Quitar `.primary` no hacía secundario el botón «Buscar» (`button[type=submit]` es amarillo): regla `.neutro` y comprobación del color calculado. (d) El texto de descargas ya no promete que Estado diagnostique ("el motivo aparece en Deseados"). (e) Los huecos se presentan como calculados «según su recuento de grapas y la numeración actual», no como acreditados por venir de Comic Vine. **Límites:** el coste del recorrido de disco de `estado()` (solo en instalación nueva, hasta el primer cómic) no está medido en un disco en red ni en la Pi; «fuente activa» significa **activada en Ajustes**, no que conteste; sin Firefox/Safari.

**V5 — «Por revisar» compacto, agrupado y con selección por HTMX (P0, L)**

- **Historia.** Como coleccionista con decenas de archivos sin clasificar, quiero verlos agrupados, con el nombre completo y la sugerencia a la vista, para resolver el grupo entero de un vistazo.
- **Criterios de aceptación.**
  1. Nueva función pura `agrupar_pendientes(archivos)` en `services/`: agrupa por la clave de título normalizada y, si existe, la edición (`edition_kind`) que ya produce `naming.py`; lo que no encaja va a «Otros». Determinista y con orden estable. Es **ayuda visual**: no decide la serie.
  2. La plantilla muestra nombre **íntegro** (sin truncar), lo detectado y la sugerencia de B12 con su puntuación y el botón «Sí, es esta»; el hueco de portada no se reserva si no hay miniatura.
  3. Casillas en un `<form>`; cada cambio dispara `hx-post` a `/ui/pendientes/seleccion` y el servidor devuelve la barra de acciones con el recuento. Sin JavaScript propio.
  4. «Seleccionar grupo» y «Seleccionar todo» son peticiones que devuelven la lista re-renderizada con las casillas marcadas.
  5. La barra de acciones queda fija en pantalla y respeta la barra inferior móvil.
  6. Lo que el usuario ve (grupos y casillas) **no altera** el catálogo hasta la confirmación de V6b.
  7. Estado vacío («¡Todo clasificado!») con enlace de vuelta al Inicio.
  8. Se conservan las rutas y los campos HTMX actuales de búsqueda y asignación individual (contratos de V0) hasta que V6b los sustituya.
- **Pruebas.** `agrupar_pendientes` con los 14 nombres reales de `_Unsorted` (grupos esperados y «Otros»); el endpoint de selección con 0, 1 y N; plantilla con y sin sugerencia; accesibilidad de las casillas (`aria-label` con el nombre del archivo).
- **Fuera de alcance.** Asignar (V6a/V6b), ignorar/recuperar (V7), mejorar el parser (B14).
- **Ficha §13.** Requerida (comportamiento nuevo P0): contrastar la asignación manual de Kapowarr y Mylar3 leyendo su código.
- **Puerta G1.** No se fusiona antes de tener los resultados de U10.
- **Dependencias.** V2, V3; B2, B12.

**V6 — Asignación por lotes: dividida en V6a (servicio) y V6b (interfaz)**

Tras el inventario de V0 la historia no cabía en una PR sin mezclar un cambio de **servicio** que mueve ficheros del usuario con un cambio de **pantalla**. V6a no cambia nada visible y puede fusionarse antes de la puerta G1; V6b no se empieza hasta que V6a esté fusionada y verificada.

**V6a — Servicio de asignación por lotes y auditoría de mover + sesión (P0, L)**

- **Historia.** Como equipo, quiero un servicio que asigne varios archivos con aislamiento por archivo y una auditoría hecha del riesgo de mover ficheros con la sesión de BD viva, para que la interfaz de lotes no multiplique un riesgo que hoy solo está anotado.
- **Estado de partida (leído en V0).** `ReviewService.assign_to_series` llama a `safe_move_async` y solo hace `flush`; el `commit` lo hace `get_db` al salir de la petición (y hace `rollback` si hay excepción). Entre el movimiento y el `commit` hay una ventana en la que un fallo deja el **fichero movido y la BD revertida**. `CLAUDE.md` §3.1.2 lo marca «pendiente de auditar». `_learn_alias` se ejecuta **siempre** y guarda `normalize_title(parsed.series)` **del archivo**.
- **Criterios de aceptación.**
  1. **Auditoría documentada antes de escribir el lote** (`docs/design/`): enumera cada punto de fallo entre `safe_move_async` y el `commit` (excepción tras mover, caída del proceso, `rollback` del `get_db`), qué estado deja en disco y en BD, y cómo se **reconcilia** (p. ej. mover de vuelta, o reintentar con idempotencia). **Si la reconciliación exige persistir algo, esa dependencia se separa en su propia historia con migración** (decisión 5 de la épica): V6a no se fusiona rebajando la garantía.
  2. **Número por archivo**: la unidad del lote es `(file_id, series_id, issue_number | None)`. Una función pura `numero_sugerido(nombre)` prefilla lo que `parse_comic_filename` detectó y devuelve **`None`** cuando no hay número **o es un rango/paquete** (`144-158`, `(94-121 usa)`); **nunca** inventa un `1` ni toma un extremo del rango. Un archivo sin número se devuelve como **`sin_numero`** y **queda pendiente** (no es un error del lote).
  3. **Alias real por archivo**: parámetro `aprender_alias` (por defecto `True`, para no cambiar B13). El patrón que se aprende es el de **cada archivo** (`normalize_title(parsed.series)`), no un «grupo»; una función pura `patrones_a_aprender(archivos)` los lista **sin duplicados** para la previsualización. Con `aprender_alias=False` no se escribe ningún `LocalAlias`.
  4. **Límites del lote**: tope máximo de archivos por lote (constante, empezando en 50 = el tope actual de Pendientes); por encima se **rechaza con un mensaje**, no se trunca en silencio. Se **mide** con ficheros reales (p. ej. 10 CBZ de ~100 MB en el disco de destino, también un CIFS) y se fija en la ficha §13 el umbral a partir del cual la ejecución dejaría de caber en una petición; si no cabe, el diseño pasa a tarea en segundo plano **como historia aparte**, no se improvisa.
  5. **Aislamiento y `commit` corto por archivo**: un fallo en el 3.º no revierte el 1.º ni el 2.º; ningún `shutil.move` cruza una transacción abierta sin haberlo auditado (criterio 1).
  6. **Resultado por archivo** con un conjunto cerrado (`asignado`, `ya_asignado`, `sin_numero`, `colision_edicion`, `no_encontrado`, `error`) y un motivo en español; **no se lanza `HTTPException`** desde el servicio.
  7. **Idempotencia**: repetir el mismo lote no duplica movimientos ni `Issue`; lo ya asignado se informa como `ya_asignado`.
  8. La asignación individual (`assign_to_series`, `POST /ui/pendientes/{id}/asignar`) **conserva su firma y su contrato**; los tests de B13 y B15 pasan sin tocarlos.
- **Decisión de diseño (2026-10-03) y ADR 0006 (aceptado el 2026-10-05 como decisión de arquitectura; no certifica apagones, CIFS ni la integración):** contrato **copia verificada → publicar → confirmar → retirar el origen → reconciliar**, con `commit` de resultado desconocido tratado como desconocido (se consulta la BD, no se borra nada), hardlinks como optimización posterior. Persistencia: **`File.metadata_` descartada con evidencia** (cinco puntos reescriben la columna entera: el marcador se pierde; y no puede reservar un destino único) → **historia con migración `0017`** (`asignacion_operaciones`) **antes** del servicio; V6a no se fusiona rebajando la garantía. Prototipo de un archivo con 43+6 pruebas (muerte tras cada paso, commit confirmado con respuesta perdida, destino con sufijo, solapamiento con `Issue` existente, cancelación; y, tras la revisión de #76: no borrar la última copia —destino ausente/corrupto, BD desviada, origen sustituido con igual tamaño y fecha—, publicar sin reemplazar con rechazo del montaje, candado de transacción con un pool real, relectura del destino también en la misma ejecución, y **vallado por época** para que un ejecutor que pierde el candado no pueda publicar, confirmar ni borrar; el límite de simultáneas es por instancia y no se ha demostrado global) y mediciones (100 MB: ~1 s de copia+hash frente a ~0 del `rename`; el hash domina). **Servicio de un archivo hecho (sin conectar a la interfaz, sin lote):** `services/asignacion.py` con límite de simultáneas compartido por motor, reconciliación al arrancar, coordinación con otros escritores por la restricción única de `files.file_path`, recuperación del `commit` desconocido y 409 específico con `flush` y `rollback` en `DELETE /api/series/{id}`; **Conectado el endpoint individual (2026-10-05, PR aparte):** `/ui/pendientes/{id}/asignar` va por el servicio; recuperables visibles (200 con aviso / 503 con tarjeta), colisión de ediciones 409 con motivo persistido, tarjeta en lugar de JSON bajo htmx; un `OSError` al publicar ya no se escapa y se distingue «no publicado» / «publicado con residuo» / «incierto» (ver el ADR 0006); avisos que nombran el mecanismo real (reinicio o volver a asignar, sin planificador). Verificado en navegador real (htmx 4 con la configuración de ZascArr): éxito, 409 y 503 se intercambian dentro de su tarjeta. `assign_to_series` queda heredado. **Pendiente:** el lote. **Migración 0017 hecha (PR aparte, solo esquema, modelo y pruebas):** tabla `asignacion_operaciones` con estados persistidos distintos de los resultados, `ON DELETE SET NULL` + CHECK para que una operación viva no desaparezca por cascada, índices únicos parciales (un archivo, un destino), downgrade que se niega con operaciones vivas; el prototipo corre ya sobre este esquema. **Orden de historias:** migración → servicio de un archivo → lote con límite **por bytes y por cantidad y operaciones simultáneas** → segundo plano si hace falta → importador. **Medido en la Pi (2026-10-04, tres ext4, dos ejecuciones: `2716ef4` con parche local del lanzador y `4ab2b07` con el del repositorio; 35 asignaciones, informes JSON en `docs/design/`):** asignar 100 MB = 1,07–1,16 s (NVMe), 1,19–1,41 s (Descargas), 2,92–3,27 s (WDElements, ~2,5–3×) y **1,58 s (Descargas → WDElements, ~2,07× más rápido que dentro de WDElements: hipótesis de contención, no aislada)**; `renameat2` sin reemplazo, `link` y `fsync` correctos; el hash de 100 MB es barato (0,08–0,10 s: «el hash domina» **retirado**) y la diferencia entre el tiempo combinado y los aislados en WDElements sugiere investigar la sincronización y la E/S, sin poder cuantificarla ni identificar el componente dominante (las mediciones aisladas no son fases de una misma ejecución); no se fija aún un límite síncrono, una operación simultánea inicial. **No demostrado:** corte eléctrico, CIFS, un lote real, fallos durante una copia cruzada, desconexión HTTP real.
- **Auditoría (criterio 1) hecha — 2026-10-03:** `docs/design/auditoria-mover-y-sesion.md` + ficha §13 `docs/design/benchmark-V6a-asignacion.md` + `tests/test_asignacion_fronteras_pg.py` (10, caracterización con Postgres y ficheros reales). Hallazgos: **(1)** un fallo entre mover y confirmar deja el fichero movido y la BD revertida por **cuatro caminos** (servicio, `commit`, respuesta, muerte del proceso); **(2)** el `commit` de `get_db` ocurre **después de enviar la respuesta**: el cliente puede recibir `200` con el `commit` fallido; **(3)** no hay reconciliación automática: el importador marca la fila como «desaparecida» y nadie registra el destino (solo hay recuperación manual por hash si el fichero vuelve a una carpeta de entrada); **(4)** el solapamiento de dos envíos **cuando el `Issue` aún no existe** es seguro, pero por el índice único de `Issue`, no por diseño; con el `Issue` ya existente no está probado. Una primera lectura decía que la reconciliación no exigía persistir nada nuevo: **retirado, no está demostrado** (recuperar tras un reinicio necesita que la operación y su destino efectivo sobrevivan). Lo evalúa el **ADR 0006**; si `File.metadata_` no acredita integridad y concurrencia, se separa una historia con esquema. **Sin medir:** `hardlink` en los montajes reales, el importador (un `commit` para todo `scan_and_import`), cancelación del cliente, tope del lote.
- **Pruebas.** Éxito total; parcial con colisión de edición (B15) y con archivo sin número; rango sin número sugerido (con los nombres reales de `_Unsorted`); límite de lote; doble ejecución; un fallo en el 3.º con el 1.º y el 2.º intactos; alias activado y desactivado (con y sin duplicados de patrón); regresión de la individual. **Postgres real y ficheros reales** para las fronteras de `commit`.
- **Verificación.** En un directorio de prueba: lote de 4 que cambia de carpeta y cuyos `Issue` se crean con el `format` esperado; forzar el fallo del criterio 1 y comprobar la reconciliación.
- **Ficha §13.** Requerida: contrastar la asignación manual de Kapowarr y Mylar3 (versión/commit y pruebas).
- **Dependencias.** B13, B15, A3 (`safe_move`). **No** depende de V5.

**V6b — Asignación en lote en la interfaz (P0, L)**

- **Historia.** Como coleccionista, quiero asignar a una serie los archivos seleccionados con una sola confirmación que me enseñe exactamente qué va a pasar y qué se queda pendiente, para clasificar en minutos sin miedo a equivocarme.
- **Precondición (cumplida en V0).** La colisión de ediciones (`409` de `asignar`) se reprodujo en la UI actual y se registró el cuerpo recibido, el intercambio de htmx 4 y lo que queda visible (`docs/design/ui-baseline/README.md` §1): **el cuerpo JSON sustituye a la tarjeta**. Por eso el criterio 3 de V6b: el lote no depende de `HTTPException`.
- **Criterios de aceptación.**
  1. Dos pasos en el servidor: `POST /ui/pendientes/asignar/previsualizar` devuelve el fragmento de confirmación y `POST /ui/pendientes/asignar/confirmar` ejecuta. **La lista que se muestra es la que se ejecuta**: el segundo paso recibe los identificadores y los números, no recalcula la selección.
  2. **Número por archivo, visible y editable** en la previsualización, prellenado con `numero_sugerido` (V6a). **Los archivos sin número no se asignan**: se muestran como **«se queda pendiente — no hemos podido saber el número (es un paquete 144-158 / no lleva número)»** y el coleccionista puede escribirlo o dejarlo. **Nunca** se rellena `1` ni se convierte un rango en un número para satisfacer el formulario.
  3. **Respuestas 4xx/5xx:** por cómo htmx 4 intercambia cuerpos de error, el lote **no depende de `HTTPException`**: devuelve **200 con un fragmento de resultado por archivo** (`asignado` / `no asignado: motivo` / `se queda pendiente: motivo`). Los fallos de validación del propio formulario (identificadores inexistentes) también devuelven fragmentos legibles. Una prueba comprueba que ninguna ruta del lote devuelve un cuerpo JSON.
  4. **Éxito parcial** visible: los no asignados siguen en Por revisar; el resumen final cuenta asignados, pendientes y fallidos y enlaza a la serie.
  5. **Alias (B13):** la previsualización muestra los patrones que se aprenderán (`patrones_a_aprender`) con una casilla `aprender_alias`; un alias incorrecto se fija, por eso se muestra antes.
  6. **No existe «deshacer» tras asignar** y la interfaz no lo promete: el texto de la confirmación dice que los archivos **se moverán** a la carpeta de la serie. Hasta confirmar no se mueve nada.
  7. Confirmar dos veces el mismo lote no duplica nada (V6a, criterio 7) y se informa.
  8. Se conservan las rutas y campos de la asignación individual (contratos de V0).
  9. Sin JavaScript propio nuevo.
- **Pruebas.** Plantillas con éxito total, parcial, archivo sin número (rango y ausente) y lote por encima del límite; ninguna ruta del lote responde JSON; doble confirmación; regresión de la individual y de V5.
- **Verificación.** Navegador real contra Postgres real y ficheros reales, con capturas antes/después **incluido el caso 409**.
- **Puerta G1.** No se fusiona antes de tener los resultados de U10.
- **Dependencias.** V5, **V6a**; B13, B15.

**V7 — Ignorar con vuelta atrás y pestaña «Ignorados» (P1, M)**

- **Historia.** Como coleccionista, quiero poder recuperar un archivo que ignoré por error, para no temer a «Ignorar».
- **Criterios de aceptación.**
  1. «Ignorar» tiene menor peso visual que la acción principal y no está pegado a ella.
  2. Al ignorar, la fila se sustituye por una línea «Ignorado · Deshacer» que revierte con `hx-post` a `recuperar`. Es reversible porque `files.review_dismissed` ya existe (sin migración), **pero hoy no hay operación inversa ni consulta de ignorados**: V7 añade `ReviewService.recuperar()` y `ignorados()` con pruebas, no solo presentación.
  3. Pestaña «Ignorados» con contador y botón «Recuperar» por archivo.
  4. Acciones sobre varios archivos (ignorar la selección) con el mismo mecanismo.
  5. Recuperar vuelve a poner el archivo en Por revisar con su sugerencia intacta.
- **Pruebas.** Ignorar → recuperar restaura estado y metadatos; idempotencia de ambos endpoints; contadores coherentes con V3.
- **Dependencias.** V5.

**V8 — Deseados: estados honestos, agrupados y sin duplicados silenciosos (P1, M)**

- **Historia.** Como coleccionista, quiero ver en qué punto está cada petición y qué hacer si no avanza, para confiar en «marcar y olvidarme».
- **Criterios de aceptación.**
  1. Función pura `estado_visible(item)` que, a partir de `WishlistStatus`, `last_error` (D9) y `last_searched_at`, devuelve un único estado de presentación (`en cola`, `buscando ahora`, `sin resultados`, `descargando`, `en tu biblioteca`, `falló`) más el **siguiente paso** con su enlace. «Buscando» y «sin resultados» **no pueden coexistir**.
  2. Cada motivo de D9 enlaza a su solución (sin fuentes → Ajustes/objetivo «que se descarguen solos»; cliente inaccesible → Ajustes y diagnóstico de red A10).
  3. Las filas de una misma serie se **agrupan visualmente** con un recuento y son expandibles.
  4. **Agrupar es solo visual** (decisión de producto 7b): cada petición sigue siendo su fila, con **número, edición (`Issue.format`) y estado** visibles para poder distinguirlas. **No hay «Unir duplicadas»**; no se borra ni se fusiona ninguna fila automáticamente. Al añadir algo ya presente (misma serie y mismo `issue_id`, incluido ninguno), el servidor lo **dice** y enlaza a la existente en vez de crear otra; se resuelve en el servicio, **sin** restricción `UNIQUE` (exige migración: dependencia separada si se quiere, decisión 5).
  5. «Buscar ahora» (D10) y su token firmado se conservan sin cambios; el aviso de uso responsable pasa a un bloque plegable manteniendo el gate legal.
  6. Antes de implementar, se comprueba en la BD real si las cinco filas «BPRD» son duplicados o números distintos, y la decisión de agrupar se ajusta a ello.
- **Pruebas.** Tabla estado×motivo→texto y enlace; alta repetida; agrupación; regresión de D10 y del gate legal.
- **Dependencias.** V2, V3; D1, D9, D10, A10.

**V9 — Estado: semáforo honesto y mensajes en llano (P1, L)**

- **Historia.** Como coleccionista, quiero que Estado me diga si debo preocuparme y qué hacer, sin términos internos.
- **Criterios de aceptación.**
  1. El semáforo global es el **peor** de los parciales («Todo bien» solo si todos lo están; «Atención» con cualquier aviso).
  2. Un catálogo por comprobación (`estado_textos`) con tres campos: qué pasa, por qué importa, qué hacer. La ruta o el detalle técnico va en «Detalle técnico» plegado.
  3. «Sin datos» de VPN se distingue de «sin protección»: el primero no afirma riesgo; el segundo sí.
  4. «No uso VPN: silenciar» guarda una bandera en `runtime_settings` (`get_flag`/`set_flag`, sin migración); silenciar no oculta el estado real, solo el aviso, y se puede revertir.
  5. Se conservan los estados de la BD de E6 (`unreachable`, `migration_required`, `schema_incompatible`, `ok`) con su texto y acción.
  6. **`/estado` se conserva en `/estado` como diagnóstico independiente de la BD** (V0): se sirve con la BD caída, y su fragmento de sondeo **no usa `get_db`** y está declarado junto a `_RUTAS_DIAGNOSTICO`. `/` ya redirige a `/ui/` (no hay página estática): **no existe un segundo semáforo** que unificar, y se mantiene así.
  7. La página se actualiza por **sondeo HTMX** y se **retira el JavaScript inline** de `estado.html` (~100 líneas con `fetch("/api/health")`). La pantalla funciona igual con la BD caída (prueba con `db_degraded`).
  8. **Seguridad aparte de la salud técnica (A11):** `/api/health` trae `seguridad.atencion` (abierto sin contraseña). Se pinta como «Atención» con su texto («qué pasa / por qué importa / qué hacer»: poner contraseña, o volver a ejecutar el instalador y elegir «solo esta máquina») **sin cambiar `status`** (observacional, como la VPN).
  9. «Copiar comando» no se implementa con JS: el comando va en un bloque seleccionable (`user-select: all`).
- **Pruebas.** Matriz de combinaciones de estados → semáforo y textos; bandera de silencio; BD degradada.
- **Dependencias.** V2, V3; E1, E6, D4.

**V10 — Ajustes guiados por objetivos (P1, L)**

- **Historia.** Como coleccionista que no sabe qué es Prowlarr, quiero que Ajustes me pregunte qué quiero conectar, para configurar sin leer párrafos técnicos.
- **Criterios de aceptación.**
  1. `GET /ui/ajustes?objetivo=` (sin parámetro, la pantalla de objetivos): «Portadas y datos», «Que se descarguen solos», «Avisos en el móvil», «Proteger con contraseña». El estado vive en la URL (enlazable y recargable).
  2. `ajustes.html` (la plantilla mayor) se divide en un parcial por objetivo; los **endpoints de guardar y de probar de D11 no cambian** de URL ni de campos (contratos de V0).
  3. Direcciones, puertos y `host.docker.internal` van en una sección «Avanzado» plegada.
  4. «Probar conexión» devuelve causa y siguiente paso en español, reutilizando D9/A10, sin excepciones ni URL en crudo; los textos tienen `aria-live`.
  5. Cada tarjeta dice en una línea para qué sirve y si es opcional.
  6. Se conservan: guardar aplica al instante, los secretos nunca se devuelven en claro, el campo de secreto vacío significa «no cambiar», y activar contraseña sin credencial se rechaza (A6).
  7. El objetivo «Proteger con contraseña» **muestra la exposición efectiva** (`seguridad.exposicion`: solo esta máquina / red local / proxy; y si hay contraseña) como **texto informativo**, con la acción «para cambiarlo, vuelve a ejecutar el instalador». **No ofrece ningún selector** de quién puede entrar ni cambia la publicación de puertos: A11 ya está implementada y el puerto es de Docker en el host (ADR 0004). El campo `base_url` (proxy que cambia `Host`) **se conserva** con su explicación actual, y la contraseña es `type="password"`.
  8. **Ningún bloque actual desaparece al repartirlos en objetivos:** los 7 de hoy (Fuentes de metadatos —**con GCD**, que la maqueta no lista—, Comic Vine, Prowlarr, Transmission, aMule, Seguridad y Avisos) quedan asignados a un objetivo o a «Avanzado», y una prueba comprueba que cada `name=` de formulario sigue existiendo.
- **Pruebas.** Cada objetivo expone los campos correctos; el modo avanzado conserva todos; regresión de secretos y del guardarraíl de A6; la prueba de conexión con y sin éxito.
- **Riesgos.** Es la plantilla más grande y donde viven los secretos: se migra por partes y con regresión específica.
- **Dependencias.** V2, V3; D11, A6, A10, D9.

**V11 — Duplicados con resumen y orden por ahorro (P2, M)**

- **Historia.** Como coleccionista con duplicados, quiero un resumen y que se ordene lo que más espacio recupera, para saber por dónde empezar.
- **Criterios de aceptación.**
  1. **V11a (presentación):** resumen superior calculado a partir del informe existente (GB recuperables, nº de grupos por tipo, fecha de la última revisión); grupos ordenados por ahorro con selector de orden; rutas legibles (nombre destacado, carpeta secundaria). La etiqueta del menú pasa a «Duplicados»; la URL `/ui/auditoria` no cambia.
  2. **Invariante de B16 intacta:** solo lectura. Sin botón de borrar ni mover; el orden por ahorro es información, no una recomendación de acción. El test de «mtimes antes y después» se mantiene.
  3. **V11b (progreso real, opcional):** el escaneo informa de «archivos leídos / total» a través de un endpoint sondeado con `hx-trigger="every 2s"`. **Requiere backend nuevo** en `LibraryAudit` (estado de progreso en memoria del proceso); se estima y se aprueba aparte antes de empezar.
- **Pruebas.** Resumen con informe vacío, con grupos de distinto tamaño y con orden; no se toca el disco.
- **Dependencias.** V2, V3; B16.

**V12 — Pantallas no maquetadas: Biblioteca, Descubrir, ficha de serie, login y aviso legal (P1, M)**

- **Historia.** Como coleccionista, quiero que las pantallas que la maqueta no cubre se vean y se comporten igual que el resto, para no sentir que hay dos aplicaciones.
- **Alcance.** **Restyle con los componentes de V2, sin rediseñar flujos.** Las plantillas implicadas: `biblioteca.html` y `_rejilla_biblioteca.html`, `descubrir.html` y sus parciales de resultados, `series_detail.html` y `_politica_serie.html`, `login.html`, `legal_wizard.html`, `legal_full.html`.
- **Criterios de aceptación.**
  1. Usan botones, chips, tarjetas y estados vacíos de V2; ninguna conserva estilos locales que contradigan los tokens de V1.
  2. Cumplen contraste, tamaño mínimo y objetivos táctiles (V1).
  3. Se conservan todos los contratos HTMX (búsqueda por personaje y saga, alta de serie, política D8 por serie).
  4. `login.html` y las pantallas legales funcionan sin menú lateral cuando el modo de autenticación lo exige.
  5. Un «rediseño de verdad» de Biblioteca y Descubrir (rejilla, filtros, ficha) se registra como épica aparte, con su propia validación.
- **Pruebas.** Regresión de los tests existentes de cada router; capturas antes/después.
- **Dependencias.** V1, V2, V3.

**V13 — Responsive y verificación en dispositivos (P1, M)**

- **Historia.** Como coleccionista que usa el móvil o la tablet en el sofá, quiero que todo funcione en pantalla pequeña, para revisar y aprobar sin ampliar.
- **Criterios de aceptación.**
  1. Verificado a 360, 390 y 414 px y en tablet (768 px), en vertical y horizontal, y en el **Chromium de la propia Pi**.
  2. Sin desbordamiento horizontal en ninguna pantalla; Por revisar en una columna. **V3 ya comprobó el menú sin desborde a 390 y 320 px en las 8 pantallas** (`docs/design/ui-v3/`); V13 cubre el resto de la página. **Medido en V0/V1 a 390 px: ya desbordaban la ficha de serie (413) y el aviso legal en texto (409); Deseados (731) quedó corregido en V1** (`docs/design/ui-v1/README.md`). Medir además a **320 px CSS**, referencia de reflujo de WCAG.
  3. Objetivos táctiles ≥ 24×24 px (WCAG 2.2 AA) y los botones principales con tamaño cómodo.
  4. **Tras cada intercambio HTMX** el foco no se pierde y el resultado se anuncia (`aria-live`); navegación completa solo con teclado.
  5. Respeta `prefers-reduced-motion` y `prefers-color-scheme`.
  6. Lista de comprobación manual en `docs/design/` y un guion opcional con Playwright **fuera del paquete** (no entra en la imagen de la Pi ni en `pyproject.toml`).
- **Pruebas.** Lista manual firmada por pantalla y ancho; el guion opcional mide desbordes y tamaños.
- **Dependencias.** V3 a V12.

**V14 — Cierre: limpieza, documentación y trazabilidad (P2, S)**

- **Historia.** Como equipo, quiero cerrar la migración sin restos, para no arrastrar CSS ni plantillas muertas.
- **Criterios de aceptación.**
  1. Se retiran los alias de clases antiguas de V2 y las reglas sin uso, y se comprueba que ninguna plantilla las referencia (script de comprobación de clases).
  2. Se eliminan plantillas y parciales huérfanos.
  3. Capturas nuevas en `docs/design/ui-actual/` y en el README; CHANGELOG, BACKLOG y la ficha de la Épica U actualizados.
  4. Se registra lo que quedó fuera: conmutador manual de tema, deshacer-tras-asignar, progreso de V11b, rediseño de Biblioteca/Descubrir.
  5. Presupuesto de peso: tamaño de `web.css` y de cada página sin crecimiento injustificado, medido en la Pi.
  6. El ADR 0005 pasa a «Aceptado».
- **Dependencias.** Todas.

#### Plan de entrega

| Fase | Historias | Resultado visible | Riesgo |
|---|---|---|---|
| 0 · Cimientos | V0, V1, V2 | Textos legibles en toda la app y piezas reutilizables | Bajo: no cambia flujos |
| 1 · Estructura | V3, V4 | Menú nuevo en todas las pantallas e Inicio guiado | Medio: toca `base.html` |
| 2 · Valor principal | V5, V6a, V7, V6b | Por revisar rediseñado, reversible al ignorar y asignación en lotes | **Alto**: asigna y mueve ficheros (V6a lo audita antes) |
| 3 · Resto de pantallas | V8, V9, V10, V11 | Deseados, Estado, Ajustes y Duplicados nuevos | Medio; V10 es la mayor |
| 4 · Cobertura y cierre | V12, V13, V14 | Coherencia total, móvil verificado, sin restos | Bajo |

**Orden de fusión recomendado:** V0 → V1 → V2 → V3 → V4 → **V6a** → (G1: U10) → V5 → V7 → **V6b** → V8 → V9 → V10 → V11 → V12 → V13 → V14. V7 se adelanta a V6b para que el usuario pueda ignorar con red de seguridad antes de poder asignar en bloque. **Tras V0, V6 se divide**: V6a (servicio y auditoría de mover + sesión viva) no cambia nada visible y puede ir antes de la puerta G1; V6b (UI) va después y solo cuando esté **verificado el comportamiento de htmx 4 con respuestas 4xx**.

**Definición de hecho de cada historia de la épica** (además de la del proyecto): PR única; sin migración dentro de la PR (si hace falta esquema, va en una historia previa aparte: decisión 5); **sin JavaScript propio nuevo, y retirada del existente cuando su pantalla se migre**; contratos HTMX de V0 conservados; pruebas del cambio más la regresión de las existentes; verificación en navegador real contra Postgres real, con capturas antes/después en la PR; CHANGELOG y nota de implementación en el BACKLOG; y comprobada la vuelta atrás con `git revert` de la PR.

**Riesgos de la épica.**
- **Sensación de «UI a medias» entre fases.** Se mitiga porque V1–V3 cambian la apariencia global primero, y cada fase deja pantallas coherentes entre sí.
- **Romper un contrato HTMX sin darse cuenta.** Por eso V0 lo lista y cada historia conserva sus rutas y campos hasta sustituirlos.
- **Confundir la maqueta con el producto.** La maqueta simula dos cosas que aquí **no** se implementan (deshacer tras asignar y el conmutador de tema); la tabla de traducción lo deja escrito.
- **Estimaciones.** Revisadas en V0 con el inventario: V4, V9 y V12 suben de M a L, V7 de S a M y V6 se divide. Siguen siendo estimaciones: la verificación en navegador puede moverlas.

## Deuda técnica registrada (peer review v2, hallazgos medios)

Sin arreglar todavía — nombrados aquí a propósito para que no vuelvan a caer
en el agujero de "estaba en el review pero nadie lo pasó al board":

- **M1 — mass assignment en la API — cerrado.**
  Se cerró para `api/wishlist.py` en D1 y, para `api/series.py`, con
  `SeriesCreate`/`SeriesUpdate` Pydantic (`extra="forbid"`, campos
  explícitos snake_case) en POST/PATCH. Regresión en `tests/test_api_series.py`
  (campos internos como `id`, `metadata_source`, `locked_fields` → 422).
- **M2 — normalizador duplicado:** `naming.normalize_series_name` y
  `matcher.normalize_title` resuelven un problema parecido (limpiar un
  título para comparar) con lógica independiente y ya divergente en algún
  matiz. Unificar o documentar explícitamente por qué deben seguir siendo
  dos, antes de que una tercera copia aparezca en el enricher.
- **M3 — `bootstrap.sh` sigue instalando con `pip install --break-system-packages`
  en el host** para poder correr las migraciones fuera de Docker. Frágil en
  distros que no sean Debian/Ubuntu recientes; considerar ejecutar la
  migración inicial dentro de un contenedor efímero en su lugar. Relacionado:
  migrar Alembic a contenedor también permitiría **eliminar el
  `ports: 127.0.0.1:5432` de PostgreSQL** (hoy el bootstrap corre `alembic`
  en el host contra loopback; sin ese `ports` bastaría con `expose`).
  **Materializada en producción (2026-09-24):** un usuario real en
  Raspberry Pi OS lo confirmó — `typing_extensions` venía instalado vía
  `apt` (paquete `python3-typing-extensions`, sin fichero `RECORD` de pip)
  y `pip install -e .` abortaba con `uninstall-no-record-file`. Parcheado
  con `--ignore-installed` (v1.2.2) como parche mínimo, no como cierre de
  M3: la solución de fondo sigue siendo mover la migración inicial a un
  contenedor efímero, tal como ya decía esta entrada.
- **M5 — caché de portada en disco sin invalidación (de C1):**
  `covers_cache_path/{series_id}.jpg` se escribe una vez y no se vuelve
  a comprobar nunca. Si se cachea primero una portada externa y más
  tarde llega un archivo real, o si el enricher cambia de fuente, el
  fichero viejo se sirve indefinidamente hasta que alguien lo borre a
  mano. Aceptable para una biblioteca personal de un solo usuario por
  ahora; revisar si se vuelve confuso en la práctica.
- **Riesgo symlink (seguridad, P0-4):** si un usuario crea manualmente un
  symlink en `DOWNLOADS_PATH` apuntando fuera, el importador podría seguirlo
  al leer/copiar. Riesgo bajo en single-user. Mitigación: documentar en
  README.md que no se deben crear symlinks en la carpeta de descargas.
- **Deuda P1 — `ReviewService.assign_to_series` mueve archivos con la sesión
  abierta:** `safe_move_async` ocurre con la transacción de BD viva; si el
  proceso muere entre el move y el commit, fichero y BD divergen. Solución
  completa: tabla `file_operations` con estados y un reconciliador al arrancar.
  Para 1.0 se acepta el riesgo (single-user, sin concurrencia masiva).

## Deuda técnica registrada (peer review de los scripts de operación, 2026-09-24)

- **`scripts/backup.sh` rompía la convención del `.env` — corregido.** Antes hacía
  `cd "$REPO_DIR"` y `docker compose exec` sin `-f` ni `--env-file` (el `.env`
  vive en `TEBEOTECA_ROOT`, el padre del repo, así que Compose no lo cargaba y
  las variables caían a sus defaults). Ahora usa
  `COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")` y hace el
  dump con temporal + `gzip -t` + `mv` atómico (antes ni verificaba el gzip).
  Sigue siendo self-contained a propósito: no comparte `_comun.sh` porque está
  pensado para copiarse a `/usr/local/bin` (unit systemd); se localiza el repo
  con `ZASCARR_REPO`. Decidir en el futuro si compensa acercarlo a `_comun.sh`.
- **Nombres de dump ahora inequívocos (corregido):** `backup_<TS>` = copia diaria
  de `backup.sh`; `update_<TS>` = copia previa a la actualización, emparejada con
  la ref `refs/zascarr/update/<TS>`; `rollback-safety_<TS>` = copia de la BD
  actual que hace `rollback.sh` justo antes de destruirla. Los tres comparten la
  retención de `RETENTION_DAYS`. `rollback.sh` también deja
  `refs/zascarr/rollback-rescue/<TS>` apuntando al commit que se abandona, para
  poder deshacer un rollback equivocado sin depender del reflog.
- **Cabecera obsoleta en `docker-compose.yml`:** el comentario de uso dice
  `cd /path/a/zascarr; cp .env.example .env; docker compose up -d`, que dejaría
  el `.env` **dentro** del repo. `bootstrap.sh` lo escribe en
  `TEBEOTECA_ROOT/.env` y todos los scripts lo buscan ahí. Induce a error justo
  en el paso que `rollback.sh` valida.
- **Sin `make update` / `make rollback`:** el `Makefile` ya tiene `backup` y el
  `README` cita `make help` como referencia de comandos, pero los dos scripts
  nuevos solo se invocan a mano. Decidir si se añaden o si se documenta que son
  comandos de host a propósito.
- **`rollback.sh` probado contra Docker + PostgreSQL reales (2026-09-24,
  cierra E3).** Además de la simulación (dobles de `docker`/`curl`, ~90
  aserciones cubriendo camino feliz, `--dry-run`, dump corrupto, pareja
  ausente, referencia huérfana, árbol sucio, destino igual al actual,
  repetición de rollback y todas las rutas de aborto), se ejecutó §16.1-16.8
  de `docs/TESTING_E2E.md` de verdad: `TEBEOTECA_ROOT` aislado con `.env` en
  el padre del repo (layout de producción), `update.sh` V1→V2 (build +
  migración 0001→0009 + backup previo verificado + healthcheck), siembra de
  datos "antes"/"después", `rollback.sh --yes` (destructivo: `dropdb --force`
  + `psql -v ON_ERROR_STOP=1` + verificación de esquema) revirtiendo código y
  BD a la vez (`serie_despues` desaparece, `serie_antes` persiste, alembic
  vuelve a la revisión de V1), y `rollback.sh --yes --forzar` repetido con
  una conexión `psql` abierta en transacción (`pg_sleep(120)`) — `dropdb
  --force` la cortó y el rollback terminó en `exit 0`. V1 se usó `d4564a2`
  (con los fixes de hoy ya aplicados) en vez del commit real anterior porque
  ese tenía el bug del Dockerfile ya corregido — probar el mecanismo de
  rollback con un Dockerfile que no compila no aporta nada nuevo. `redis-cli
  FLUSHDB` no se verificó por separado (lo ejecuta el propio script en el
  paso 8; no se comprobó el estado de Redis antes/después explícitamente).

## Deuda técnica registrada (ejecución real de TESTING_E2E.md/TESTING_NFR_Zascarr.md, 2026-09-24)

Primera ejecución real de ambos planes de testing contra un stack Docker
aislado (clon limpio de GitHub, sin tocar el entorno local). Encontró tres
bugs P0/P1 que bloqueaban el release 1.0 — ninguno visible en la suite
unitaria porque ninguno de los tres tiene cobertura de integración contra
Docker/Postgres reales. Los tres están **corregidos y verificados** en este
commit:

- **`Dockerfile` no compilaba nunca (P0, corregido).** El stage `builder`
  copiaba solo `pyproject.toml` y ejecutaba `pip install .` antes de copiar
  `src/`; como el paquete usa layout `src` (`where = ["src"]`), `setuptools`
  fallaba en `egg_info` el 100% de las veces, en cualquier máquina. Fix:
  `COPY src ./src` antes del `pip install`. Verificado con `docker compose
  build --no-cache`.
- **El importador no importaba nada con el `docker-compose.yml` real (P0,
  corregido).** Dos bugs independientes que se combinaban:
  1. `utils/fs.py::_same_filesystem()` compara `st_dev`, pero dos bind
     mounts distintos del mismo filesystem host reportan el mismo `st_dev`
     dentro del contenedor aunque el kernel trate cruzar entre ellos como
     `rename()` entre mounts distintos — `os.replace()` fallaba con
     `OSError: Invalid cross-device link` (EXDEV) en vez de caer al camino
     de copia-y-verifica que sí funciona. Fix: capturar `EXDEV` y caer al
     camino de discos distintos existente, sin duplicar lógica.
  2. `HOST_DOWNLOADS_DIR`/`HOST_AMULE_INCOMING_DIR` estaban montados `:ro`
     en `docker-compose.yml`, pero `safe_move` necesita borrar el origen
     tras copiar (`src.unlink()`, A3) — con solo lectura eso también habría
     fallado. Fix: quitado el `:ro` de ambos mounts (el importador SÍ
     necesita escribir ahí; era un despiste, no una decisión deliberada
     documentada en ningún ADR).
  Verificado con el fixture completo del runbook (dedupe, saneado de rutas,
  `_Unsorted`, asignación manual con `locked_fields`) tras el fix.
- **La restauración de un backup fallaba siempre, en cualquier dump (P0/P1,
  corregido).** No era un problema de orden de volcado (hipótesis inicial
  descartada tras reproducir el caso aislado): `pg_dump` antepone `SELECT
  pg_catalog.set_config('search_path', '', false)` al restore, y la
  migración 0006 definió `f_title_norm()` llamando a `f_unaccent($1)` SIN
  cualificar el esquema. Con `search_path` vacío esa llamada no resuelve, y
  `CREATE FUNCTION`/su inlining posterior fallan con "function
  f_unaccent(text) does not exist" — tumbando la tabla `series` entera y
  todo lo que depende de ella. `scripts/rollback.sh` (usa `-v
  ON_ERROR_STOP=1`) habría abortado en el primer intento de cualquier
  restore real. Fix: migración `0009_fix_title_norm_search_path` (0006 ya
  aplicada, no se reescribe) que re-declara la función con `CREATE OR
  REPLACE` usando `public.f_unaccent($1)`. Verificado extremo a extremo:
  migrar 0001→0009, sembrar datos, `pg_dump`, `dropdb`+`createdb`, restore
  con `psql -v ON_ERROR_STOP=1` (igual que `rollback.sh`) → `exit 0`, datos
  y columna generada `title_norm` intactos.
- **`GET /api/health` tardaba 60-90s cuando Transmission/aMule no responden
  rápido (P1, corregido).** `TransmissionClient`/`AMuleClient` se llamaban
  secuencialmente, cada uno con `timeout=30.0`; si ninguno responde con RST
  inmediato (servicio parado, VPN aún no arriba, firewall con DROP en vez
  de REJECT — nada raro en una Pi real), cada `/api/health` tardaba hasta
  ~60s. El `HEALTHCHECK` del `Dockerfile` tiene `--timeout=10s`, así que
  Docker marcaría el contenedor `unhealthy` de forma casi permanente,
  justo lo contrario de "healthcheck observacional, no bloqueante"
  (CLAUDE.md §4). Fix: ambas comprobaciones ahora corren en paralelo
  (`asyncio.gather`) con `asyncio.wait_for(timeout=3.0)` cada una — el
  endpoint responde siempre en ese margen, reachable o no.
- **Hallazgo menor sin corregir:** el enricher llama a Comic Vine con
  `api_key` vacía (sin configurar) y recibe 401 en cada ciclo — no rompe
  nada, pero es ruido evitable en los logs. Queda como mejora futura, no
  bloquea release.
- **No ejecutado por tiempo/recursos** (dejar constancia explícita, no dar
  por probado): carga sintética a escala (NFR-07, 1000 series), 20 ciclos
  de restart (NFR-09), concurrencia/doble-procesamiento (NFR-10), abuso con
  100 peticiones simultáneas (NFR-14), escaneo de dependencias/imagen con
  `trivy`/`pip-audit` (NFR-17, no instalados en el sandbox → `NOT RUN`,
  nunca `PASS`, tal como exige el propio documento), portabilidad ARM64
  (NFR-19, sin runner ARM disponible). La fase 16 de `TESTING_E2E.md`
  (`update.sh`/`rollback.sh` destructivo contra Docker/Postgres reales) **sí
  se ejecutó** en una segunda pasada — ver la entrada de arriba sobre
  `rollback.sh` (cierra E3).

## Deuda técnica registrada (instalador de un comando + rename de infraestructura, 2026-09-24)

Tras publicar v1.0.0, revisión del flujo de instalación desde el punto de
vista de "El Coleccionista" (persona: no técnico, no abre terminales) sacó
tres problemas reales:

- **`git` y Docker eran dependencias invisibles y no gestionadas.**
  `bootstrap.sh` comprobaba que existieran y moría con instrucciones de
  `apt-get`/`curl` si no — nunca los instalaba él mismo. Para alguien sin
  conocimientos técnicos, eso rompe la promesa de "instalador de un solo
  comando" que ya hacía el propio README.
- **La instalación eran 3 pasos manuales, no 1.** `mkdir` + `git clone` +
  `sudo bash bootstrap.sh` — el usuario tenía que teclear `git clone` sin
  que nadie le explicara qué es git.
- **Nombres de infraestructura heredados de "Tebeoteca Digital"** (el
  nombre original del proyecto, antes de SecuenciArr y de ZascArr — el
  docstring de la migración 0001 lo confirma: *"Initial schema — Tebeoteca
  Digital v1.3"*): el proyecto Compose (`tebeoteca-arr`), los contenedores
  (`tebeoteca-db`/`-cache`/`-orquestador`), la red (`tebeoteca-internal`),
  la base de datos (`tebeoteca`) y la variable `TEBEOTECA_ROOT` en los tres
  scripts de operación sobrevivieron a los dos renames posteriores, que
  solo tocaron la capa superficial (paquete Python, README, badges).

**Fix aplicado:**

- `bootstrap.sh` ahora es el **único comando** de instalación
  (`curl -fsSL .../bootstrap.sh | sudo bash`). El mismo fichero detecta si
  se le invoca suelto (sin `docker-compose.yml` al lado, típico de un
  `curl | bash`) o desde dentro de un clon ya existente: en el primer caso,
  instala `git`/Docker si faltan, crea `~/zascarr` (en el HOME del usuario
  real que invocó `sudo`, no en `/root`), clona el repo, y se relanza a sí
  mismo (`exec`) desde dentro del clon para continuar con la configuración
  de siempre (3 preguntas, `docker compose up`, migraciones). Verificado de
  extremo a extremo en un sandbox aislado: rama de instalación en frío
  (detecta modo suelto, prepara `ZASCARR_ROOT`, clona, relanza) y la
  configuración completa después (build, migrar 0001→0009, arrancar,
  healthcheck), incluida una segunda ejecución idempotente.
- **Rename completo `tebeoteca` → `zascarr`** en toda la capa de
  infraestructura: `docker-compose.yml` (proyecto, contenedores, red, BD),
  `scripts/_comun.sh`/`backup.sh`/`rollback.sh` (`TEBEOTECA_ROOT` →
  `ZASCARR_ROOT`, `DB_NAME` por defecto), `bootstrap.sh`, `README.md`, y los
  comandos literales de `docs/TESTING_E2E.md`/`TESTING_NFR_Zascarr.md`. Se
  hizo ahora a propósito: el mismo día del release 1.0.0, sin instalaciones
  reales todavía — mañana, con gente ya corriendo `tebeoteca-db` en su Pi,
  habría sido un cambio incompatible con cualquier `update.sh` futuro.
- **Hallazgo colateral real, no cosmético:** al ejecutar `bootstrap.sh` de
  verdad por primera vez en este proyecto (hasta ahora solo se había
  probado la migración vía `docker compose run zascarr alembic upgrade
  head`, nunca el camino de host que usa `bootstrap.sh`), salió que la
  comprobación `python3 -c "import alembic"` **siempre daba positivo**
  incluso sin `pip install` — porque se ejecuta con el cwd puesto en la
  raíz del repo, que tiene su propia carpeta `alembic/` (las migraciones),
  y `python3 -c` añade el cwd a `sys.path` antes que el paquete instalado.
  El check "pasaba" con la carpeta local, saltaba el `pip install`, y el
  `alembic upgrade head` posterior fallaba con "orden no encontrada" —
  **esto habría roto toda instalación real desde cero**, en cualquier
  versión anterior a esta. Corregido a `command -v alembic` (comprueba el
  PATH, no el import), que no sufre el shadowing. Reproducido y verificado
  el fix contra el mismo sandbox que lo encontró.

## Deuda técnica registrada (el instalador no se autoactualizaba, 2026-09-24)

Confirmado en vivo por el mismo usuario: tras corregir el bug de
`typing_extensions` (v1.2.2), reintentó la instalación **tres veces**
(`curl | sudo bash` de nuevo, y `sudo bash bootstrap.sh` directo sobre el
clon) y siguió viendo el error YA CORREGIDO, siempre idéntico. Causa: la
rama "ya existe un clon, lo reutilizo" nunca actualizaba nada — cualquier
reintento se quedaba pegado a la primera versión descargada, para
siempre, aunque se publicaran correcciones en GitHub.

**Fix:** `bootstrap.sh` se autoactualiza ahora (fetch + `merge --ff-only`,
mismo patrón que `scripts/update.sh`) en los dos puntos de entrada: la
rama de instalación en frío (clon ya existente) y la reinvocación directa
del script ya clonado — con una marca de entorno
(`_ZASCARR_YA_ACTUALIZADO`) para no intentarlo dos veces ni reemplazar el
propio fichero mientras se ejecuta (se relanza limpio si hubo cambios).

**Y ese mismo fix habría fallado en silencio sin un segundo hallazgo**: el
usuario probó `sudo git pull` a mano primero y le dio `fatal: detected
dubious ownership in repository` — los `git` de `bootstrap.sh` corren
como `root`, pero el repo es de `media` desde v1.2.0, y git rechaza
tocarlo sin autorización explícita. Añadido `git config --global --add
safe.directory` antes de cualquier operación git sobre el repo, mismo
patrón que `scripts/_comun.sh::comprobar_git_utilizable()` ya resolvía
para `update.sh`/`rollback.sh`. Publicado como v1.2.3.

## Deuda técnica registrada (cwd inválido heredado del shell, 2026-09-24)

Tercer bug real reportado por el mismo usuario en la misma Pi: al hacer
`cd ~/zascarr` + `sudo rm -rf ~/zascarr` en el mismo terminal (justo lo que
este documento recomienda como workaround para reintentar una instalación
fallida) y ejecutar el instalador desde ahí, todo revienta con
`getcwd: cannot access parent directories: No such file or directory` en
cascada — hasta el propio instalador oficial de `get.docker.com` fallaba
en cada paso, no solo `git clone`. Reproducido en un sandbox antes de
corregir: `mkdir` + `cd` + `rm -rf` (el mismo directorio) + invocar
`bootstrap.sh` en el mismo proceso de shell, exactamente el escenario real.
Corregido con `cd /tmp` al principio del script (antes de cualquier otra
cosa), para no heredar un `cwd` inválido del proceso padre. Publicado como
v1.2.1.

## Deuda técnica registrada (rutas de instalación coherentes con la suite *arr, 2026-09-24)

El mismo usuario que reportó el bug de arriba ya tiene todo el resto de la
suite *arr (Sonarr, Radarr, Prowlarr, Bazarr, Lidarr, Readarr, Whisparr)
instalada con una convención concreta — compartió el script real
(`arr_suite.sh`, parte de su propio "confiraspa"): binarios en
`/opt/<AppCapitalizado>`, datos en `/var/lib/<appname>` (separados a
propósito), y todo corriendo bajo un usuario de servicio dedicado
(`ARR_USER`/`ARR_GROUP`, por defecto `media`) vía `systemd`, no el usuario
personal. ZascArr (Docker, no binarios nativos con systemd) vivía hasta
ahora en el `HOME` de quien ejecutaba `sudo`, con código y datos mezclados
en la misma carpeta — inconsistente con esa convención ya establecida en
la Pi real del usuario.

**Verificación previa a tocar nada:** antes de cambiar el propietario de
los directorios de datos, se comprobó que Postgres y Redis arrancan como
`root` dentro del contenedor y se autocorrigen el propietario de su propio
directorio de datos en el entrypoint oficial (`find $PGDATA ! -user
postgres -exec chown postgres`) — así que el `chown` del host a `media` no
les afecta. El caso distinto es `config/covers` (portadas) y la biblioteca
del usuario: los escribe el propio contenedor de ZascArr, que corre como
`uid 1000` fijo *sin* privilegios para autocorregirse (a diferencia de
postgres/redis) — esos dos siguen en `uid 1000` a propósito, no es una
inconsistencia sino una restricción técnica real del `Dockerfile`.

**Cambio aplicado (v1.2.0):**
- `ZASCARR_ROOT` (código): por defecto pasa de `$HOME/zascarr` a
  `/opt/zascarr`.
- `ZASCARR_DATA_DIR` (datos de los contenedores, variable nueva): por
  defecto `/var/lib/zascarr`, separado del código — `docker-compose.yml`
  deja de usar rutas relativas `../config/...` y pasa a usar
  `${ZASCARR_DATA_DIR:-/var/lib/zascarr}/...`.
- `ZASCARR_USER`/`ZASCARR_GROUP` (variables nuevas, por defecto `media`):
  `bootstrap.sh` crea el usuario de sistema si no existe
  (`asegurar_usuario_servicio()`, idempotente, llamada tanto en la rama de
  instalación en frío como en la fase de configuración) y le da la
  propiedad del código y de los datos de postgres/redis/vpn-state.
  `config/covers` y la biblioteca del usuario NO cambian: siguen en
  `uid 1000` explícito.
- Las tres variables son overridables (`export VAR=... && sudo -E bash`),
  para quien prefiera otra convención (p.ej. `/opt/Zascarr` con mayúscula,
  como el resto de sus apps vía `${app_name^}`).

## Deuda técnica registrada (bug real en producción, instalador de un comando, 2026-09-24)

Un usuario ejecutó el instalador de la 1.1.0 en una Raspberry Pi real y
limpia: `curl -fsSL .../bootstrap.sh | sudo bash` se detuvo en la primera
pregunta con `sed: -e expression #1, char 47: unknown option to 's'`, tras
un aviso de que el idioma `'# El repo vive en SCRIPT_DIR; ...'` no era
reconocido — un comentario del propio `bootstrap.sh` colándose como si
fuera la respuesta a "¿Idioma de la interfaz?".

**Sandbox de verificación anterior no lo cazó porque no probaba el camino
real.** La verificación fiel de la 1.1.0 (contenedor limpio, git/Docker sin
instalar, usuario con sudo real — ver entrada de más abajo) validó la rama
de instalación en frío y la fase de configuración **por separado**: la
primera con `curl | sudo bash` sin preguntas interactivas (moría antes,
en la comprobación de Docker), y la segunda invocando `bootstrap.sh`
directamente desde el clon con las respuestas ya preparadas por `printf`
— nunca las dos cosas seguidas, en la misma tubería, tal como las
ejecutaría un usuario real. Reproducido en cuanto se probó así de seguido.

**Causa raíz confirmada (reproducida en sandbox antes de corregir):**
`curl -fsSL URL | sudo bash` deja el `stdin` de ese primer proceso
conectado al pipe de `curl`. Bash lee el script de ese pipe **por bloques**
a medida que lo ejecuta, no de golpe; cuando la rama de instalación en frío
llega a `exec bash "$ZASCARR_ROOT/zascarr/bootstrap.sh" "$@"`, el proceso
nuevo **hereda ese mismo stdin** — y en él pueden quedar restos sin
consumir del propio código fuente de `bootstrap.sh` todavía en el pipe. El
primer `read -rp` de la fase 2 (la pregunta del idioma) se traga esos
restos como si fueran la respuesta tecleada, y el `set_env_var` posterior
pasa esa cadena (con `/`, `(`, `)`...) a un `sed` que no la espera.

**Fix:** reconectar `stdin` a `/dev/tty` justo antes del `exec` de la rama
de instalación en frío (con un `< /dev/null` de reserva si no hay terminal
controladora disponible, en vez de heredar el pipe roto). Reproducido el
bug en un sandbox limpio (mismos pasos, mismo error letra por letra) antes
de tocar el código, y reproducida también la corrección en el mismo
sandbox tras el fix. Publicado como v1.1.1.

**Nota sobre una explicación incorrecta que llegó junto al reporte:** el
reporte inicial venía acompañado de un diagnóstico y un *workaround*
apuntando a un fichero `languages/es.sh` inexistente en este repo, con
variables de entorno (`ZASCARR_LANG`, `ZASCARR_HOST`, `ZASCARR_DATA_DIR`...)
que no existen en `.env.example` ni en `config.py`. Se descartó sin
aplicarlo — no coincidía con el código real del proyecto.

## Deuda técnica registrada (CI + lint, 2026-09-24)

No había ningún pipeline de CI (`.github/workflows` no existía): los 256
tests solo corrían si alguien se acordaba de ejecutarlos a mano. Tampoco se
había corrido nunca `ruff check`/`mypy` como gate — al hacerlo salieron 214
errores de ruff y 7 de mypy, ninguno descubierto hasta ahora porque nada los
exigía.

- **`.github/workflows/ci.yml` nuevo:** tres jobs en push/PR a `main` — suite
  unitaria (bloqueante), `ruff check` (informativo, `continue-on-error`
  hasta que se limpie el resto de la deuda de abajo, para no bloquear
  merges con un lint que ya arrastraba 214 errores antes de este commit), y
  build de la imagen Docker (bloqueante — habría cazado el bug P0 del
  `Dockerfile` de la 1.0.0 al instante).
- **36 de los 214 errores de ruff eran falso positivo, no deuda real:**
  regla `B008` ("no llamar a una función en un valor por defecto") marcando
  los 33 usos de `Depends(...)` en firmas de rutas FastAPI — es el patrón
  obligatorio del framework, no un antipatrón. Añadido `ignore = ["B008"]`
  a `[tool.ruff.lint]`.
- **48 errores corregidos automáticamente** (`ruff check --fix`): imports
  desordenados/sin usar, `datetime.timezone.utc` → `datetime.UTC` (Python
  3.11+). Solo cambios mecánicos, verificados contra la suite completa
  (256/20 sin regresiones) y revisados a mano los ficheros de lógica de
  negocio (`enricher.py`, `importer.py`) para confirmar que ningún import
  "sin usar" eliminado era en realidad un re-export que otro módulo
  necesitara.
- **132 errores de ruff sin tocar, deuda real pendiente:** 118 líneas por
  encima de 100 caracteres, 8 candidatos a `StrEnum` nativo de Python 3.11
  (`UP042`, incluye enums de dominio como `ComicTradition` — cambiarlos
  altera semántica de `__str__` en según qué versión, no es mecánico),
  5 sentencias múltiples en una línea, 1 excepción que podría ser
  `contextlib.suppress`. No se tocan en esta pasada: no es proporcional
  arreglarlos a ciegas en ficheros de dominio que nadie pidió tocar.
- **7 errores de mypy sin tocar:** 2 son solo stubs de tipos que faltan
  (`types-Markdown`, `lxml-stubs`, triviales de instalar); los otros 5 son
  incompatibilidades de tipo reales en `enricher.py`/`transmission.py` que
  requieren entender la intención del código, no un fix mecánico.

## Deuda técnica registrada (integridad del hash de fichero, 2026-09-29)

Ficha `benchmark-integridad-hash-dedupe`; PR de implementación de la batida de
deuda. Mecanismo de cierre: columna `File.original_sha256` (migración 0016, hash
del fichero **tal como se importó**, que B6 fija solo la primera vez que reescribe
un CBZ), consulta de dedupe compartida (`or_` de `sha256_hash` y
`original_sha256`, `.first()` con orden determinista, aviso por coincidencias
múltiples en vez de `scalar_one_or_none()`), y **reenlazado** de la fila
`is_missing` cuando el fichero reaparece (reinicia `imported_at`, actualiza
ruta/nombre/tamaño/hash, vacía las marcas de ComicInfo si es el original, cuenta
como importado con «recuperado»).

**Lo que NO se arregla y queda dicho:**
- Los ficheros **ya etiquetados antes de esta migración** no pueden reconstruir
  su hash original: quedan con `original_sha256 = NULL` y solo los detecta la
  auditoría B16 como «misma obra, otra copia». No se inventa.
- El rango `1..total_issues` sigue asumiendo numeración que arranca en el #1
  (una serie que empieza en el #0 pediría un número inexistente y nunca el #0):
  previo a D8, vive en `huecos_de_serie`, y queda pendiente de medir con la
  biblioteca real.

## Deuda técnica registrada (observabilidad del logging, 2026-09-30)

Encontrado al implementar E4 (el aviso de importación): el módulo de avisos
construye URLs que **llevan el secreto dentro** (en Telegram, el token del bot:
`/bot<token>/sendMessage`; en ntfy, el tema hace de contraseña), y `httpx`
registra cada petición a nivel **INFO con la URL completa**.

- **`log_level` y `log_json` son ajustes SIN EFECTO.** Se declaran en
  `config.py` pero **no hay ninguna configuración de `logging`** en el proyecto
  (ni `basicConfig`, ni `dictConfig`, ni `getLogger`): un `LOG_LEVEL=DEBUG` en el
  `.env` no cambia nada. Hoy eso evita la fuga (no se emite el registro de
  `httpx`), pero es por accidente, no por diseño.
- **Mitigado en E4:** `httpx` y `httpcore` se fijan a `WARNING` al importar
  `main.py`, con prueba que lo fija (raíz en INFO durante un envío de Telegram, y
  el token no aparece).
- **Pendiente (no bloquea):** decidir si `log_level`/`log_json` se cablean de
  verdad (configurar `logging`/structlog con ellos) o se retiran. Mientras tanto,
  la documentación no debería prometer que cambian el nivel de log.

## Deuda técnica registrada (E6: trabajos de fondo con la BD degradada, 2026-10-01)

`lifespan` levantaba la app degradada (E6: `/api/health` responde y `/ui/*` falla
cerrado con 503) pero **arrancaba igualmente los cuatro ciclos de fondo**
(auditoría de biblioteca, importación, enriquecimiento y orquestación): cada
intervalo intentaban usar una BD inaccesible, fallaban y llenaban el log sin
poder hacer nada útil. La interfaz se degradaba; los trabajos no.

- **Arreglado:** con `app.state.db_degraded` **no se crean las tareas** y se
  registra **una vez** `background_tasks_skipped_db_degraded`. Así «solo
  diagnóstico» es literal. Al reiniciar con la BD arreglada arrancan solas: la
  bandera es de este proceso, no hay estado persistido que desbloquear.
- Regresión: `tests/test_e6_degradado.py` — el caso degradado **no necesita
  Postgres** (apunta a un puerto muerto, la conexión se rechaza al instante), y la
  contraprueba (con la BD disponible el aviso **no** aparece) se salta sin
  `TEST_DATABASE_URL`.

## Deuda técnica registrada (B15: asignación manual ante duplicados de edición, 2026-10-01)

**B15: asignación manual tolerante a duplicados de edición.** Encontrado en la
revisión de la PR #8 (verificado en el código, no solo leído).

`ReviewService.assign_to_series` busca el `Issue` por `series_id` + `issue_number`
**sin filtrar por `format`** y resuelve con `.scalar_one_or_none()`. Con **dos
filas del mismo número y el mismo formato** —que el esquema puede permitir según
`volume` y `NULL`— SQLAlchemy lanza `MultipleResultsFound`, es decir, un **500
crudo** en vez de una explicación manejable para el coleccionista. Hoy la
colisión de formatos *distintos* sí se detecta (`ColisionDeEdicion` → el archivo
se queda en Pendientes con motivo y 409 en la interfaz), pero la ambigüedad *del
mismo* formato no pasa por ahí porque la consulta revienta antes.

**Propuesta:**

> Buscar candidatos por serie, número **y formato**: si hay exactamente uno,
> reutilizarlo; si hay cero, crear; si hay varios, responder **409 en español** y
> conservar el archivo en **Pendientes**. No dejar que `scalar_one_or_none()`
> convierta una ambigüedad de catálogo en error 500.

**Casos de prueba:**

- Dos `Issue` con mismo `series_id`, `issue_number` **y `format`** → 409, sin
  mover ni enlazar.
- Uno con formato distinto → 409 actual, sin regresión.
- Uno exacto → reutilización normal.
- Cero → creación con el formato derivado del nombre.

Encaja como historia propia o como una línea bajo **B22** (modelo de identidad
editorial), que es donde se decidirá si el esquema debe permitir esas dos filas o
impedirlas con una restricción. SQLAlchemy documenta que los métodos de resultado
que exigen **una sola fila** lanzan `MultipleResultsFound` si hay más de una
(«Using the ORM Result methods», *SQLAlchemy Core exceptions*).


## Deuda técnica registrada (V0: la BD cae con la app en marcha, 2026-10-01)

Encontrado al tomar la línea base de la UI (`docs/design/ui-baseline/README.md` §2). **Defecto operativo,
independiente de la Épica V** (no se arregla dentro de ninguna historia de UI):

- **Síntoma medido:** con la BD caída **después** de arrancar la app, `GET /ui/` (el panel) responde un
  **`500` de texto plano** (`Internal Server Error`). Con la BD caída **desde el arranque** (E6) responde,
  en cambio, el `503` en español «Base de datos no lista … consulta el estado del sistema». `/estado` y
  `/api/health` responden `200` en ambos casos y siguen diagnosticando bien.
- **Alcance:** solo se midió `/ui/`. Las demás rutas `/ui/*` y `/api/*` **no se probaron**; que fallen igual
  es una deducción: el único manejador de excepciones de BD de `main.py` cubre `ProgrammingError` con
  SQLSTATE `42P01` (esquema ausente), no una conexión perdida.
- **Esperado:** el mismo diagnóstico que E6 (503, en español, enlace a `/estado`; en `/api/*`, JSON 503),
  no un 500 crudo. **Primero medir** qué rutas fallan y con qué excepción, y recién entonces decidir si es
  un manejador por tipo de excepción de conexión o un tratamiento en el `AuthMiddleware`.
- **Por qué importa más con la UI nueva:** htmx 4 intercambia los cuerpos de error, así que cualquier
  fragmento que se cargue solo (menú, estado) pintaría ese texto en pantalla (V3).
- **Prueba de regresión pedida:** parar la BD con la app en marcha y comprobar el cuerpo y el código de
  `/ui/`, `/ui/pendientes` y una ruta de `/api/`, con nombre del mecanismo (p. ej.
  `test_bd_caida_tras_arrancar_no_devuelve_500_crudo`).

## Benchmarking competitivo (2026-09-21)

Comparado contra tres proyectos del mismo espacio para no reinventar ni
perder de vista el hueco real:

- **[Kapowarr](https://github.com/Casvt/Kapowarr)** (Python, GPL-3.0): el más
  parecido en forma (UI server-side, Docker, Pi-friendly). Solo Comic Vine
  como fuente, descarga por DDL (MediaFire/Mega/GetComics, sin eD2K), sin
  naming consciente de tradición. Confirma que el ADR-0001 (server-side, sin
  SPA) es la elección correcta para este dominio.
- **[Mylar3](https://github.com/mylar3/mylar3)** (Python, GPL-3.0): el veterano
  del espacio arr-cómic. Aporta tres ideas de valor que ZascArr no
  tiene todavía — pull-list/calendario de lanzamientos (**D5** arriba),
  reintento automático con el siguiente resultado si una descarga falla
  (nota añadida a **D1**), y escritura de `ComicInfo.xml` tras enriquecer
  (**B6** arriba) para que la biblioteca sea legible por cualquier otra
  herramienta sin pasar por la API de ZascArr. Mismo punto ciego que
  Kapowarr: solo Comic Vine, sin tebeo español.
- **[Suwayomi-Server](https://github.com/Suwayomi/Suwayomi-Server)**
  (Kotlin/JVM, MPL-2.0): servidor de manga con arquitectura de fuentes como
  plugins independientes y OPDS nativo (**C5** arriba). JVM no encaja en el
  presupuesto de memoria de una Pi junto al resto del stack — se estudia
  como referencia de diseño, no se integra.
- **Corrección sobre una idea propuesta en el análisis:** se sugirió que
  Tebeosfera ya tenía un flag `optional=True` y que solo faltaba "el toggle
  operativo" para poder desactivar fuentes de enriquecimiento sin
  redeploy. Verificado contra el código actual: **no existe tal flag** — ni
  en `tebeosfera.py`, ni en `enricher.py`, ni en `config.py` (que sí tiene
  `forum_enabled`, pero para la fuente de descarga del foro, sin relación
  con el enricher). Un toggle por fuente (`comicvine_enabled`,
  `anilist_enabled`, `tebeosfera_enabled` en `Settings`, mirando el patrón
  ya usado por `forum_enabled`) sigue siendo una mejora barata y razonable
  — pendiente de registrar como historia si se decide priorizar — pero
  parte de cero, no de una base ya construida.
- **Ninguno de los tres cubre tebeo español con fuentes honestas + eD2K**:
  ese sigue siendo el hueco real de ZascArr frente a los tres.

## Benchmarking competitivo, ronda 2 (2026-09-22)

El usuario trajo un segundo documento de benchmarking (mismas tres
herramientas, análisis más profundo: 16 historias F1-F16 + lecciones de
modelo de datos). Antes de registrar nada se verificó cada claim contra
el código real — tres de las 16 historias resultaron ser lo mismo que ya
se había registrado la ronda anterior, y de paso se encontraron dos
huecos reales no mencionados por ningún documento:

- **F3 = B6, F5 = D5** exactamente (mismo alcance) — no se duplican,
  solo se referencian.
- **F9 vs C5: relacionadas pero no iguales.** C5 se decidió a propósito
  como "solo catálogo, no contenido". F9 añade OPDS-PSE (streaming
  progresivo de páginas), que ES servir contenido — en tensión directa
  con esa decisión. Se deja fuera de C5 por ahora (ver "Lo que no se
  roba" más abajo); si algún día se quiere lectura progresiva por OPDS,
  es una historia nueva, no una ampliación silenciosa de C5.
- **F1 (reintento) ya estaba hecho por D1** (ver sus notas); lo que
  faltaba de verdad —motivo de fallo legible— se registró como hueco
  pendiente en las notas de D1, no como historia nueva.
- **F2 llevó a revisar `api/series.py` de verdad, no solo confiar en la
  descripción del documento**: confirmado el bug de `sort_order`
  truncado (`int(r) for r in ... Issue.sort_order`, con `sort_order`
  siendo `Float` — un `1.5` trunca a `1` y puede colisionar con el
  issue entero 1 en el cálculo de huecos) — ya estaba anotado en C2
  desde el review anterior, esto solo lo confirma con el código delante.
  De paso se encontró que **M1 (mass assignment) no estaba tan cerrado
  como decía este mismo documento el día anterior**: `api/series.py`
  tiene el mismo `Series(**data)`/`setattr` crudo que `api/wishlist.py`
  tenía antes de D1, sin tocar. Corregido el propio backlog (ver M1
  arriba) — más vale corregirse a uno mismo que dejar un "cerrado" falso.
- Los 16 ítems restantes (F4, F6, F7, F8, F10-F16) se registraron como
  historias nuevas en sus épicas correspondientes (A5/A6, B7-B10, C6/C7,
  D6/D7, E4/E5) — ninguno estaba construido, confirmado contra el código
  antes de anotarlo, no solo contra lo que decía el documento.

**Lecciones de diseño del documento (no son historias, son principios):**

- **Validado por comparación, no tocar:** JSONB por entidad para
  metadata suelta (mismo patrón que el `memo` de Suwayomi), IDs de
  proveedor en columnas paralelas en vez de una clave global acoplada a
  una sola fuente (a diferencia de Mylar3, que usa el ID de Comic Vine
  como clave y se queda cojo sin él), `issue_number VARCHAR + sort_order
  FLOAT` (Suwayomi necesitó un módulo entero para resolver lo que este
  diseño ya resolvía, aparte del propio bug de truncado de arriba),
  `story_arc_issues.reading_order` (ya modelado antes de mirar a la
  competencia).
- **Regla nueva, pendiente de auditar:** no mantener la transacción de
  BD abierta cruzando un `shutil.move` de archivo grande — el tracker de
  Kapowarr está lleno de bloqueos de SQLite por esto. ZascArr usa
  Postgres (MVCC, no bloqueo de fichero completo), así que el riesgo no
  es idéntico, pero `ReviewService.assign_to_series` y el importer sí
  hacen `shutil.move` con la sesión de la request todavía abierta — no
  es un incidente confirmado, pero vale la pena revisar si conviene
  mover primero y hacer el upsert en una transacción corta después,
  antes de que la biblioteca crezca lo bastante para que un `move` de
  archivos grandes tarde de verdad.
- **Regla nueva:** cualquier `UNIQUE` de una tabla gestionada desde la UI
  necesita reconciliación amable (upsert/mensaje claro), no una excepción
  cruda de integridad — Kapowarr tiene un bug abierto justo por esto con
  sus carpetas raíz. Aplica el día que exista alguna tabla así en
  ZascArr (hoy ninguna se gestiona desde la UI salvo `wishlist`, que
  no tiene UNIQUE propio).

**Lo que no se roba (y por qué), del propio documento — confirmado
razonable:** Comic Vine como fuente única (mata el diferencial), NZB/
usenet (ecosistema ajeno), extensiones Tachiyomi/JVM (no cabe en la Pi),
GraphQL como segunda API (REST+OPDS bastan para un usuario), WebView
embebido para logins (la vía de cookies exportadas ya lo cubre), sync de
progreso con trackers externos (duplica a Kavita), editor de plantillas
de naming con variables en UI (demasiada superficie para el
coleccionista) — y, añadido en esta ronda, **OPDS-PSE** (streaming de
contenido) por la misma razón que ya motivó que C5 fuera solo catálogo.

## Fuera de alcance (parking lot honesto)

Multiusuario con perfiles, sincronización de lectura entre dispositivos (es de
Kavita), app móvil nativa, descubrimiento por recomendación IA, integración
con tiendas o wishlists de compra física. Apuntarlos explícitamente evita que
el MVP engorde hasta no salir nunca — el coleccionista quiere su tebeoteca
ordenada, no un Facebook del cómic.

## Definition of Done del release "listo para usar"

El release 1.0 se corta cuando un coleccionista sin conocimientos técnicos,
partiendo de una Pi con Raspberry Pi OS limpio:

1. ejecuta un comando,
2. espera menos de 20 minutos,
3. ve su caos de descargas organizado en series con portadas,
4. marca una serie como deseada y la ve aparecer días después sin intervenir, y
5. jamás ha abierto una terminal, un JSON ni un log.

Las historias P0 suman ~10-14 semanas de trabajo a ritmo de proyecto personal;
el orden sugerido de ataque es **B** (vale oro y está medio hecha) →
**E1/A1** (confianza) → **C1/D1** (la UI que convierte backend en producto).
