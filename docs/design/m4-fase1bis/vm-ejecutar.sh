#!/usr/bin/env bash
# =============================================================================
# vm-ejecutar.sh — M4 · Fase 1 bis (#121). Se ejecuta DENTRO de la VM desechable, como root, con la RED CERRADA.
#
#     sudo bash vm-ejecutar.sh [sección ...]        # sin argumentos: todas, en orden
#
# Secciones, en este orden: antes · instalacion · fuentes_iniciales · salud · credenciales · reejecucion · originales ·
#   fuentes_persistencia · cierre.  Las fuentes se APAGAN justo tras instalar (ventana medida), no al final.
#   Códigos de salida: 0 · 1 FAIL · 2 precondición/controles del arnés (no se mide el producto) · 3 PARADA DE SEGURIDAD
#
# Imprime y registra (en $EV/resultados.txt) una línea por comprobación:   PASS id detalle · FAIL id detalle ·
# NOT_RUN id motivo. NUNCA imprime el valor de una credencial: solo estados, modos, longitudes y huellas.
#
# Parada de seguridad: si UN intento de lectura/modificación/sustitución/redirección por una identidad no administrativa
# TIENE ÉXITO, la fase se DETIENE (código de salida 3) sin reparar nada: un fallo de seguridad no se corrige sobre la
# marcha para convertir el intento inicial en PASS.
#
# Entradas (variables de entorno, las pone anfitrion.sh a partir de MANIFIESTO-CANDIDATO.txt):
#   CANDIDATO          SHA del commit del candidato (el espejo local debe tener main = CANDIDATO)
#   BOOTSTRAP_SHA256   huella del bootstrap.sh del candidato entregado en /home/ensayo/bootstrap.sh
#   ALEMBIC_ESPERADA   revisión de la cabeza de Alembic del candidato
#   CSS_SHA256         huella de src/zascarr/static/web.css del candidato
#   MUESTRAS           muestras de la observación de salud (una por minuto; por defecto 5)
# =============================================================================
set -uo pipefail

EV="${EV:-/root/ensayo/evidencia}"
RAIZ="${RAIZ:-/opt/zascarr}"
REPO="${RAIZ}/zascarr"
ENVF="${RAIZ}/.env"
BIBLIOTECA="${BIBLIOTECA:-/media/library}"
URL="${URL:-http://127.0.0.1:8000}"
MUESTRAS="${MUESTRAS:-5}"
SVC="${SVC:-media}"            # usuario de servicio que crea el instalador
OTRO="${OTRO:-otroprueba}"     # usuario local ordinario, sin sudo (lo crea vm-preparar.sh)
COMPOSE=(docker compose -f "${REPO}/docker-compose.yml" --env-file "${ENVF}")
mkdir -p "${EV}"
RES="${EV}/resultados.txt"
: >> "${RES}"

# ── utilidades ────────────────────────────────────────────────────────────────────────────────────────────────────
reg()  { echo "$1 $2 ${3:-}" | tee -a "${RES}"; }
pass() { reg PASS "$1" "${2:-}"; }
fail() { reg FAIL "$1" "${2:-}"; }
nr()   { reg NOT_RUN "$1" "${2:-}"; }
afirmar() { local id="$1" texto="$2"; shift 2; if "$@" >/dev/null 2>&1; then pass "${id}" "${texto}"; else fail "${id}" "${texto}"; fi; }
como() { local u="$1"; shift; runuser -u "${u}" -- "$@"; }
modo() { stat -c '%a %U:%G' -- "$1" 2>/dev/null; }
huella() { sha256sum -- "$1" 2>/dev/null | cut -c1-16; }
valor_env() { grep -E '^DB_PASSWORD=' "${ENVF}" 2>/dev/null | tail -n 1 | cut -d= -f2-; }
api() { curl -sS -m 15 "$@"; }
sec() { echo; echo "── $* ──" | tee -a "${RES}"; }

# Una prueba de seguridad que SE PUDO hacer detiene la fase (sin reparar).
parada_seguridad() {
    fail "$1" "$2 — SE PUDO HACER. Fase detenida; no se repara ni se continúa (código 3)"
    echo "PARADA DE SEGURIDAD: ${1}" | tee -a "${RES}"
    exit 3
}
# negar ID texto cmd… : PASS si el comando FALLA (se denegó); si TIENE ÉXITO, parada de seguridad.
negar() {
    local id="$1" texto="$2"; shift 2
    if "$@" >/dev/null 2>&1; then parada_seguridad "${id}" "${texto}"; else pass "${id}" "${texto}"; fi
}

# ── 0. antes ──────────────────────────────────────────────────────────────────────────────────────────────────────
inventario() {   # inventario ARCHIVO → ruta<TAB>tamaño<TAB>sha256 de cada fichero de la biblioteca (orden estable)
    ( cd "${BIBLIOTECA}" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum | awk '{h=$1; $1=""; sub(/^ /,""); print $0 "\t" h}' ) > "$1"
}
seccion_antes() {
    sec "ANTES: punto de partida limpio y huella de la biblioteca sintética"
    date -Is | tee "${EV}/00-inicio.txt" >/dev/null
    [[ ! -e "${RAIZ}" ]] && pass A-01 "no existe ${RAIZ} (instalación nueva)" || fail A-01 "ya existe ${RAIZ}"
    [[ ! -e /var/lib/zascarr ]] && pass A-02 "no existe /var/lib/zascarr (sin base de datos del producto)" || fail A-02 "ya existe /var/lib/zascarr"
    [[ "$(docker ps -aq | wc -l)" == "0" ]] && pass A-03 "sin contenedores" || fail A-03 "hay contenedores"
    ! getent passwd "${SVC}" >/dev/null && pass A-04 "el usuario de servicio '${SVC}' no existe todavía (lo crea el instalador)" \
        || fail A-04 "el usuario '${SVC}' ya existía"
    getent passwd "${OTRO}" >/dev/null && ! id -nG "${OTRO}" | grep -qw -e sudo -e adm -e docker \
        && pass A-05 "existe '${OTRO}', usuario ordinario sin sudo, adm ni docker" || fail A-05 "falta '${OTRO}' o tiene privilegios"
    inventario "${EV}/biblioteca-antes.tsv"
    find "${BIBLIOTECA}" -type d | sort > "${EV}/directorios-antes.txt"
    [[ "$(wc -l < "${EV}/biblioteca-antes.tsv")" -ge 1 ]] && pass A-06 "huella inicial de $(wc -l < "${EV}/biblioteca-antes.tsv") ficheros sintéticos" \
        || fail A-06 "biblioteca vacía"
    [[ -n "${BOOTSTRAP_SHA256:-}" && "$(sha256sum /home/ensayo/bootstrap.sh | cut -d' ' -f1)" == "${BOOTSTRAP_SHA256}" ]] \
        && pass A-07 "el bootstrap.sh entregado es el del candidato (SHA-256 ${BOOTSTRAP_SHA256:0:16}…)" || fail A-07 "el bootstrap.sh entregado no coincide con el manifiesto"
    [[ "$(git config --system --get url./srv/espejo/zascarr.git.insteadOf 2>/dev/null)" == "https://github.com/juanajok/zascarr.git" ]] \
        && pass A-08 "ADAPTACIÓN DEL ARNÉS registrada: git resuelve el repositorio del producto contra el espejo local del candidato" \
        || fail A-08 "no está configurado el espejo local"
    [[ "$(git -C /srv/espejo/zascarr.git rev-parse main 2>/dev/null)" == "${CANDIDATO:-sin-candidato}" ]] \
        && pass A-09 "el espejo tiene main = candidato" || fail A-09 "el espejo no apunta al candidato"
    if ! curl -sS -m 5 -o /dev/null https://github.com 2>/dev/null; then pass A-10 "red cerrada: sin salida a Internet"; else fail A-10 "HAY salida a Internet"; fi
    # Contador de bytes recibidos: toda la fase de ejecución debe ser ~0 (solo SSH).
    cat /sys/class/net/enp0s1/statistics/rx_bytes > "${EV}/rx-inicio.txt" 2>/dev/null || true
    # Una precondición fallida es un problema del ARNÉS o del ENTORNO (no del producto) y IMPIDE empezar la instalación:
    # medir el producto sobre un punto de partida que no es el declarado no tendría valor.
    ! grep -q '^FAIL A-' "${RES}"
}

# ── 1. instalación nueva ──────────────────────────────────────────────────────────────────────────────────────────
seccion_instalacion() {
    sec "INSTALACIÓN: bootstrap.sh del candidato, sin terminal, sin preparar DB_PASSWORD"
    [[ ! -e "${ENVF}" ]] || { fail I-00 "ya había un .env antes de instalar: no es una instalación nueva"; return 1; }
    local t0 t1 rc
    t0=$(date +%s)
    # Equivalente a `curl … | sudo bash` sin terminal: stdin cerrado, el instalador usa los valores por defecto.
    bash /home/ensayo/bootstrap.sh < /dev/null > "${EV}/bootstrap.log" 2>&1
    rc=$?
    t1=$(date +%s)
    echo "rc=${rc} segundos=$((t1 - t0))" > "${EV}/bootstrap.rc"
    [[ ${rc} -eq 0 ]] && pass I-01 "el instalador terminó con RC=0 en $((t1 - t0)) s, sin editar credenciales (el arnés no escribió el .env)" \
        || fail I-01 "RC=${rc}: $(sed 's/\x1b\[[0-9;]*m//g' "${EV}/bootstrap.log" | tail -n 4 | tr '\n' ' ')"
    grep -q "${URL}" "${EV}/bootstrap.log" && pass I-02 "publica la URL documentada (${URL})" || fail I-02 "no publica la URL documentada"
    ! grep -qiE 'edita .*\.env|pon una contraseña' "${EV}/bootstrap.log" && pass I-03 "sin petición de editar el .env ni de poner una contraseña" \
        || fail I-03 "el instalador pidió un paso manual sobre el .env"
    local cacheadas
    cacheadas=$(grep -c 'CACHED' "${EV}/bootstrap.log" || true)
    if [[ "${cacheadas}" -gt 0 ]]; then
        nr I-04 "CONSTRUCCIÓN EN FRÍO: la imagen se construyó con ${cacheadas} pasos en caché (capas precargadas en la preparación): NO acredita una construcción desde cero"
    else
        pass I-04 "la imagen se construyó sin pasos en caché"
    fi
    [[ -f "${ENVF}" ]] && pass I-05 "el instalador creó ${ENVF}" || fail I-05 "no hay .env"
    sed 's/\x1b\[[0-9;]*m//g' "${EV}/bootstrap.log" > "${EV}/bootstrap.limpio.log"
    return 0
}

# ── 2. salud del stack real ───────────────────────────────────────────────────────────────────────────────────────
estado_contenedor() {  # estado_contenedor SERVICIO → "estado salud reinicios oom exit"
    local id
    id=$(docker ps -aq --filter "label=com.docker.compose.service=$1" | head -n 1)
    [[ -n "${id}" ]] || { echo "inexistente"; return; }
    docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.RestartCount}} {{.State.OOMKilled}} {{.State.ExitCode}}' "${id}"
}
cgroup_de() {  # cgroup_de SERVICIO → ruta del cgroup v2 del contenedor
    local id
    id=$(docker ps -aq --filter "label=com.docker.compose.service=$1" | head -n 1)
    [[ -n "${id}" ]] && echo "/sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' "${id}").scope"
}
seccion_salud() {
    sec "SALUD: interfaz, base de datos, esquema, contenedores, memoria"
    "${COMPOSE[@]}" ps -a --format '{{.Service}} {{.State}} {{.Status}}' > "${EV}/compose-ps.txt" 2>&1
    api -o "${EV}/health.json" -w '%{http_code}' "${URL}/api/health" > "${EV}/health.http" 2>/dev/null
    [[ "$(cat "${EV}/health.http")" == "200" ]] && pass S-01 "/api/health responde 200" || fail S-01 "/api/health no responde 200"
    api -o /dev/null -w '%{http_code}' "${URL}/estado" 2>/dev/null | grep -q '^200$' && pass S-02 "/estado responde 200" || fail S-02 "/estado no responde 200"
    local css
    css=$(api "${URL}/static/web.css" 2>/dev/null | sha256sum | cut -d' ' -f1)
    [[ "${css}" == "${CSS_SHA256:-x}" ]] && pass S-03 "el CSS servido es el del candidato (SHA-256 ${css:0:16}…)" || fail S-03 "el CSS servido no coincide con el manifiesto"
    python3 - "${EV}/health.json" <<'EOF' >/dev/null 2>&1 && pass S-04 "base de datos conectada (checks.database = ok); el estado global 'degraded' por Transmission/aMule/VPN ausentes es del entorno" || fail S-04 "checks.database no es ok"
import json, sys
sys.exit(0 if json.load(open(sys.argv[1]))["checks"]["database"] == "ok" else 1)
EOF
    local v esperada
    v=$(docker exec zascarr-db psql -U comics_admin -d zascarr -tAc 'select version_num from alembic_version' 2>/dev/null | tr -d '[:space:]')
    esperada=$(docker exec zascarr-orquestador alembic heads 2>/dev/null | awk '{print $1}' | head -n 1)
    [[ -n "${v}" && "${v}" == "${esperada}" && "${v}" == "${ALEMBIC_ESPERADA:-?}" ]] \
        && pass S-05 "esquema = cabeza de Alembic del candidato (${v})" || fail S-05 "esquema ${v:-?} · cabeza en el contenedor ${esperada:-?} · esperada ${ALEMBIC_ESPERADA:-?}"
    local e
    e=$(estado_contenedor zascarr); echo "zascarr: ${e}" >> "${EV}/contenedores.txt"
    [[ "${e%% *}" == "running" && "${e}" == *" healthy "* ]] && pass S-06 "aplicación sana (${e})" || fail S-06 "aplicación: ${e}"
    e=$(estado_contenedor postgres); echo "postgres: ${e}" >> "${EV}/contenedores.txt"
    [[ "${e%% *}" == "running" && "${e}" == *" healthy "* ]] && pass S-07 "PostgreSQL sano (${e})" || fail S-07 "PostgreSQL: ${e}"
    e=$(estado_contenedor credenciales); echo "credenciales: ${e}" >> "${EV}/contenedores.txt"
    [[ "${e%% *}" == "exited" && "${e##* }" == "0" ]] \
        && pass S-08 "el servicio de un solo uso 'credenciales' terminó con código 0 (salida esperada, no un servicio caído)" || fail S-08 "credenciales: ${e}"
    local nom lim cg
    for nom in zascarr postgres; do
        cg=$(cgroup_de "${nom}")
        lim=$(cat "${cg}/memory.max" 2>/dev/null)
        [[ "${lim}" == "536870912" ]] && pass "S-09-${nom}" "límite de memoria efectivo de 512 M en el cgroup de ${nom} (memory.max=${lim})" \
            || fail "S-09-${nom}" "memory.max de ${nom} = ${lim:-?} (se esperaba 536870912): el límite NO se aplica"
    done
    # Observación: una muestra por minuto.
    local i malo=0
    : > "${EV}/observacion.txt"
    for ((i = 1; i <= MUESTRAS; i++)); do
        {
            echo "muestra ${i} $(date -Is)"
            docker stats --no-stream --format '{{.Name}} mem={{.MemUsage}} cpu={{.CPUPerc}}'
            for nom in zascarr postgres; do
                cg=$(cgroup_de "${nom}")
                echo "${nom} $(estado_contenedor "${nom}") oom_kill=$(awk '$1=="oom_kill"{print $2}' "${cg}/memory.events" 2>/dev/null)"
            done
        } >> "${EV}/observacion.txt"
        for nom in zascarr postgres; do
            e=$(estado_contenedor "${nom}"); set -- ${e}
            [[ "${3:-9}" == "0" && "${4:-x}" == "false" ]] || malo=1
        done
        ((i < MUESTRAS)) && sleep 60
    done
    [[ ${malo} -eq 0 ]] && pass S-10 "${MUESTRAS} muestras (≈$((MUESTRAS - 1)) min): 0 reinicios, 0 OOM en aplicación y PostgreSQL" || fail S-10 "reinicios u OOM durante la observación"
    [[ "$(dmesg 2>/dev/null | grep -ci 'out of memory\|oom-kill')" == "0" ]] && pass S-11 "sin OOM en dmesg" || fail S-11 "OOM en dmesg"
    ss -ltn | awk 'NR>1{print $4}' > "${EV}/puertos.txt"
    if grep -E ':(8000|5432)$' "${EV}/puertos.txt" | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then fail S-12 "8000/5432 escuchan fuera del bucle local"
    else pass S-12 "8000 y 5432 solo escuchan en el bucle local"; fi
}

# ── 3. protección y conservación de credenciales ──────────────────────────────────────────────────────────────────
seccion_credenciales() {
    sec "CREDENCIALES: propietario, modo, identidades no administrativas, controles positivos, código protegido"
    [[ "$(modo "${ENVF}")" == "600 root:root" ]] && pass C-01 ".env = 600 root:root" || fail C-01 ".env = $(modo "${ENVF}")"
    [[ "$(modo "${RAIZ}")" == "755 root:root" ]] && pass C-02 "la carpeta del .env (${RAIZ}) = 755 root:root" || fail C-02 "${RAIZ} = $(modo "${RAIZ}")"
    [[ "$(stat -c %U "${REPO}")" == "root" ]] && pass C-03 "el repositorio es de root" || fail C-03 "el repositorio es de $(stat -c %U "${REPO}")"
    local abiertos
    abiertos=$(find "${REPO}" ! -type l -perm /022 2>/dev/null | wc -l)
    [[ "${abiertos}" == "0" ]] && pass C-04 "ningún fichero ni carpeta del repositorio admite escritura de grupo u otros" || fail C-04 "${abiertos} entradas del repo admiten escritura de grupo u otros"
    # `stat` sin -L NO sigue el enlace: da el propietario del propio enlace (`-h` no existe en stat).
    [[ "$(readlink "${REPO}/.env")" == "${ENVF}" && "$(stat -c %U "${REPO}/.env")" == "root" ]] \
        && pass C-05 "el enlace del repo apunta al .env y es de root" || fail C-05 "enlace .env del repo: $(readlink "${REPO}/.env") ($(stat -c %U "${REPO}/.env"))"
    local longitud
    longitud=$(valor_env | wc -c)
    [[ "${longitud}" -ge 33 ]] && pass C-06 "DB_PASSWORD generada (${longitud} caracteres, no se muestra)" || fail C-06 "DB_PASSWORD ausente o corta (${longitud})"
    ! grep -qE 'DB_PASSWORD:-[^}]' "${REPO}/docker-compose.yml" 2>/dev/null \
        && pass C-07 "el docker-compose.yml instalado no tiene ningún valor por defecto para DB_PASSWORD (la lista del servicio 'credenciales' es de RECHAZO)" \
        || fail C-07 "el compose conserva un valor por defecto para DB_PASSWORD"

    seccion_identidades || return $?
    # Tras todos los intentos (todos denegados) el .env y su enlace siguen intactos.
    [[ "$(modo "${ENVF}")" == "600 root:root" && "$(readlink -f "${REPO}/.env")" == "${ENVF}" ]] \
        && pass C-30 "tras los intentos, el .env sigue 600 root:root y el enlace sigue apuntando a él" || fail C-30 "el .env o su enlace cambió"
    # Ninguna credencial en lo que se ha capturado ni en los registros de los contenedores.
    local P fugas=0 f
    P=$(valor_env)
    for f in "${EV}"/*.log "${EV}"/*.txt "${EV}"/*.json; do
        [[ -f "${f}" ]] && grep -qF -- "${P}" "${f}" && { fugas=$((fugas + 1)); echo "fuga en ${f}" >> "${EV}/fugas.txt"; }
    done
    for f in zascarr postgres; do docker logs "$(docker ps -aq --filter "label=com.docker.compose.service=${f}" | head -n 1)" 2>&1 | grep -qF -- "${P}" && fugas=$((fugas + 1)); done
    [[ ${fugas} -eq 0 ]] && pass C-31 "la credencial no aparece en la salida del instalador, en la evidencia ni en los registros de los contenedores" || fail C-31 "la credencial aparece en ${fugas} sitio(s)"
    nr C-32 "LÍMITE conocido (ADR 0012): quien esté en el grupo docker (o sea root) puede leer las variables de un contenedor con 'docker inspect'; no se intenta impedir ni se mide aquí"
}

# Intentos de lectura, modificación, sustitución y redirección desde identidades NO administrativas, con controles
# positivos. Se puede ejecutar sola (la usa la prueba del propio guion: tests/escenarios/guion_f1bis.sh).
seccion_identidades() {
    # Controles positivos: sin esto, «denegado» podría ser solo que no se puede entrar en el directorio.
    local u
    for u in "${SVC}" "${OTRO}"; do
        afirmar "C-10-${u}" "control positivo: ${u} atraviesa ${RAIZ} y lee el código público del repo" como "${u}" cat "${REPO}/docker-compose.yml"
    done
    afirmar C-11 "control positivo: root lee el .env" bash -c "grep -q '^DB_PASSWORD=' '${ENVF}'"
    afirmar C-12 "control positivo: ${OTRO} puede crear ficheros donde le corresponde (/tmp)" como "${OTRO}" bash -c 'f=$(mktemp) && rm -f "$f"'
    # Si un control positivo falla, «denegado» no demuestra nada (podría ser solo que no se puede entrar en el directorio): no se
    # interpretan las denegaciones como protección acreditada. Problema del ARNÉS o del ENTORNO, no del producto.
    if grep -q '^FAIL C-1[0-2]' "${RES}"; then
        nr C-13 "controles positivos fallidos: los intentos de acceso NO se ejecutan ni se interpretan (problema del arnés o del entorno)"
        return 2
    fi

    local decoy_dir="/tmp/ensayo-ajeno-$$"
    mkdir -p "${decoy_dir}"; chmod 777 "${decoy_dir}"
    for u in "${SVC}" "${OTRO}"; do
        local p="C-20-${u}"
        negar "${p}-leer" "${u} NO puede abrir el .env" como "${u}" bash -c "exec 3< '${ENVF}'"
        negar "${p}-leer-enlace" "${u} NO puede abrirlo a través del enlace del repo" como "${u}" bash -c "exec 3< '${REPO}/.env'"
        negar "${p}-anadir" "${u} NO puede añadir líneas al .env" como "${u}" bash -c "echo X=1 >> '${ENVF}'"
        negar "${p}-truncar" "${u} NO puede truncarlo" como "${u}" bash -c ": > '${ENVF}'"
        negar "${p}-borrar" "${u} NO puede eliminarlo" como "${u}" rm -f "${ENVF}"
        negar "${p}-mover" "${u} NO puede moverlo" como "${u}" mv "${ENVF}" "${decoy_dir}/robado.env"
        como "${u}" bash -c "echo 'falso' > '${decoy_dir}/${u}.falso.env'" 2>/dev/null
        negar "${p}-sustituir" "${u} NO puede sustituirlo por un fichero suyo" como "${u}" mv -f "${decoy_dir}/${u}.falso.env" "${ENVF}"
        negar "${p}-junto" "${u} NO puede crear ficheros junto a él (temporales, copias)" como "${u}" touch "${RAIZ}/.env.copia"
        negar "${p}-redirigir" "${u} NO puede redirigir el enlace del repo (borrar y recrear)" \
            como "${u}" bash -c "rm -f '${REPO}/.env' && ln -s '${decoy_dir}/${u}.falso.env' '${REPO}/.env'"
        negar "${p}-redirigir2" "${u} NO puede sustituirlo por otro enlace" como "${u}" ln -sfn "${decoy_dir}/${u}.falso.env" "${REPO}/.env"
        # Código que root ejecuta
        negar "${p}-compose" "${u} NO puede modificar el docker-compose.yml que root ejecutará" como "${u}" bash -c "echo '# x' >> '${REPO}/docker-compose.yml'"
        negar "${p}-dockerfile" "${u} NO puede modificar el Dockerfile con el que root construye la imagen" como "${u}" bash -c "echo '# x' >> '${REPO}/Dockerfile'"
        negar "${p}-scripts" "${u} NO puede modificar los scripts de operación" como "${u}" bash -c "echo '# x' >> '${REPO}/scripts/update.sh'"
        negar "${p}-bootstrap" "${u} NO puede modificar bootstrap.sh" como "${u}" bash -c "echo '# x' >> '${REPO}/bootstrap.sh'"
    done
    rm -rf "${decoy_dir}"
    return 0
}

# ── 4. reejecución del instalador ─────────────────────────────────────────────────────────────────────────────────
seccion_reejecucion() {
    sec "REEJECUCIÓN: mismas respuestas, la contraseña se conserva (no es una prueba de actualización desde otra versión)"
    local h0 m0 rc
    h0=$(sha256sum "${ENVF}" | cut -d' ' -f1); m0=$(modo "${ENVF}")
    bash /home/ensayo/bootstrap.sh < /dev/null > "${EV}/bootstrap-reejecucion.log" 2>&1
    rc=$?
    sed -i 's/\x1b\[[0-9;]*m//g' "${EV}/bootstrap-reejecucion.log"
    [[ ${rc} -eq 0 ]] && pass R-01 "la reejecución termina con RC=0" || fail R-01 "reejecución RC=${rc}: $(tail -n 3 "${EV}/bootstrap-reejecucion.log" | tr '\n' ' ')"
    [[ "$(sha256sum "${ENVF}" | cut -d' ' -f1)" == "${h0}" ]] && pass R-02 "el .env es byte a byte el mismo: la contraseña se conserva" || fail R-02 "el .env cambió tras reejecutar"
    [[ "$(modo "${ENVF}")" == "${m0}" ]] && pass R-03 "propietario y modo intactos (${m0})" || fail R-03 "modo/propietario cambiaron: ${m0} → $(modo "${ENVF}")"
    api -o "${EV}/health-reejecucion.json" "${URL}/api/health" >/dev/null 2>&1
    python3 - "${EV}/health-reejecucion.json" <<'EOF' >/dev/null 2>&1 && pass R-04 "tras reejecutar, la aplicación sigue conectada a la base con la misma contraseña (checks.database = ok)" || fail R-04 "la aplicación no conecta con la base tras reejecutar"
import json, sys
sys.exit(0 if json.load(open(sys.argv[1]))["checks"]["database"] == "ok" else 1)
EOF
    ! grep -qiE 'He generado una contraseña' "${EV}/bootstrap-reejecucion.log" && pass R-05 "no vuelve a generar una contraseña" || fail R-05 "generó otra contraseña"
    nr R-06 "la reejecución no es una actualización desde otra versión (M4-03/04, fuera de esta fase)"
}

# ── 5. originales sintéticos ──────────────────────────────────────────────────────────────────────────────────────
seccion_originales() {
    sec "ORIGINALES: rutas, nombres, tamaños y contenido de la biblioteca sintética antes y después"
    inventario "${EV}/biblioteca-despues.tsv"
    if diff -q "${EV}/biblioteca-antes.tsv" "${EV}/biblioteca-despues.tsv" >/dev/null; then
        pass O-01 "los $(wc -l < "${EV}/biblioteca-antes.tsv") originales sintéticos conservan ruta, nombre, tamaño y SHA-256"
    else
        fail O-01 "la biblioteca cambió: $(diff "${EV}/biblioteca-antes.tsv" "${EV}/biblioteca-despues.tsv" | head -n 4 | tr '\n' ';')"
    fi
    find "${BIBLIOTECA}" -type d | sort > "${EV}/directorios-despues.txt"
    comm -13 "${EV}/directorios-antes.txt" "${EV}/directorios-despues.txt" > "${EV}/directorios-nuevos.txt"
    pass O-02 "OBSERVACIÓN: el instalador creó $(wc -l < "${EV}/directorios-nuevos.txt") carpetas vacías (estructura documentada); no borró ni movió ningún original"
    [[ -z "$(comm -23 "${EV}/directorios-antes.txt" "${EV}/directorios-despues.txt")" ]] && pass O-03 "no desapareció ninguna carpeta" || fail O-03 "desapareció alguna carpeta"
}

# Valor efectivo, dentro del contenedor, de los flags de las integraciones de descarga y el foro. `-i` mantiene abierta la entrada
# estándar: sin ella `docker exec` no entrega el programa del heredoc y no ejecuta nada.
integraciones_efectivas() {
    docker exec -i zascarr-orquestador python - <<'PY'
from zascarr.config import get_settings
s = get_settings()
for n in ("prowlarr_enabled", "transmission_enabled", "amule_enabled", "forum_enabled"):
    print(f"{n}={getattr(s, n)}")
PY
}

# ── 6. fuentes ────────────────────────────────────────────────────────────────────────────────────────────────────
# Las fuentes se apagan INMEDIATAMENTE tras la instalación (no al final): la ventana con los defaults es la mínima posible y se
# MIDE. Primero el estado tal como se instala; después, por Ajustes (override de runtime guardado en la BD), la vía soportada
# que SÍ llega a la aplicación; la persistencia se comprueba más tarde (`seccion_fuentes_persistencia`).
estado_fuentes() {  # → JSON de /api/health → fuentes
    api "${URL}/api/health" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["fuentes"]))'
}
todas_desactivadas() { [[ "$(grep -o 'disabled' <<<"$1" | wc -l)" == "4" && "$(grep -o '"enabled"' <<<"$1" | wc -l)" == "0" ]]; }

seccion_fuentes_iniciales() {
    sec "FUENTES (1/2): estado tal como se instala y apagado inmediato por Ajustes"
    local i
    for i in $(seq 1 30); do [[ "$(api -o /dev/null -w '%{http_code}' "${URL}/api/health" 2>/dev/null)" == "200" ]] && break; sleep 2; done
    # (1) ¿Qué variables *_ENABLED recibe el contenedor? (solo nombres)
    docker exec zascarr-orquestador env | cut -d= -f1 | grep -E '_ENABLED$' | sort > "${EV}/env-enabled-nombres.txt"
    [[ "$(cat "${EV}/env-enabled-nombres.txt")" == "FORUM_ENABLED" ]] \
        && pass F-01 "DOCUMENTADO: Compose solo transmite FORUM_ENABLED; los cuatro flags de fuentes de metadatos escritos en el .env NO llegan al contenedor (inertes)" \
        || fail F-01 "el contenedor recibe: $(tr '\n' ' ' < "${EV}/env-enabled-nombres.txt")"
    # (2) Estado inicial: lo primero que se registra tras la primera respuesta utilizable.
    local inst t_inicio t_apagado
    inst="$(estado_fuentes)"; echo "${inst}" > "${EV}/fuentes-instalado.json"
    nr F-02 "TAL COMO SE INSTALA (hallazgo vigente #239, sin cambiar defaults): ${inst}"
    # (3) Apagado inmediato por Ajustes (Origin local obligatorio: sin él, 403).
    local http
    http=$(api -o /dev/null -w '%{http_code}' -X POST "${URL}/ui/ajustes/guardar/fuentes" -H "Origin: ${URL}" \
        --data-urlencode "comicvine_enabled=false" --data-urlencode "anilist_enabled=false" \
        --data-urlencode "tebeosfera_enabled=false" --data-urlencode "gcd_enabled=false")
    date +%s > "${EV}/fuentes-apagadas-epoch.txt"
    [[ "${http}" == "200" ]] && pass F-04 "POST /ui/ajustes/guardar/fuentes (Origin local) → 200" || fail F-04 "POST de Ajustes → ${http}"
    local conf; conf="$(estado_fuentes)"; echo "${conf}" > "${EV}/fuentes-configuradas.json"
    todas_desactivadas "${conf}" && pass F-05 "configuración efectiva: las cuatro fuentes de metadatos 'disabled' en /api/health" || fail F-05 "${conf}"
    # Ventana con los defaults: desde que arrancó la aplicación hasta que se apagaron.
    t_inicio=$(date -d "$(docker inspect -f '{{.State.StartedAt}}' zascarr-orquestador)" +%s 2>/dev/null || echo 0)
    t_apagado=$(cat "${EV}/fuentes-apagadas-epoch.txt")
    if [[ ${t_inicio} -gt 0 ]]; then
        echo "ventana_con_defaults_segundos=$((t_apagado - t_inicio))" | tee "${EV}/ventana-fuentes.txt" >/dev/null
        nr F-11 "VENTANA MEDIDA con las fuentes por defecto (aplicación arrancada → apagadas): $((t_apagado - t_inicio)) s, red cerrada, sin aceptación legal; el instalador no ofrece un gancho entre las migraciones y el arranque (decisión de #239)"
    else nr F-11 "no se pudo medir la ventana con los defaults"; fi
    # Solo los cuatro flags (no se vuelca la configuración de runtime).
    docker exec zascarr-db psql -U comics_admin -d zascarr -tAc \
        "select concat_ws(',', \"values\"->>'comicvine_enabled', \"values\"->>'anilist_enabled', \"values\"->>'tebeosfera_enabled', \"values\"->>'gcd_enabled') from runtime_settings" \
        > "${EV}/runtime-cuatro-flags.txt" 2>&1
    [[ "$(tr -d '[:space:]' < "${EV}/runtime-cuatro-flags.txt")" == "false,false,false,false" ]] \
        && pass F-06 "guardado en la base de datos (runtime_settings): los cuatro flags a false (solo se exportan esos cuatro)" || fail F-06 "runtime_settings: $(head -c 120 "${EV}/runtime-cuatro-flags.txt" | tr '\n' ' ')"
    # (4) Integraciones de descarga y foro: valor efectivo dentro del contenedor.
    integraciones_efectivas > "${EV}/integraciones-descarga.txt" 2>&1
    if [[ "$(grep -c '=False$' "${EV}/integraciones-descarga.txt")" == "4" ]]; then pass F-03 "las integraciones de descarga y el foro están apagadas (valor efectivo dentro del contenedor)"
    else fail F-03 "integraciones de descarga: $(tr '\n' ' ' < "${EV}/integraciones-descarga.txt")"; fi
    todas_desactivadas "${conf}"   # código de salida: si no quedaron apagadas, el resto del ensayo no tiene sentido con ese supuesto
}

seccion_fuentes_persistencia() {
    sec "FUENTES (2/2): persistencia, reinicio deliberado y registros"
    local fin_reejecucion
    todas_desactivadas "$(estado_fuentes)" && pass F-07a "tras la reejecución del instalador (que recrea la aplicación) las cuatro siguen 'disabled'" \
        || fail F-07a "tras la reejecución: $(estado_fuentes)"
    # Reinicio DELIBERADO (identificado como tal; no cuenta como «reinicio inesperado» de la observación de salud).
    echo "REINICIO DELIBERADO de la aplicación para comprobar la persistencia: $(date -Is)" | tee -a "${EV}/reinicios-deliberados.txt" >/dev/null
    "${COMPOSE[@]}" restart zascarr >"${EV}/restart.log" 2>&1
    local i
    for i in $(seq 1 30); do [[ "$(api -o /dev/null -w '%{http_code}' "${URL}/api/health" 2>/dev/null)" == "200" ]] && break; sleep 2; done
    local tras; tras="$(estado_fuentes)"; echo "${tras}" > "${EV}/fuentes-tras-reinicio.json"
    todas_desactivadas "${tras}" && pass F-07 "las fuentes siguen 'disabled' tras el reinicio deliberado (la configuración persiste)" || fail F-07 "tras reiniciar: ${tras}"
    # Registros de la aplicación de TODA la fase. Un grep acredita «no observado en esos registros», no la ausencia universal.
    local app intentos
    app=$(docker ps -aq --filter "label=com.docker.compose.service=zascarr" | head -n 1)
    docker logs "${app}" > "${EV}/zascarr.log" 2>&1
    intentos=$(grep -ciE 'ConnectError|getaddrinfo|Temporary failure in name resolution|Name or service not known|tebeosfera|comicvine|anilist|gcd\.|ConnectTimeout' "${EV}/zascarr.log" || true)
    [[ "${intentos}" == "0" ]] && pass F-08 "NO OBSERVADOS intentos de conexión externa ni referencias a fuentes en los registros de la aplicación (acredita ausencia en esos registros, no en general)" \
        || fail F-08 "${intentos} líneas con intentos de conexión externa o referencias a fuentes (ver zascarr.log)"
    grep -q 'skipped_no_legal_acknowledgment' "${EV}/zascarr.log" && pass F-09 "el orquestador omite sus ciclos por falta de aceptación legal (barrera adicional, NO sustituye apagar las fuentes)" \
        || nr F-09 "no se observó el aviso de ciclos omitidos"
    # La red cerrada es una salvaguarda adicional: solo cuenta si A-10 se comprobó.
    if grep -q '^PASS A-10' "${RES}"; then pass F-10 "red cerrada comprobada al empezar (A-10): barrera adicional, NO sustituye apagar las fuentes"
    else fail F-10 "A-10 no es PASS: no se puede afirmar que la red estuviera cerrada"; fi
}

# ── 7. cierre ─────────────────────────────────────────────────────────────────────────────────────────────────────
seccion_cierre() {
    sec "CIERRE"
    date -Is > "${EV}/99-fin.txt"
    cat /sys/class/net/enp0s1/statistics/rx_bytes > "${EV}/rx-fin.txt" 2>/dev/null || true
    docker ps -a --format '{{.Names}} {{.Status}}' > "${EV}/contenedores-final.txt"
    df -h / | tail -n 1 > "${EV}/disco-final.txt"
    local p f n
    p=$(grep -c '^PASS' "${RES}"); f=$(grep -c '^FAIL' "${RES}"); n=$(grep -c '^NOT_RUN' "${RES}")
    echo "RESUMEN: PASS=${p} FAIL=${f} NOT_RUN=${n}" | tee -a "${RES}"
    [[ ${f} -eq 0 ]]
}

principal() {
    local SECCIONES=("$@") s rc=0
    [[ ${#SECCIONES[@]} -gt 0 ]] || SECCIONES=(antes instalacion fuentes_iniciales salud credenciales reejecucion originales fuentes_persistencia cierre)
    for s in "${SECCIONES[@]}"; do
        "seccion_${s}"; local r=$?
        [[ ${r} -eq 0 ]] || rc=1
        # Una PRECONDICIÓN fallida (red, candidato, limpieza del entorno, identidad de prueba) impide instalar: es un problema
        # del arnés o del entorno, no del producto, y medir sobre un punto de partida que no es el declarado no vale.
        if [[ "${s}" == "antes" && ${r} -ne 0 ]]; then
            nr X-00 "PRECONDICIÓN FALLIDA (problema del arnés o del entorno, NO del producto): la instalación NO se inicia"
            seccion_cierre || true
            return 2
        fi
        # Si la instalación no terminó, el resto mediría un sistema que no existe: se registra y se pasa al cierre.
        if [[ "${s}" == "instalacion" ]] && grep -q '^FAIL I-0[015]' "${RES}"; then
            nr X-01 "la instalación falló: fuentes, salud, credenciales y reejecución NO se ejecutan (medirían un sistema inexistente)"
            seccion_originales || true      # los originales sí se comparan: un instalador que falla tampoco debe haberlos tocado
            seccion_cierre || true
            return 1
        fi
        if [[ "${s}" == "fuentes_iniciales" && ${r} -ne 0 ]]; then
            nr X-02 "las fuentes no quedaron apagadas: el resto del ensayo NO continúa con fuentes activas"
            seccion_cierre || true
            return 1
        fi
        if [[ "${s}" == "credenciales" && ${r} -eq 2 ]]; then
            nr X-03 "controles positivos fallidos (arnés/entorno): se detiene antes de interpretar ninguna denegación"
            seccion_cierre || true
            return 2
        fi
    done
    return "${rc}"
}
# Solo si se ejecuta (no si se carga con `source`, como hace la prueba del guion).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    principal "$@"
    exit $?
fi
