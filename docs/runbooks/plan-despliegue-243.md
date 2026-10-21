# Plan de despliegue — #243 (fuentes de metadatos apagadas por defecto) y todo lo fusionado desde la versión de la Pi

> **Estado: EJECUTADO DE HECHO por el PO en cuatro actualizaciones (ver §9); verificación 5.2–5.4 pendiente.** El texto de abajo es el plan original (no se ejecutó paso a paso: el PO actualizó la Pi por su cuenta). (Alcance ampliado el 2026-10-21 a todo lo fusionado desde `625a564`: ver §0.) Nada de este documento se ejecuta en la Raspberry Pi hasta que el PO lo autorice **paso a paso**
> (fusión y despliegue son decisiones separadas). Quien ejecuta marca cada casilla y anota la hora; la evidencia se guarda
> en un paquete con su `.sha256`. Un fallo **detiene** el plan; no se improvisa.

## 0. Alcance y condiciones previas

- **Qué se despliega (corregido el 2026-10-21):** **todo lo fusionado en `main` desde el SHA que la Pi tiene hoy (`625a564`, #242)**, no solo #243.
  `update.sh` hace `git merge --ff-only origin/main`: lo que llega es la cabeza, con todo lo que hay debajo. Son **14 PR con código** (de 20 fusionadas)
  (más las de solo documentación). Por riesgo:

  | Área | PR | Efecto en la Pi |
  |---|---|---|
  | **Datos / migración** | #243 (ADR 0013) | Migración **0020** (`fuentes_heredadas`), cuatro fuentes de metadatos con `default=False`, aviso en Ajustes. **Es la única migración** del conjunto (`alembic/versions/` solo añade `0020`). |
  | **Legal** | #243 y #267 | `LEGAL.md` cambia **dos veces** (#243 y #267: sin marcas `[web:N]`, listas separadas). `legal_version` es el hash del fichero: lo que cuenta es el de la cabeza desplegada, y hay **una sola** reaceptación (paso 4). |
  | **Funcionalidad nueva** | #259 (BL-R1a) y #268 (BL-R1b) | «Desvincular» un archivo: API (`/api/revision/desvinculacion*`), servicio y la sección «Archivos por número» de la ficha de la serie. **Sin migración.** No actúa por sí solo: solo si la persona confirma. |
  | **Interfaz** | #248, #249, #251, #252, #256, #257, #258, #260, #261, #269 | Tipografía propia y marca (ficheros nuevos en `static/vendor/fonts` y `static/brand`), Inicio con cifras que cuadran, Estado y Ajustes en lenguaje llano, página de error propia, logo. Sin cambios de datos. |
  | **Documentación / diseño** | #244–#247, #250, #255, … | Solo `docs/`. |

  **Lo que NO cambia en el delta** (`git diff 625a564..<SHA> -- scripts docker-compose.yml Dockerfile alembic`): `scripts/`, `docker-compose.yml` y el `Dockerfile` no se tocan; `alembic/` solo añade `0020`; `pyproject.toml` solo amplía los ficheros de datos del paquete (`static/vendor/fonts`, `static/brand`).
- **Cabeza revisada de la PR #243:** `46bd09b969f5d9a544dc592574198d744b682f92`.
- **SHA a desplegar:** `SHA_DESPLIEGUE` = la **cabeza de `origin/main` en el momento de autorizar el despliegue** (se anota en 0.2; `git ls-remote origin refs/heads/main`).
  - `update.sh` hace `git merge --ff-only origin/main`, así que a la Pi llega **esa cabeza**, no el *merge commit* de #243.
  - Referencias conocidas: #243 → `4ab462b1a7d0088658f1f88abf267376c8d03b8e` (**el código desplegado**); #244 → `cdf36e9552c6f9fabd0a2062b37c93e37fc94f40` (solo documentación, CI verde). Cada PR de solo documentación que se fusione después **mueve la cabeza** (esta incluida): por eso el SHA no se fija en el texto del plan, se anota al autorizar.
  - **Comprobación de seguridad (0.2), reescrita:** el plan original exigía que `4ab462b..SHA_DESPLIEGUE` fuera solo `docs/`; ya no vale, porque entre medias hay código revisado y probado (arriba). En su lugar, **dos comprobaciones**:
    1. `git diff --stat 625a564..SHA_DESPLIEGUE -- scripts docker-compose.yml Dockerfile alembic pyproject.toml` lista **solo** `alembic/versions/20261019_0020_*.py` y `pyproject.toml`. Cualquier otro fichero (otra migración, `scripts/`, `docker-compose.yml`, `Dockerfile`) → **no se despliega**: se informa al PO y se reevalúa.
    2. `git log --first-parent --oneline 625a564..SHA_DESPLIEGUE` no contiene ninguna PR con código **que no esté en la tabla de arriba**. Si aparece una, el PO la revisa antes de seguir.
  - Cada PR de solo documentación que se fusione después **mueve la cabeza** sin cambiar el código; basta repetir las dos comprobaciones y la CI (0.3) sobre la nueva cabeza.
  - Si `main` avanza entre 0.2 y 3, se rehacen 0.2–0.3 con la nueva cabeza.

- **No autorizado hasta nueva orden del PO** (cada uno es un paso separado): fusionar #243 · desplegar en la Pi · aceptar el aviso legal
  en la Pi · ejecutar un rollback · cambiar el tablero.

- [ ] 0.1 PO autoriza **fusionar** #243 (anotar fecha y quién): ____________
- [ ] 0.2 #243 fusionada (`4ab462b`). `SHA_DESPLIEGUE` = cabeza actual de `origin/main`: `____________________`. Contiene la migración `20261019_0020_*` y el `LEGAL.md` de #243 **y** #267, y pasan las dos comprobaciones de seguridad de arriba (anotar la salida en la evidencia).
- [ ] 0.3 CI bloqueante **en verde sobre `SHA_DESPLIEGUE` exacto** (no sobre `4ab462b` ni sobre una cabeza anterior) (Suite unitaria, Pruebas con Postgres real, Docker build, pip-audit; `ruff` informativo puede estar en rojo).
- [ ] 0.4 PO autoriza **desplegar en la Pi** con ese SHA (fecha/quién): ____________
- [ ] 0.5 Ventana acordada y la persona que aceptará el aviso legal está presente (paso 4).
- [ ] 0.6 **Ruta real de la biblioteca en la Pi fijada y anotada en la hoja de evidencia (§8)**: `RUTA_BIBLIOTECA = /media/WDElements/Tebeos` (confirmada por el PO el 2026-10-20). Se usa en 2.3 y 3.6; no se deja por decidir el día de la ejecución. **Es un disco externo: comprobar que está montado** antes de cualquier inventario (`findmnt /media/WDElements` debe responder). **Un aviso de montaje obliga a parar y consultar al PO; no se continúa**: un inventario de un disco no montado saldría vacío y parecería «sin cambios».
- [ ] 0.7 **Condición de entrada (§1.3):** la predicción de la migración 0020 está **escrita y revisada por el PO** (nombre/fecha: ____________). **No se ejecuta `update.sh` mientras esta casilla esté sin marcar.**

## 1. Estado previo (solo lectura) y qué se espera

Se ejecuta en la Pi como el usuario habitual, **antes** de tocar nada. Las consultas devuelven **solo** estas claves; no imprimir nunca `runtime_settings.values` completo (contiene secretos).

```bash
EV=/home/pi/evidencia-despliegue-243-$(date +%Y%m%d_%H%M%S); mkdir -p "$EV"
git -C /opt/zascarr/zascarr rev-parse HEAD  > "$EV/sha-antes.txt"
docker exec zascarr-db psql -U comics_admin -d zascarr -tAc 'select version_num from alembic_version' > "$EV/alembic-antes.txt"
docker exec zascarr-db psql -U comics_admin -d zascarr -tAc \
  "select coalesce(\"values\"->>'fuentes_heredadas','(ausente)'), coalesce(\"values\"->>'comicvine_enabled','(ausente)'), coalesce(\"values\"->>'anilist_enabled','(ausente)'), coalesce(\"values\"->>'tebeosfera_enabled','(ausente)'), coalesce(\"values\"->>'gcd_enabled','(ausente)') from runtime_settings where id=1" > "$EV/fuentes-antes.txt"
curl -sS -m 15 http://127.0.0.1:8000/api/legal/status > "$EV/legal-antes.json"
curl -sS -m 15 http://127.0.0.1:8000/api/health   > "$EV/health-antes.json"
sudo sha256sum /opt/zascarr/.env | cut -d' ' -f1 > "$EV/env-sha256-antes.txt"      # SOLO el hash; nunca el contenido
```

- [ ] 1.1 `sha-antes.txt` = el SHA que la Pi ya tenía (`625a564…` en la última validación) y el árbol está limpio (`git status` sin cambios).
- [ ] 1.2 `alembic-antes` = `0019`.
- [ ] 1.3 **Predicción del resultado de la 0020** según `fuentes-antes.txt`. **Es condición de entrada (0.7): se escribe en `prediccion-0020.txt` y la revisa el PO antes de actualizar.**

| `fuentes-antes` (heredado, 4 claves) | Es el caso | Esperado tras la 0020 |
|---|---|---|
| `(ausente)` en las cuatro | Con uso previo, sin preferencia | `fuentes_heredadas = true`; las cuatro `true` |
| Las cuatro presentes (`true`/`false`) | Preferencia ya guardada | **Sin cambio** y sin marcador (`(ausente)`) |
| Solo algunas presentes | Decisión parcial (no debería darse: el formulario guarda las cuatro) | Las presentes se respetan, las ausentes pasan a `true`, sin marcador |
| *(Instalación nueva)* | **No aplica a la Pi**; lo cubren `tests/test_migracion_fuentes_pg.py` | Sin marcador, apagadas |

- [ ] 1.4 Hay una instalación de la Pi con uso previo (series/ficheros/ciclos del importador) → la 0020 se aplicará en alguno de los tres primeros casos.

## 2. Copias de seguridad (qué cubre `update.sh` y qué NO)

| Qué | Cómo | Alcance |
|---|---|---|
| **PostgreSQL** | Copia **completa** (`pg_dump`) gestionada por `update.sh`: `update_<TS>.sql.gz` en `/var/backups/zascarr/postgres`, verificada con `gzip -t`, más la referencia de rescate `refs/zascarr/update/<TS>` | Copia real y restaurable (la usa `rollback.sh`) |
| **`.env`** | Copia **interna en la Pi** (root, modo 600); a la evidencia va **solo su SHA-256** | Nunca sale de la Pi |
| **Biblioteca** | **Verificación por inventario** (ruta, tamaño y fecha de todos los ficheros + SHA-256 de una muestra determinista, antes y después) | **No es una copia física** |
| **Copia física de la biblioteca** | — | **Fuera del alcance de este plan.** Requeriría tamaño, destino y autorización aparte del PO |

`update.sh` **no copia el `.env` ni la biblioteca** (garantía A3: no toca la colección).

- [ ] 2.1 **Base de datos:** la hace `update.sh` en el paso 3; anotar la ruta y el SHA-256 (`sha256sum`) del `.sql.gz` y comprobar que se puede leer:
  ```bash
  sha256sum /var/backups/zascarr/postgres/update_<TS>.sql.gz | tee -a "$EV/backup-bd.sha256"
  gzip -t /var/backups/zascarr/postgres/update_<TS>.sql.gz && zcat /var/backups/zascarr/postgres/update_<TS>.sql.gz | head -c 2000 >/dev/null
  zcat /var/backups/zascarr/postgres/update_<TS>.sql.gz | grep -c -E '^CREATE TABLE (public\.)?(series|files|runtime_settings|legal_acknowledgments)\b' | tee "$EV/backup-bd-tablas.txt"   # 4 esperado
  ```
- [ ] 2.2 **Configuración (`.env`):** es un secreto y vive solo en la Pi. Antes de actualizar: copia con `sudo install -m 600 -o root -g root /opt/zascarr/.env /var/backups/zascarr/env-antes-despliegue-243` (queda **en la Pi**, nunca en la evidencia ni en Drive) y registrar **solo su SHA-256** (`env-sha256-antes.txt`).
- [ ] 2.3 **Biblioteca:** no se copia (el actualizador no la toca). Se toma un **inventario** antes y después para demostrar que no cambió: **ruta, tamaño y fecha de modificación de todos los ficheros**, y **SHA-256 de una muestra determinista** (un SHA-256 de toda la biblioteca en una Pi con disco USB puede tardar horas y aporta poco a este objetivo: tamaño y fecha detectan cualquier cambio relevante; la muestra añade comprobación de contenido).
  ```bash
  RUTA_BIBLIOTECA=/media/WDElements/Tebeos
  findmnt /media/WDElements >/dev/null || echo "DISCO NO MONTADO: PARAR Y CONSULTAR AL PO (no continuar con los comandos siguientes)"
  cd "$RUTA_BIBLIOTECA"
  # inventario completo: ruta <TAB> tamaño <TAB> mtime (ordenado, reproducible)
  sudo find . -type f -printf '%P\t%s\t%T@\n' | LC_ALL=C sort > "$EV/biblioteca-antes.tsv"
  N=$(wc -l < "$EV/biblioteca-antes.tsv"); echo "$N" > "$EV/biblioteca-n-ficheros.txt"          # esperado ≈ 1339 (files en la base)
  # muestra determinista: ~50 ficheros, 1 de cada K en el orden del inventario
  K=$(( N / 50 + 1 ))
  cut -f1 "$EV/biblioteca-antes.tsv" | awk -v k="$K" 'NR % k == 1' > "$EV/biblioteca-muestra-lista.txt"
  while IFS= read -r f; do sudo sha256sum -- "$f"; done < "$EV/biblioteca-muestra-lista.txt" > "$EV/biblioteca-muestra-antes.sha256"
  ```
  *Cómo se genera la muestra (reproducible):* se toma el inventario ordenado con `LC_ALL=C sort`, `N` = su número de líneas, `K = N / 50 + 1` (división entera) y se eligen las líneas `1, K+1, 2K+1, …` (`awk 'NR % K == 1'`), es decir, ~50 ficheros repartidos por toda la biblioteca. El mismo inventario y el mismo `K` dan la misma muestra; se guardan `biblioteca-n-ficheros.txt` y `biblioteca-muestra-lista.txt` en la evidencia.
  *Limitación:* nombres con salto de línea romperían el TSV; si `find` y el inventario no coinciden en número (`find . -type f | wc -l` ≠ `N`), se detiene y se reevalúa.
  La copia física de la biblioteca queda fuera de este plan (ver la tabla de arriba).
- [ ] 2.4 Paquete de evidencia previa con hash: `tar -czf "$EV.tar.gz" -C /home/pi "$(basename "$EV")" && sha256sum "$EV.tar.gz" > "$EV.tar.gz.sha256"`.

## 3. Actualización (autorizada en 0.4)

```bash
sudo bash /opt/zascarr/zascarr/scripts/update.sh 2>&1 | tee "$EV/update.log"
```
- [ ] 3.1 `update.sh` termina con "Actualización completada" (RC 0); `NEW_SHA` = `SHA_DESPLIEGUE`.
- [ ] 3.2 Aparece el backup `update_<TS>.sql.gz`; cumplir 2.1 con ese `<TS>`.
- [ ] 3.3 `alembic` tras actualizar = **`0020`**:
  `docker exec zascarr-db psql -U comics_admin -d zascarr -tAc 'select version_num from alembic_version' | tee "$EV/alembic-despues.txt"`.
- [ ] 3.4 `/api/health` → 200; contenedores `zascarr-orquestador` y `zascarr-db` en `healthy` (`docker ps`); `credenciales` terminado con código 0.
- [ ] 3.5 `.env` byte a byte: `sudo sha256sum /opt/zascarr/.env` = `env-sha256-antes.txt`.
- [ ] 3.6 Biblioteca intacta, **con el disco montado** (`findmnt /media/WDElements`): repetir el inventario de 2.3 como `biblioteca-despues.tsv` y comprobar `diff "$EV/biblioteca-antes.tsv" "$EV/biblioteca-despues.tsv"` **vacío** (ruta, tamaño y mtime), y `cd "$RUTA_BIBLIOTECA" && sudo sha256sum -c "$EV/biblioteca-muestra-antes.sha256"` → **todo OK**. Cualquier diferencia: se detiene y se informa al PO (no se repara).

## 4. Reaceptación legal (consecuencia esperada del cambio de política)

`LEGAL.md` cambia y su `legal_version` es el hash del fichero. **Esto no revoca un consentimiento previo:** la política de fuentes de metadatos cambia y la aplicación pide una **confirmación nueva** antes de que el orquestador reanude su funcionamiento.

- [ ] 4.1 `curl -sS http://127.0.0.1:8000/api/legal/status` → `"accepted": false` y `legal_version` distinta de la de `legal-antes.json` (guardar como `legal-despues-actualizar.json`).
- [ ] 4.2 El orquestador está detenido: en `docker logs zascarr-orquestador` aparece `orchestrator.cycle_skipped_no_legal_acknowledgment`. **Es lo esperado**, no un fallo.
> **Regla (no práctica informal):** el nombre de quien acepta se registra **únicamente en la hoja de evidencia** (§8 / `aceptacion-legal.txt`).
> **No se añade a la base de datos ni a `LEGAL.md` ningún dato personal**; `legal_acknowledgments` conserva solo `accepted_at` y `legal_version`.

- [ ] 4.3 **La persona autorizada por el PO** abre `http://127.0.0.1:8000/ui/legal` y acepta (3 casillas). Anotar nombre y hora **en la hoja de evidencia** (`aceptacion-legal.txt`): ZascArr no guarda quién acepta (`legal_acknowledgments` solo tiene `accepted_at` y `legal_version`, sin usuario) y no se añade ningún dato personal.
- [ ] 4.4 `curl … /api/legal/status` → `"accepted": true` con la `legal_version` nueva y `accepted_at` coherente con 4.3 (`legal-despues-aceptar.json`).
- [ ] 4.5 Reanudación: tras el siguiente ciclo del orquestador (hasta `scan_interval_minutes` = 60 min; el ciclo del importador es de 15) la línea `…skipped_no_legal_acknowledgment` **deja de repetirse**. Anotar el log de ese ciclo.

## 5. Verificación posterior específica de #243

### 5.1 Migración 0020 (`fuentes_heredadas`)
Repetir la consulta de 1 y guardar como `fuentes-despues.txt`; comparar con la **predicción de 1.3**:
- [ ] Caso "ausentes" → `fuentes_heredadas = true` y las cuatro `true`.
- [ ] Caso "preferencia guardada" → idéntico a `fuentes-antes.txt`, `fuentes_heredadas` = `(ausente)`.
- [ ] Caso "parcial" → conforme a la tabla de 1.3.
- [ ] La salida **no** contiene ninguna otra clave de `runtime_settings` (nada de secretos en la evidencia).

### 5.2 Aviso de Ajustes
> **Acceso:** si la instancia requiere autenticación, el operador debe tener una **sesión válida (cookie)** antes de ejecutar el `grep` sobre `/ui/ajustes`; en una instalación local sin autenticación no hace falta. **La cookie se comprueba al preparar la ventana (p. ej. abriendo `/ui/ajustes` en el navegador con esa sesión), no en mitad del despliegue.**

- [ ] Si `fuentes_heredadas = true`: `curl -s http://127.0.0.1:8000/ui/ajustes | grep -c 'id="aviso-fuentes-heredadas"'` → **1**; la página dice «…activadas por compatibilidad con tu instalación anterior…».
- [ ] Si no es heredado: el mismo `grep -c` → **0**.
- [ ] (Solo si es heredado) **El PO decide** si se confirma ya: abrir Ajustes → «Fuentes de metadatos» → **Guardar** (sin cambiar nada, o apagando las que quiera). Después: `grep -c` → **0** y `fuentes_heredadas = false` en la consulta de 5.1 (`fuentes-despues-guardar.txt`). Guardar **otra** tarjeta no debe quitar el aviso.
- [ ] Tras `docker restart zascarr-orquestador`: el aviso (si seguía) y el estado de las fuentes **persisten** (`/api/health` → `fuentes` coincide con la base).

### 5.3 Que nada más cambió
- [ ] `/api/health`: `database: ok`; `fuentes` conforme a 5.1.
- [ ] `docker logs zascarr-orquestador --since 30m` sin tracebacks nuevos.
- [ ] Paquete final de evidencia con `.sha256` (`$EV-final.tar.gz`), sin `.env` ni valores secretos (revisar por patrones antes de compartir).

### 5.4 Lo fusionado además de #243 (solo lectura: no se confirma nada sin orden del PO)
- [ ] **Interfaz:** `/ui/`, `/ui/biblioteca`, `/ui/pendientes`, `/ui/wishlist`, `/ui/ajustes`, `/estado` responden 200 y se ven con la tipografía y la marca nuevas (sin peticiones a servidores externos de fuentes: son ficheros locales). Una ruta inexistente (`/ui/no-existe`) muestra la página de error propia, no JSON.
- [ ] **BL-R1 (lista y vista previa):** abrir la ficha de una serie con archivos: aparece «Archivos por número» con «Desvincular» solo en los archivos vinculados con «Vincular en su sitio». Abrir la vista previa de **uno** (`GET`, solo lectura): se ve «¿Desvincular este archivo?» y el botón. **No se pulsa «Desvincular el archivo».**
- [ ] `curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/revision/desvinculacion/previsualizar -H 'Content-Type: application/json' -d '{"file_id":"00000000-0000-0000-0000-000000000000"}'` → **404** (archivo inexistente) y el contador de «Por revisar» no cambia.
- [ ] **Desvincular de verdad en la biblioteca real (opcional):** solo si el PO lo autoriza **sobre un archivo concreto** que él elija (la operación es recuperable —el archivo vuelve a «Por revisar» y se puede volver a vincular— pero cambia la base real). Anotar el archivo y el resultado en la evidencia.

## 6. Criterios de éxito

Todas las casillas de 1–5 marcadas **y**: backup verificado (2.1) · migración `0020` aplicada (3.3) con el resultado previsto (5.1) · aviso correcto (5.2) · `.env` y biblioteca intactos (3.5, 3.6) · aceptación legal registrada (4.4) · orquestador reanudado (4.5) · interfaz y BL-R1 conforme a 5.4.

## 7. Rollback (NO se ejecuta sin autorización explícita del PO)

Disparadores: `update.sh` falla a partir de su paso 5, la 0020 no deja el resultado previsto, el aviso se comporta mal de forma persistente, o `/api/health` no vuelve a 200.

1. **Parar y avisar al PO.** No reintentar ni "arreglar sobre la marcha".
2. Con la autorización del PO: `sudo bash /opt/zascarr/zascarr/scripts/rollback.sh --dry-run` y revisar el plan (emparejado por `refs/zascarr/update/<TS>` + `update_<TS>.sql.gz`, **no** "el backup más reciente").
3. Con una segunda confirmación del PO: `sudo bash /opt/zascarr/zascarr/scripts/rollback.sh` (restaura la base y vuelve al SHA anterior; hace antes una copia de seguridad de la BD actual).
4. Comprobar: SHA = el de `sha-antes.txt`, `alembic` = `0019`, `/api/health` 200, `.env` y biblioteca idénticos a 3.5/3.6.
5. Efectos a conocer: restaurar la base **deshace** la aceptación legal hecha después de actualizar, `fuentes_heredadas` y cualquier «Desvincular» confirmado después (BL-R1 no tiene migración: el código anterior ignora el historial `vinculo_historial` que haya quedado en `files.metadata`); con el código anterior las claves a `true` serían inofensivas (la bajada de la 0020 no hace nada a propósito).

## 8. Registro de ejecución

| Paso | Hora | Quién | Resultado | Evidencia |
|---|---|---|---|---|
| 0.1 fusión autorizada | | | | |
| 0.6 ruta de la biblioteca fijada y disco montado | | | `RUTA_BIBLIOTECA=/media/WDElements/Tebeos` | |
| 0.7 predicción 0020 revisada por el PO | | | | `prediccion-0020.txt` |
| 0.4 despliegue autorizado | | | | |
| 3 `update.sh` | | | | `update.log` |
| 4.3 aceptación legal | | | | `aceptacion-legal.txt` |
| 5.2 aviso / guardar | | | | |

## 9. Registro real (2026-10-21): lo que ocurrió, frente al plan

El plan se redactó para **una** actualización con comprobaciones antes y después. En la práctica **el PO actualizó la Pi con `update.sh` cuatro veces** conforme se fusionaban PR, sin lanzar los pasos 1–3 del plan. Se descubrió al ejecutar `paso1` el 21 de octubre (la comprobación 1.1 saltó porque la Pi ya no estaba en `625a564`). Fuente: `git reflog` y `refs/zascarr/update/*` de la Pi, y `legal_acknowledgments`.

| Actualización (hora local) | De → a | Backup de la base (`/var/backups/zascarr/postgres`) | Qué trajo |
|---|---|---|---|
| 2026-10-20 20:26 | `625a564` → `8238acb` | `update_20261020_202609.sql.gz` | #243 con la migración **0020** (y las PR de documentación hasta #248) |
| 2026-10-21 00:42 | `8238acb` → `4035dc3` | `update_20261021_004230.sql.gz` | Interfaz |
| 2026-10-21 11:27 | `4035dc3` → `8589b47` | `update_20261021_112718.sql.gz` | #267 (`LEGAL.md`), BL-R1a (#259) |
| 2026-10-21 17:58 | `8589b47` → `134eae3` | `update_20261021_175846.sql.gz` | BL-R1b (#268), #271 (CSS y página de error) |

- **Aviso legal:** aceptado el 2026-10-20 22:45 UTC (versión `847503505cc41f74`, la de #243) y de nuevo el 2026-10-21 09:36 UTC (**`cf5bde4f949117a1`**, la de #267). El hash de `LEGAL.md` en `134eae3` (y en `main` a `a272172`) es `cf5bde4f949117a1`: **la aceptación vigente es la actual**. Ciclos del orquestador saltados por falta de aceptación en la última hora: 0.
- **Estado de la Pi a las 18:20 (`estado-actual.sh`, solo lectura, sin ✗):** `alembic = 0020`; fuentes `heredadas=true` y las cuatro `true` (el resultado previsto de la 0020 para una instalación con uso previo y sin preferencia guardada); `/api/health` 200; `zascarr-orquestador` y `zascarr-db` en `healthy`; 0 *tracebacks* en la última hora; copia más reciente legible (`gzip -t`, SHA-256 `e46bce5a…b817`); disco montado.
- **Paquete de evidencia:** `evidencia-estado-actual-20261021_182058.tar.gz`, SHA-256 `4cf22124f9dfca80cc0a983a637321d81ccceeeec285ebee2b2b57c940386b94` (en la Pi; el `.env` no está, solo su hash).
- **Lo que NO existe:** el estado «antes» de la 0020 medido con `paso1` (`fuentes-antes.txt`, inventario previo de la biblioteca, hash del `.env` previo). Queda la copia de la base de la primera actualización, de donde se podría reconstruir restaurándola en una base temporal (no hecho). Por tanto **no se puede demostrar** que la 0020 partiera del caso «ausentes»; solo que el resultado es coherente con él, ni que la biblioteca no cambió durante las actualizaciones (el actualizador no la toca, A3, pero no hay inventario previo).
- **Biblioteca:** 1577 ficheros inventariados (el plan esperaba ≈ 1339, la cifra de `files` en la base cuando se escribió). **Sin explicar todavía**: puede ser que la biblioteca haya crecido o que haya ficheros que no son tebeos; se comprueba contra `select count(*) from files` sin tocar nada.
- **Pendiente de verificar (solo lectura, §5.2–5.4):** aviso de Ajustes (`fuentes_heredadas = true`, decide el PO si pulsa «Guardar»), la ficha con «Archivos por número», la vista previa de un archivo (**sin pulsar «Desvincular el archivo»**), la página de error propia.
- **Fuera de este despliegue:** `main` está en `a272172` (#273, interfaz) y **no** se ha desplegado.
