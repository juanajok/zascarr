# Guion de validación en la Raspberry Pi — MVP «vincular series ya existentes»

> **Estado: guion, NO ejecutado en la Pi.** Se ensayó entero en un sandbox x86 con Docker (§10) para que los
> comandos y los resultados esperados no sean suposiciones, pero **un ensayo en x86 no es evidencia de la Pi**: el
> disco, la memoria y la CPU son justo lo que se quiere medir. Hasta que alguien lo ejecute, todo lo que dice «en la
> Pi» está **NOT RUN**.

## 1. Qué valida y qué no

**Valida** el recorrido que dejaron cerrado #118–#120, para series que **ya están** en la biblioteca:
elegir serie → revisar archivos y números → confirmar la vinculación → ver el resultado → recuperar un fallo sin duplicar.
Además: restauración de la base de datos de la pila de validación y el tiempo de confirmar 100 archivos (D8, hoy una
**hipótesis**: «100 archivos» no está validado).

**No valida** (sigue NOT RUN aunque todo pase): crear una serie desde el asistente (el tramo de alta no está asignado),
fuentes reales (Comic Vine, AniList, Tebeosfera, GCD), el despliegue sobre la instalación real, el ensayo completo de
`backup.sh`/`rollback.sh` de #123, lectores de pantalla y móvil físico.

## 2. Reglas que no se rompen

1. **La instalación real no se toca.** Se levanta una **pila aparte** (contenedores, volumen de datos, biblioteca y puerto
   propios). No se para, no se reinicia y no se actualiza la de producción sin una decisión expresa y separada.
2. **Biblioteca de prueba, nunca la real.** Los CBZ de prueba se generan (§4) o, como mucho, se **copian** fuera de la
   biblioteca real; la pila de validación nunca monta la real.
3. **Sin red hacia fuentes ni hacia los servicios de la Pi.** Fuentes apagadas; Transmission, Prowlarr y aMule vacíos
   (si no, la pila de validación hablaría con los de producción). No se acepta el asistente legal.
4. **Postgres y Redis no se publican** (ADR 0004); la interfaz escucha solo en `127.0.0.1`. Se entra por túnel SSH.
5. **`scripts/backup.sh` y `scripts/rollback.sh` NO valen para esta pila**: no llevan `--project-name` y apuntarían al
   proyecto `zascarr` (producción). Aquí se usan los comandos explícitos de §7.
6. **Un FAIL de seguridad (§9, V-40…V-43) para el guion** y se informa antes de seguir.
7. **Se registra el resultado, no solo «ha ido bien»**: cada caso termina en PASS, FAIL o NOT RUN con su evidencia (§11).
   Sin nombres ni rutas reales en el informe.

## 3. Preparación (V-00…V-05)

| ID | Qué hacer | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-00 | Registrar el equipo: `cat /proc/device-tree/model; uname -a; docker version --format '{{.Server.Version}}'; docker compose version; free -m; df -h /var/lib /srv; vcgencmd measure_temp` | Se anotan modelo, RAM, almacenamiento (SD / SSD / USB) y temperatura inicial | — (dato) |
| V-01 | **Capacidad.** `free -m` → columna *disponible* | **≥ 1024 MB** disponibles (la pila declara hasta 1152 MB de tope; en el ensayo usó ~200 MB) | PASS si ≥ 1024; si no, **parar**: no se libera RAM parando producción sin permiso |
| V-02 | **Compose ≥ 2.24** (`docker compose version`): el fichero de §4.2 usa `!override` | Versión suficiente | FAIL → usar la variante de §4.2 con `sed` |
| V-03 | **El código contiene #187:** `git -C <repo> log -1 --format=%H` y `git -C <repo> merge-base --is-ancestor 80014ce8017865c2c87db87f7d2b412b591ec15a HEAD && echo SI` | Imprime `SI`; se anota el commit | FAIL si `NO` |
| V-04 | **Estado de producción antes:** `docker ps --format '{{.Names}} {{.Status}}'` y, **solo lectura**, el recuento de filas de `files`, `issues` y `series` de la BD real (`docker exec zascarr-db psql -U comics_admin -d zascarr -tAc "select (select count(*) from files),(select count(*) from issues),(select count(*) from series)"`) | Se guardan para compararlos en V-43 | — (dato) |
| V-05 | **Puertos libres:** `ss -tlnp \| grep -E ':18000\b'` | Sin resultados | FAIL → elegir otro puerto en §4.2 y en las URL |

## 4. La pila aislada

### 4.1 Carpetas y entorno

```bash
VAL=/srv/zascarr-val                         # o cualquier disco con ≥ 2 GB libres; el nombre es lo de menos
sudo mkdir -p "$VAL"/{data,biblioteca,descargas,incoming} && sudo chown -R "$USER": "$VAL"

cat > "$VAL/.env" <<'EOF'
DB_PASSWORD=cambia_esto_ahora
ZASCARR_DATA_DIR=/srv/zascarr-val/data
HOST_LIBRARY_DIR=/srv/zascarr-val/biblioteca
HOST_DOWNLOADS_DIR=/srv/zascarr-val/descargas
HOST_AMULE_INCOMING_DIR=/srv/zascarr-val/incoming
ZASCARR_BIND_ADDRESS=127.0.0.1
EOF
```

### 4.2 El fichero que aísla la pila (verificado con `docker compose config`)

```yaml
# /srv/zascarr-val/override.yml
services:
  postgres:
    container_name: zascarr-val-db
    ports: !override []          # el compose base publica 127.0.0.1:5432: chocaría con producción
  redis:
    container_name: zascarr-val-cache
    ports: !override []
  zascarr:
    container_name: zascarr-val-orquestador
    ports: !override
      - "127.0.0.1:18000:8000"
    environment:
      - COMICVINE_ENABLED=false
      - ANILIST_ENABLED=false
      - TEBEOSFERA_ENABLED=false
      - GCD_ENABLED=false
      - FORUM_ENABLED=false
      - PROWLARR_URL=
      - TRANSMISSION_URL=
      - AMULE_URL=
```

```bash
cd <repo>        # el repo con #187
C=(docker compose --project-name zascarr-val --env-file /srv/zascarr-val/.env \
   -f docker-compose.yml -f /srv/zascarr-val/override.yml)
"${C[@]}" config | grep -nE 'container_name|published|source:'   # revisar: puerto 18000, rutas de /srv/zascarr-val
```

> El nombre de proyecto (`zascarr-val`) y los `container_name` distintos son lo que impide que estos comandos
> alcancen la pila real. **Todos** los comandos siguientes usan `"${C[@]}"`.

### 4.3 La biblioteca de prueba (sintética, con contenido único)

121 CBZ en una sola carpeta: 120 con número y 1 sin número. **El contenido de cada uno debe ser distinto**: dos CBZ idénticos
son duplicados y no se registran como archivos distintos.

```bash
python3 - <<'EOF'
import struct, zipfile, zlib
from pathlib import Path

def png() -> bytes:
    def ch(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + ch(b"IEND", b""))

carpeta = Path("/srv/zascarr-val/biblioteca/Comics/Flash (1987)")
carpeta.mkdir(parents=True, exist_ok=True)
imagen = png()

def cbz(nombre: str) -> None:
    with zipfile.ZipFile(carpeta / nombre, "w") as z:
        z.writestr("001.png", imagen)
        z.writestr("nota.txt", f"contenido propio de {nombre}\n" * 3)

for i in range(1, 121):
    cbz(f"Flash {i:03d} (1987).cbz")
cbz("Sin numero.cbz")
print(len(list(carpeta.glob("*.cbz"))), "archivos")
EOF
```

Para repetir la medición de D8 tres veces (§8) hacen falta **≥ 300** con número: cambia `range(1, 121)` por
`range(1, 321)`. **Genéralos TODOS antes de adoptar (§5):** lo que se añada a la biblioteca después de registrarla no se
recoge («Tu biblioteca ya está registrada, no hay nada nuevo»). Para repetir desde cero: `"${C[@]}" down -v` y vaciar
`data/` y `biblioteca/`.

## 5. Arranque y registro (V-10…V-16)

```bash
"${C[@]}" build zascarr
"${C[@]}" up -d
"${C[@]}" run --rm zascarr alembic upgrade head      # migrar ANTES de usar la interfaz (el health dirá «migration_required»)
"${C[@]}" restart zascarr
```

| ID | Qué hacer | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-10 | `curl -s http://127.0.0.1:18000/api/health` | `checks.database = "ok"`; `fuentes.*` = `"disabled"`. El estado global sale **`degraded`** y es lo esperado: `transmission`, `amule` y `vpn` aparecen inalcanzables porque la pila no los tiene | PASS si `database=ok` y las cuatro fuentes `disabled` |
| V-11 | `docker stats --no-stream` (los tres `zascarr-val-*`) | Cada uno por debajo de su tope (512 / 128 / 512 MB) | PASS; se anota el uso |
| V-12 | `curl -s http://127.0.0.1:18000/ui/auditoria` (texto visible) | «Se han mirado 121 tebeos», «Tu biblioteca está limpia» | PASS |
| V-13 | `curl -s -X POST -H 'Origin: http://127.0.0.1:18000' http://127.0.0.1:18000/ui/auditoria/adoptar` y **esperar**: es en segundo plano | `GET /api/revision/carpetas` pasa a `grupos = 1`, `Comics/Flash (1987)` con **121** archivos | PASS; se anota cuánto tardó |
| V-14 | Comprobar que no se movió nada: `find /srv/zascarr-val/biblioteca -type f -printf '%P %s %T@\n' \| sort \| sha256sum` antes y después | Mismo hash | FAIL si cambia |
| V-15 | `docker logs zascarr-val-orquestador 2>&1 \| grep -iE 'comicvine\|anilist\|tebeosfera\|comics.org'` | Sin llamadas a fuentes | PASS si no hay ninguna |
| V-16 | `docker logs zascarr-val-orquestador 2>&1 \| grep -iE 'traceback\|error'` | Sin errores tras el arranque (el aviso de «ciclo omitido sin aceptación legal» es normal) | PASS |

### 5.1 Crear la serie «a mano» (operador, por API)

Hoy **no hay camino por la interfaz** para crear una serie sin fuentes (el tramo de alta no está asignado): se hace por
la ruta sin carpeta, que no consulta nada. Es un paso de preparación, no parte del recorrido de la persona.

```bash
B=http://127.0.0.1:18000
T=$(curl -s -X POST -H "Origin: $B" -H 'Content-Type: application/json' \
      -d '{"manual":{"titulo":"Flash","anio":1987},"tradicion":"american"}' \
      $B/api/revision/serie/sin-carpeta/previsualizar | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
SID=$(curl -s -X POST -H "Origin: $B" -H 'Content-Type: application/json' -d "{\"token\":\"$T\"}" \
      $B/api/revision/serie | python3 -c 'import json,sys; print(json.load(sys.stdin)["serie"]["series_id"])')
echo "$SID"
```

| ID | Qué hacer | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-17 | Lo anterior | Devuelve un UUID de serie | PASS |

## 6. El recorrido de la persona (V-20…V-29), por la interfaz

Desde el portátil, con un túnel (la interfaz **no** se abre a la red):

```bash
ssh -L 18000:127.0.0.1:18000 usuario@<la-pi>        # y se abre http://127.0.0.1:18000 en el navegador
```

Entrada: `http://127.0.0.1:18000/ui/pendientes/carpetas/asistente/vinculacion?clave=Comics%2FFlash%20(1987)&series_id=<SID>`

| ID | Acción | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-20 | «Pendientes por carpeta» | Aparece la carpeta con 121 registros y el enlace «Elegir la serie de esta carpeta» | PASS |
| V-21 | Abrir ese enlace | Muestra la carpeta, 121 registros y «no ha consultado ninguna fuente». Con las fuentes apagadas, al buscar dice **«No hay ninguna fuente activa»** y ofrece crear a mano | PASS |
| V-22 | Abrir la entrada de arriba | 100 archivos **sin ninguno marcado**, sin lote; «archivos 1–100» y «valen solo para esta página» | PASS |
| V-23 | Marcar 3 archivos y escribir otro número en uno | Cada cambio renueva la vista; «Lote preparado: 3 archivos»; el número escrito pone «Escrito por ti» | PASS |
| V-24 | «Página siguiente» y volver | En la 2.ª no hay nada marcado y sale «Trabajo guardado en otras páginas»; al volver se recupera lo marcado y se revisa de nuevo | PASS |
| V-25 | Confirmar «Vincular 3 archivos» | «Hecho: todos los archivos del lote quedaron vinculados»; 3 vinculados; **no** cambia nada más | PASS |
| V-26 | Recargar el navegador (F5) en la página del resultado | No vuelve a vincular nada (un `GET` no confirma) | PASS |
| V-27 | Marcar 2 archivos, **cambiar uno en disco** (`echo x >> "…/Flash 010 (1987).cbz"`) y confirmar | «Vinculación parcial»; «Esto NO está completo»; 1 pendiente con «Cambió (tamaño o fecha) mientras revisabas» | PASS |
| V-28 | «Revisar de nuevo» | Vista nueva, sin lote; el archivo cambiado vuelve a poder marcarse y confirmarse | PASS |
| V-29 | `Sin numero.cbz`: marcarlo | No es marcable: «Falta el número»; escribir un número lo hace marcable | PASS |

Se anota, para cada paso, el tiempo percibido; si algún paso tarda **más de 5 s**, se anota cuál (no es FAIL: es dato).

## 7. Recuperación y restauración (V-30…V-36)

```bash
# Variables de comodidad (API; Origin obligatorio en POST)
post() { curl -s -X POST -H "Origin: $B" -H 'Content-Type: application/json' -d "$2" "$B$1"; }
```

| ID | Qué hacer | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-30 | Preparar un lote (previsualizar con `marcados`), **confirmar**, y justo después `docker kill zascarr-val-orquestador && docker start zascarr-val-orquestador`; esperar `/api/health`; repetir **el mismo token** | `repetida: true`, **mismo** `operacion_id` y mismos totales; las filas vinculadas no cambian | PASS |
| V-31 | Dos confirmaciones **a la vez** con el mismo token (`post … & post … & wait`) | Una `repetida:false` y otra `true`; los archivos vinculados no se duplican | PASS |
| V-32 | **Token caducado:** previsualizar, esperar **16 min**, confirmar | `410 token_caducado`, `puede_haberse_aplicado:false`, sin cambios | PASS |
| V-33 | **Restaurar la BD de la pila de validación** (comandos de abajo) | Mismos recuentos antes y después; `health` con `database=ok`; los pendientes vuelven a salir | PASS |
| V-34 | Tras V-33, repetir el token de V-30 | Devuelve el mismo informe (el informe viaja en la copia) | PASS |
| V-35 | **Reiniciar la Pi** (`sudo reboot`), con la pila de validación ya creada | Tras arrancar, la pila vuelve a estar sana sin intervención y conserva el estado (§5 V-10) | PASS / NOT RUN si no se puede reiniciar |
| V-36 | Con el disco de la pila casi lleno (opcional, solo en la biblioteca de prueba) | La app lo dice en español y no borra nada | NOT RUN por defecto |

```bash
# V-33: copia y restauración de ESTA pila (no usar backup.sh ni rollback.sh)
mkdir -p /srv/zascarr-val/backup
"${C[@]}" exec -T postgres pg_dump -U comics_admin zascarr | gzip > /srv/zascarr-val/backup/validacion.sql.gz
gzip -t /srv/zascarr-val/backup/validacion.sql.gz                     # íntegro, o se para
Q="select (select count(*) from files where issue_id is not null), (select count(*) from issues), (select count(*) from vinculacion_operaciones), (select count(*) from series)"
"${C[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc "$Q"   # ANTES
"${C[@]}" stop zascarr
"${C[@]}" exec -T postgres dropdb -U comics_admin --force zascarr
"${C[@]}" exec -T postgres createdb -U comics_admin zascarr
gunzip -c /srv/zascarr-val/backup/validacion.sql.gz | \
  "${C[@]}" exec -T postgres psql -U comics_admin -d zascarr -v ON_ERROR_STOP=1 -q >/dev/null
"${C[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc "$Q"   # DESPUÉS: debe ser idéntico
"${C[@]}" start zascarr
```

## 8. Medición de confirmar 100 archivos (D8) (V-50…V-53)

Convierte «100 archivos» de hipótesis en dato. **Antes de medir, el responsable del producto fija el umbral** (el
repositorio no tiene ninguno y este guion no lo inventa). Propuesta para aceptar o cambiar: **confirmar 100 archivos
en < 30 s, sin errores ni `503`, y con la memoria del contenedor por debajo de su tope**.

```bash
SID=<el UUID de la serie de §5.1> python3 - <<'EOF'
import json, os, subprocess, time, urllib.error, urllib.request
B = "http://127.0.0.1:18000"; CLAVE = "Comics/Flash (1987)"; SID = os.environ["SID"]
def temperatura():
    try:
        return subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return "(sin vcgencmd)"
def post(ruta, cuerpo):
    req = urllib.request.Request(B + ruta, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": B})
    t = time.perf_counter()
    try:
        r = urllib.request.urlopen(req, timeout=600); return r.status, json.loads(r.read()), time.perf_counter() - t
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), time.perf_counter() - t
for ronda in range(1, 4):
    _, p, t_prev0 = post("/api/revision/vinculacion/previsualizar", {"clave": CLAVE, "series_id": SID})
    ids = [a["id"] for a in p["archivos"] if a["marcable"]]
    if len(ids) < 100: print("ronda", ronda, "solo", len(ids), "marcables: faltan archivos"); break
    st, p, t_prev = post("/api/revision/vinculacion/previsualizar", {"clave": CLAVE, "series_id": SID, "marcados": ids[:100]})
    st2, r, t_conf = post("/api/revision/vinculacion", {"token": p["token"]})
    temp = temperatura()
    print(f"ronda {ronda}: previsualizar={t_prev:.2f}s confirmar={t_conf:.2f}s http={st2} "
          f"global={r.get('resultado', {}).get('global')} vinculados={r.get('resultado', {}).get('totales', {}).get('vinculados')} {temp}")
EOF
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep zascarr-val
```

| ID | Qué | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-50 | Tres rondas de 100 | `confirmar` por debajo del umbral aceptado en cada una; `global = vinculados_todos`; `vinculados = 100` | PASS / FAIL por ronda |
| V-51 | Memoria durante la confirmación (`docker stats` en otra terminal) | Sin pasar el tope del contenedor; sin reinicios (`docker inspect -f '{{.RestartCount}}' zascarr-val-orquestador` = 0) | PASS |
| V-52 | Páginas: con ≥ 321 archivos, ir a la 2.ª y 3.ª página en la interfaz | Cada página tarda lo razonable; el borrador por página funciona (V-24) | PASS / dato |
| V-53 | Mismo recorrido con la **Pi usada** (Kavita, Transmission y Prowlarr en marcha) | Se repite V-50 una vez con la carga normal | dato (importa más que el vacío) |

## 9. No-efectos y aislamiento (V-40…V-43) — un FAIL aquí para el guion

| ID | Qué hacer | Oráculo | PASS / FAIL |
|---|---|---|---|
| V-40 | Manifiesto de la biblioteca de prueba antes y después de todo el guion (V-14) | **Idéntico**: nombres, tamaños y fechas. Vincular no mueve ni renombra | FAIL si cambia |
| V-41 | `ss -tlnp \| grep -E '5432\|6379\|18000'` | Solo `127.0.0.1:18000`; **ni 5432 ni 6379 de la pila de validación** | FAIL si hay otra |
| V-42 | `docker logs zascarr-val-orquestador` y los de `zascarr-val-db` | Sin rutas ni nombres de archivo en los avisos de error (CLAUDE.md §5.4) | FAIL si salen |
| V-43 | Repetir **V-04**: `docker ps` y los recuentos de la BD **real** | Producción **idéntica**: mismos contenedores y estados, mismos recuentos | FAIL si cambia |

## 10. Qué se ensayó ya (sandbox x86, 2026-10-13) y qué NO

Ensayado en una máquina x86 con Docker Compose v5.5 sobre `main` en `80014ce` (incluye #118–#120), con **la pila
aislada de §4**, 121 CBZ sintéticos y **sin tocar nada fuera de `/tmp`**:

| Qué | Resultado |
|---|---|
| `docker compose config` con el fichero de §4.2 | Sin puertos de Postgres/Redis; app en `127.0.0.1:18000`; datos y biblioteca en la carpeta de prueba |
| Migrar, arrancar, adoptar la biblioteca | `database=ok`; 1 grupo, 121 archivos; biblioteca sin cambios |
| Crear serie a mano + previsualizar + confirmar **100** archivos | `vinculados_todos`, 100 vinculados, 100 números nuevos; **0,33 s** (x86, 8 CPU) |
| Repetir el token | `repetida: true`, 0,01 s, mismos totales |
| **Medición de §8, 3 rondas de 100** (con el script literal de §8, 320 archivos) | `previsualizar` 0,03–0,06 s; `confirmar` **0,35 / 0,28 / 0,28 s**; `vinculados_todos` ×3; 0 reinicios del contenedor; app ~86 MB (x86, 8 CPU, NVMe: **no extrapolable a la Pi**) |
| Confirmar 20 + `docker kill` + `docker start` + repetir el token | Misma operación, `repetida: true`, mismos totales, **biblioteca idéntica** |
| `pg_dump` → `dropdb` → `createdb` → restaurar | Recuentos idénticos (120 / 120 / 2 / 1); salud `ok`; pendientes correctos |
| Uso de memoria en reposo | app ~90 MB, Postgres ~100 MB, Redis ~4–12 MB |

**No se ensayó (sigue NOT RUN):** nada en la Pi; la **interfaz web** de V-20…V-29 (cubierta por pruebas automáticas y
una comprobación en navegador en las PR #185–#187, no por este guion); V-32 (espera de 16 min), V-35 (reinicio),
V-36 (disco lleno) y V-53 (Pi con carga).

### Hallazgos del ensayo

1. **El compose base publica Postgres y Redis en `127.0.0.1`** (5432 y 6379): una segunda pila en el mismo equipo chocaría
   con producción. Por eso §4.2 usa `ports: !override []` (hace falta Compose ≥ 2.24).
2. **Hay que migrar antes de usar la pila nueva**; si no, `/api/health` dice `migration_required` y la interfaz no sirve.
3. **El estado `degraded` es normal** en la pila aislada (sin Transmission, aMule ni VPN); no es un fallo.
4. **Dos CBZ iguales son duplicados**: una biblioteca de prueba con archivos idénticos no se registra como archivos distintos.
5. **Adoptar es asíncrono** («puedes cerrar la página»): hay que sondear `GET /api/revision/carpetas`.
6. **No hay camino por la interfaz para crear una serie sin fuentes** (§5.1): confirma que el tramo de alta sigue siendo
   el hueco del MVP.
7. **`backup.sh` y `rollback.sh` no sirven para esta pila** (apuntan al proyecto por defecto): se documentan los
   comandos explícitos.
8. **Lo que se añade a la biblioteca después de registrarla no se recoge** por esta vía (el registro queda «hecho»;
   los archivos nuevos llegan por descargas). La biblioteca de prueba se genera entera **antes** de adoptar.

## 11. Informe de la ejecución (plantilla)

Un fichero por ejecución, **sin nombres de archivo ni rutas reales**:

```
Fecha / quién:            commit:           equipo (V-00):
Pila: aislada (sí/no)   Biblioteca: sintética | copia   Archivos: N
Umbral D8 aceptado (V-50):
| ID | Resultado (PASS/FAIL/NOT RUN) | Evidencia (salida, tiempo, captura) | Notas |
Resumen:  PASS n · FAIL n · NOT RUN n
FAIL de seguridad (V-40…43): ninguno | cuáles
Producción tocada: no | sí (qué)
Decisión que se pide: …
```

## 12. Al terminar

1. Guardar el informe y la evidencia **antes** de limpiar.
2. `"${C[@]}" down -v` y borrar `/srv/zascarr-val` (la copia `validacion.sql.gz` solo contiene datos sintéticos).
3. Comprobar con `docker ps -a` que **no queda ningún contenedor `zascarr-val-*`** y que los de producción siguen igual.
4. El **despliegue** sobre la instalación real es una decisión posterior, con su propia copia de seguridad y, si hay
   migraciones, la restauración probada (`update.sh` / `rollback.sh`), y no forma parte de este guion.
