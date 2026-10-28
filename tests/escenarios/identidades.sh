#!/usr/bin/env bash
# Escenario «identidades» de las pruebas de credenciales: una instalación HEREDADA (todo del usuario de servicio,
# `.env` legible por todos) se pasa por el bootstrap.sh REAL y se intenta leer / escribir / reemplazar el `.env`
# desde cada identidad. El resultado se mide INTENTÁNDOLO, no leyendo el script.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo
poner_docker_de_pega

SINT="Sint3tica-Identidades-0002-$$"
RAIZ="${W}/opt/zascarr"
instalacion_heredada "${RAIZ}" "${SINT}"
echo "# stub" > "${RAIZ}/zascarr/Dockerfile"; chown "${SVC}:${SVC}" "${RAIZ}/zascarr/Dockerfile"
# Un enlace «hostil» dentro del repo apuntando a un fichero de OTRO usuario: un `chown -R` sin cuidado lo seguiría.
echo "ajeno" > "${W}/ajeno.txt"; chown "${OTRO}:${OTRO}" "${W}/ajeno.txt"
ln -s "${W}/ajeno.txt" "${RAIZ}/zascarr/enlace-hostil"; chown -h "${SVC}:${SVC}" "${RAIZ}/zascarr/enlace-hostil"
ANTES_AJENO="$(stat -c '%U' "${W}/ajeno.txt")"

ejecutar_instalador "${RAIZ}"
ENV="${RAIZ}/.env"
H0="$(huella "${ENV}")"

# Cada intento de escritura es independiente de los anteriores: si uno TUVIERA éxito (un fallo del producto), se
# repone el estado para que los demás intentos midan lo suyo y no un efecto en cascada.
GUARDA="${W}/guarda"; mkdir -p "${GUARDA}"
ARCHIVOS_VIGILADOS=("${ENV}" "${RAIZ}/zascarr/docker-compose.yml" "${RAIZ}/zascarr/Dockerfile" "${RAIZ}/zascarr/scripts/update.sh")
for a in "${ARCHIVOS_VIGILADOS[@]}"; do
    cp -p "${a}" "${GUARDA}/$(echo "${a}" | tr / _)"; stat -c '%a %u %g' "${a}" > "${GUARDA}/$(echo "${a}" | tr / _).meta"
done
reponer() {
    local a g m u gr
    rm -f "${RAIZ}/.env.copia" "${RAIZ}/viejo"
    for a in "${ARCHIVOS_VIGILADOS[@]}"; do
        g="${GUARDA}/$(echo "${a}" | tr / _)"
        if [[ ! -f "${a}" || -L "${a}" || "$(huella "${a}")" != "$(huella "${g}")" ]]; then
            rm -f "${a}"; cp -p "${g}" "${a}"
            read -r m u gr < "${g}.meta"; chown "${u}:${gr}" "${a}"; chmod "${m}" "${a}"
        fi
    done
    [[ "$(readlink "${RAIZ}/zascarr/.env" 2>/dev/null)" == "${ENV}" ]] || { rm -f "${RAIZ}/zascarr/.env"; ln -s "${ENV}" "${RAIZ}/zascarr/.env"; }
}
intentar() { negar "$@"; reponer; }

# Control positivo: sin esto, «denegado» podría ser solo que no se puede atravesar el directorio.
afirmar P00 "control: el código del repo es legible por cualquier usuario (los directorios se atraviesan)" \
    como "${OTRO}" cat "${RAIZ}/zascarr/docker-compose.yml"
afirmar P00b "control: el instalador llegó a PostgreSQL con la instalación heredada" llego_a_postgres

# Confidencialidad
negar P01 "un usuario local no autorizado NO puede leer el .env" como "${OTRO}" cat "${ENV}"
negar P02 "el usuario de servicio NO puede leer el .env" como "${SVC}" cat "${ENV}"
negar P02b "ni a través del enlace del repo" como "${OTRO}" cat "${RAIZ}/zascarr/.env"

# Integridad: editar, truncar, eliminar, mover, reemplazar, redirigir
intentar P03 "el usuario de servicio no puede añadir líneas al .env" como "${SVC}" bash -c "echo X=1 >> '${ENV}'"
intentar P03b "ni truncarlo" como "${SVC}" bash -c ": > '${ENV}'"
intentar P04 "ni eliminarlo" como "${SVC}" rm -f "${ENV}"
intentar P04b "ni moverlo" como "${SVC}" mv "${ENV}" "${RAIZ}/viejo"
# El fichero que el usuario de servicio intentará poner en su lugar vive en una carpeta SUYA (para mover un fichero
# también hace falta poder escribir en su carpeta de origen: si no, el intento fallaría por otra razón).
mkdir -p "${W}/casa-svc"; chown "${SVC}:${SVC}" "${W}/casa-svc"
echo "falso" > "${W}/casa-svc/falso.env"; chown "${SVC}:${SVC}" "${W}/casa-svc/falso.env"
intentar P05 "ni reemplazarlo por otro fichero suyo" como "${SVC}" mv -f "${W}/casa-svc/falso.env" "${ENV}"
intentar P05b "ni crear ficheros junto a él (temporales, copias)" como "${SVC}" touch "${RAIZ}/.env.copia"
intentar P06 "ni redirigir el enlace efectivo del repo (borrar y recrear)" como "${SVC}" bash -c "rm -f '${RAIZ}/zascarr/.env' && ln -s '${W}/casa-svc/falso.env' '${RAIZ}/zascarr/.env'"
intentar P06b "ni sustituirlo por otro enlace" como "${SVC}" bash -c "ln -sfn '${W}/casa-svc/falso.env' '${RAIZ}/zascarr/.env'"
intentar P07 "el usuario de servicio no puede modificar el docker-compose.yml que root ejecutará" \
    como "${SVC}" bash -c "echo '# x' >> '${RAIZ}/zascarr/docker-compose.yml'"
intentar P07b "ni el Dockerfile con el que root construye la imagen" como "${SVC}" bash -c "echo '# x' >> '${RAIZ}/zascarr/Dockerfile'"
intentar P07c "ni los scripts de operación" como "${SVC}" bash -c "echo '# x' >> '${RAIZ}/zascarr/scripts/update.sh'"
if [[ "$(huella "${ENV}")" == "${H0}" ]] && [[ "$(readlink -f "${RAIZ}/zascarr/.env")" == "$(readlink -f "${ENV}")" ]]; then
    pass P08 "tras todos los intentos, el .env sigue intacto y el enlace sigue apuntando a él"
else fail P08 "el .env o su enlace cambió"; fi

# Modo y propietario resultantes
if [[ "$(modo "${ENV}")" == "600 root:root" ]]; then pass P09 "el .env es 600 root:root"; else fail P09 "el .env es $(modo "${ENV}")"; fi
if [[ "$(modo "${RAIZ}")" == "755 root:root" ]]; then pass P09b "la carpeta que lo contiene es 755 root:root"; else fail P09b "la carpeta es $(modo "${RAIZ}")"; fi
if [[ "$(stat -c %U "${RAIZ}/zascarr")" == "root" ]]; then pass P09c "el repo es de root"; else fail P09c "el repo es de $(stat -c %U "${RAIZ}/zascarr")"; fi

# Un `chown -R` que siguiera enlaces habría robado el fichero de otro usuario
if [[ "$(stat -c '%U' "${W}/ajeno.txt")" == "${ANTES_AJENO}" && "$(stat -c '%U' "${RAIZ}/zascarr/enlace-hostil")" == "root" ]]; then
    pass P10 "un enlace hostil dentro del repo no cambia el dueño del fichero ajeno al que apunta, y el enlace mismo pasa a root"
else fail P10 "dueño del fichero ajeno: $(stat -c '%U' "${W}/ajeno.txt"); del enlace: $(stat -c '%U' "${RAIZ}/zascarr/enlace-hostil")"; fi

# Root (administrador) sigue pudiendo operar
afirmar P11 "root lee el .env y a través del enlace" bash -c "grep -q '^DB_PASSWORD=' '${ENV}' && grep -q '^DB_PASSWORD=' '${RAIZ}/zascarr/.env'"
afirmar P11b "root puede comprobar el estado con scripts/credenciales.sh" bash "${RAIZ}/zascarr/scripts/credenciales.sh" comprobar
if [[ -f "${RAIZ}/zascarr/scripts/credenciales.sh" ]]; then
    negar P11c "sin ser root, la herramienta se niega (sale con error) en vez de leer o escribir nada" \
        como "${SVC}" bash "${RAIZ}/zascarr/scripts/credenciales.sh" comprobar
else fail P11c "no existe scripts/credenciales.sh"; fi

# Consumidores de administración: backup.sh (el temporizador del backup diario lo ejecuta root) sigue funcionando con
# el .env 600; con la identidad de servicio falla limpio, sin dejar un volcado.
BACKUP="${W}/backups"; OFFSITE="${W}/backups-offsite"; STATUS="${W}/backup-status"
mkdir -p "${BACKUP}" "${OFFSITE}" "${STATUS}"; chmod 777 "${BACKUP}" "${OFFSITE}" "${STATUS}"
if env PATH="${W}/bin:${PATH}" STUB_LOG="${W}/docker.log" BACKUP_DIR="${BACKUP}" \
    BACKUP_OFFSITE_DIR="${OFFSITE}" BACKUP_OFFSITE_MOUNT="/" BACKUP_SKIP_DEVICE_CHECK=1 \
    BACKUP_STATUS_DIR="${STATUS}" BACKUP_LOCK_FILE="${W}/backup.lock" \
    bash "${RAIZ}/zascarr/scripts/backup.sh" >/dev/null 2>&1 \
   && ls "${BACKUP}"/backup_*.sql.gz >/dev/null 2>&1; then
    pass P15 "backup.sh (root) sigue funcionando con el .env en 600 root:root"
else fail P15 "backup.sh no funcionó como root"; fi
rm -f "${BACKUP}"/backup_*.sql.gz
if como "${SVC}" env PATH="${W}/bin:${PATH}" STUB_LOG="${W}/docker.log" BACKUP_DIR="${BACKUP}" bash "${RAIZ}/zascarr/scripts/backup.sh" >/dev/null 2>&1; then
    fail P15b "backup.sh funcionó con la identidad de servicio (leyó el .env)"
else pass P15b "con la identidad de servicio, backup.sh falla y no deja ningún volcado"; fi
ls "${BACKUP}"/backup_*.sql.gz >/dev/null 2>&1 && fail P15c "quedó un volcado" || pass P15c "sin volcado residual"

# Reconfiguración: volver a ejecutar el instalador mantiene propietario/modo y la credencial
: > "${W}/docker.log"
ejecutar_instalador "${RAIZ}"
if [[ "$(modo "${ENV}")" == "600 root:root" && "$(valor_de "${ENV}")" == "${SINT}" ]] && llego_a_postgres; then
    pass P12 "reejecutar el instalador mantiene 600 root:root y la credencial, y sigue funcionando"
else fail P12 "tras reejecutar: $(modo "${ENV}")"; fi
if ! grep -qF -- "${SINT}" "${W}/salida.out" "${W}/salida.err" "${W}/docker.log" 2>/dev/null; then
    pass P13 "la credencial sintética no aparece en la salida del instalador ni en las órdenes a Docker"
else fail P13 "la credencial aparece en la salida"; fi

# Una carpeta que NO es solo de ZascArr (como un home) no se reclama: no se cambia su dueño ni su modo, y el instalador
# SE DETIENE (antes avisaba y seguía: quien puede escribir en esa carpeta podría sustituir el .env). Más casos de
# ubicación en el escenario «ubicacion».
HOGAR="${W}/home/colecc"; mkdir -p "${HOGAR}/Documentos"; echo secreto-ajeno > "${HOGAR}/.bashrc"
instalacion_heredada "${HOGAR}" "${SINT}"
mkdir -p "${HOGAR}/Documentos"; chown -R "${SVC}:${SVC}" "${HOGAR}"; chmod 750 "${HOGAR}"
ANTES="$(modo "${HOGAR}")"
: > "${W}/docker.log"
ejecutar_instalador "${HOGAR}"
if [[ "$(modo "${HOGAR}")" == "${ANTES}" && "${RC}" -ne 0 ]] && ! llego_a_postgres; then
    pass P14 "una carpeta compartida (home) no se reclama y el instalador se detiene en vez de seguir"
else fail P14 "carpeta compartida: $(modo "${HOGAR}"), rc=${RC}"; fi
if grep -q 'no es solo de ZascArr' "${W}/salida.out" "${W}/salida.err"; then pass P14b "y explica que ahí el .env no quedaría a salvo de ser reemplazado"
else fail P14b "no lo explicó"; fi

rm -rf "${W}"
exit 0
