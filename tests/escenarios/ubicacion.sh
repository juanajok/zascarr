#!/usr/bin/env bash
# Escenario «ubicación» (C5, C8): si otra cuenta puede sustituir el `.env` (o un componente de su ruta, o el código
# que root ejecuta), el instalador SE DETIENE sin escribir ningún secreto y dice qué hacer. Antes avisaba y seguía.
# Se mide intentándolo: cada caso monta una instalación heredada en una ubicación distinta, ejecuta el instalador
# real y comprueba (1) que se detuvo, (2) que no llegó a PostgreSQL, (3) que no tocó nada (huella y modo del .env y de
# la carpeta) y (4) que el mensaje da una salida segura.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo
poner_docker_de_pega

SINT="Sint3tica-Ubicacion-0005-$$"

# parar ID "texto" RAIZ [RUTA_DEL_ENV]   (también comprueba que NO se reclamó la raíz ni el repo antes de parar)
parar() {
    local id="$1" texto="$2" raiz="$3" env="${4:-$3/.env}" h m mr mp
    h="$(huella "${env}")"; m="$(modo "${env}")"
    mr="$(modo "$(dirname "${env}")")"; mp="$(modo "$(dirname "${env}")/zascarr")"
    : > "${W}/docker.log"
    ejecutar_instalador "${raiz}"
    if [[ "${RC}" -ne 0 ]] && ! llego_a_postgres && [[ "$(huella "${env}")" == "${h}" && "$(modo "${env}")" == "${m}" ]] \
       && [[ "$(modo "$(dirname "${env}")")" == "${mr}" && "$(modo "$(dirname "${env}")/zascarr")" == "${mp}" ]]; then
        pass "${id}" "${texto}: se detiene sin escribir ni cambiar nada (ni reclamar la carpeta ni el repo)"
    else
        fail "${id}" "${texto}: rc=${RC}, Postgres=$(llego_a_postgres && echo si || echo no), .env ${m}→$(modo "${env}")"
    fi
    if grep -q '/opt/zascarr' "${W}/salida.err" "${W}/salida.out" && grep -qi 'ZASCARR_ROOT' "${W}/salida.err" "${W}/salida.out"; then
        pass "${id}b" "${texto}: el mensaje da una salida segura (/opt/zascarr, ZASCARR_ROOT)"
    else fail "${id}b" "${texto}: el mensaje no explica la salida: $(tail -c 300 "${W}/salida.err" | tr '\n' ' ')"; fi
    if ! grep -qF -- "${SINT}" "${W}/salida.out" "${W}/salida.err" 2>/dev/null; then :; else fail "${id}c" "${texto}: la salida lleva la credencial"; fi
}

# U01: ZASCARR_ROOT es el home de alguien (carpeta compartida, no dedicada): se rechaza, ya no se avisa y se sigue.
HOGAR="${W}/home/colecc"; mkdir -p "${HOGAR}/Documentos"; echo secreto-ajeno > "${HOGAR}/.bashrc"
instalacion_heredada "${HOGAR}" "${SINT}"
mkdir -p "${HOGAR}/Documentos"; chown -R "${SVC}:${SVC}" "${HOGAR}"; chmod 750 "${HOGAR}"
parar U01 "una raíz compartida de otra cuenta (un home)" "${HOGAR}"

# U02: la carpeta de ZascArr es dedicada, pero cuelga de una carpeta que escribe el usuario de servicio.
mkdir -p "${W}/publica"; chown "${SVC}:${SVC}" "${W}/publica"; chmod 755 "${W}/publica"
instalacion_heredada "${W}/publica/zascarr" "${SINT}"
parar U02 "un antecesor del que es dueño el usuario de servicio" "${W}/publica/zascarr"

# U03: un enlace en una carpeta que escribe el usuario de servicio, hacia un destino que por sí solo sería seguro.
mkdir -p "${W}/real"; chown root:root "${W}/real"; chmod 755 "${W}/real"
instalacion_heredada "${W}/real/zascarr" "${SINT}"
mkdir -p "${W}/enlaces"; chown "${SVC}:${SVC}" "${W}/enlaces"; chmod 755 "${W}/enlaces"
ln -s "${W}/real/zascarr" "${W}/enlaces/atajo"; chown -h "${SVC}:${SVC}" "${W}/enlaces/atajo"
parar U03 "un enlace que el usuario de servicio puede reapuntar" "${W}/enlaces/atajo" "${W}/real/zascarr/.env"

# U08: el enlace es de OTRA cuenta aunque viva en una carpeta de root cerrada y apunte a un destino de root.
mkdir -p "${W}/enlaces_ajeno"; chown root:root "${W}/enlaces_ajeno"; chmod 755 "${W}/enlaces_ajeno"
instalacion_heredada "${W}/real/zascarr3" "${SINT}"
ln -s "${W}/real/zascarr3" "${W}/enlaces_ajeno/atajo"; chown -h "${OTRO}:${OTRO}" "${W}/enlaces_ajeno/atajo"
parar U08 "un enlace de otra cuenta en una carpeta de root" "${W}/enlaces_ajeno/atajo" "${W}/real/zascarr3/.env"

# U04 (control positivo): un enlace DE ROOT, en una carpeta de root, hacia un destino de root, es legítimo
# (como /opt → /mnt/disco/opt) y el instalador sigue adelante.
mkdir -p "${W}/enlaces_root"; chown root:root "${W}/enlaces_root"; chmod 755 "${W}/enlaces_root"
instalacion_heredada "${W}/real/zascarr2" "${SINT}"
ln -s "${W}/real/zascarr2" "${W}/enlaces_root/atajo"
: > "${W}/docker.log"
ejecutar_instalador "${W}/enlaces_root/atajo"
if llego_a_postgres && [[ "$(modo "${W}/real/zascarr2/.env")" == "600 root:root" ]]; then
    pass U04 "un enlace de root hacia un destino de root es legítimo: la instalación sigue y el .env queda 600 root:root"
else fail U04 "con un enlace de root legítimo: rc=${RC}, $(tail -c 250 "${W}/salida.err" | tr '\n' ' ')"; fi

# U05: el propio .env es un enlace (a un fichero de otra cuenta): no se sigue, no se escribe, no se cambia su dueño.
RAIZ5="${W}/opt5/zascarr"; instalacion_heredada "${RAIZ5}" "${SINT}"
echo "DB_PASSWORD=${SINT}" > "${W}/ajeno.env"; chown "${OTRO}:${OTRO}" "${W}/ajeno.env"; chmod 644 "${W}/ajeno.env"
mv -f "${RAIZ5}/.env" "${W}/guardado.env"; ln -s "${W}/ajeno.env" "${RAIZ5}/.env"
H5="$(huella "${W}/ajeno.env")"; M5="$(modo "${W}/ajeno.env")"
: > "${W}/docker.log"
ejecutar_instalador "${RAIZ5}"
if [[ "${RC}" -ne 0 ]] && ! llego_a_postgres && [[ "$(huella "${W}/ajeno.env")" == "${H5}" && "$(modo "${W}/ajeno.env")" == "${M5}" ]]; then
    pass U05 "un .env que es un enlace no se sigue: el instalador se detiene y el fichero ajeno queda intacto"
else fail U05 "rc=${RC}; ajeno ${M5}→$(modo "${W}/ajeno.env")"; fi

# U06: raíz COMPARTIDA pero de root y cerrada (como /opt) con el repo ya de root: no se reclama y se instala.
COMP="${W}/compartida"; mkdir -p "${COMP}/otra-cosa"; chown root:root "${COMP}" "${COMP}/otra-cosa"; chmod 755 "${COMP}"
copiar_repo "${COMP}"; chown -hR root:root "${COMP}/zascarr"; chmod -R go-w "${COMP}/zascarr"
M6="$(modo "${COMP}")"
: > "${W}/docker.log"
ejecutar_instalador "${COMP}"
if llego_a_postgres && [[ "$(modo "${COMP}")" == "${M6}" && "$(modo "${COMP}/.env")" == "600 root:root" ]]; then
    pass U06 "una raíz compartida pero de root y cerrada (como /opt) no se reclama y la instalación sigue con el .env 600 root:root"
else fail U06 "raíz compartida segura: rc=${RC} $(tail -c 250 "${W}/salida.err" | tr '\n' ' ')"; fi

# U07: raíz compartida segura, pero el CÓDIGO que root ejecuta es del usuario de servicio: se detiene.
COMP2="${W}/compartida2"; mkdir -p "${COMP2}/otra-cosa"; chown root:root "${COMP2}" "${COMP2}/otra-cosa"; chmod 755 "${COMP2}"
copiar_repo "${COMP2}"; chown -R "${SVC}:${SVC}" "${COMP2}/zascarr"
echo "DB_PASSWORD=${SINT}" > "${COMP2}/.env"; chown root:root "${COMP2}/.env"; chmod 600 "${COMP2}/.env"
: > "${W}/docker.log"
H7="$(huella "${COMP2}/.env")"
ejecutar_instalador "${COMP2}"
if [[ "${RC}" -ne 0 ]] && ! llego_a_postgres && [[ "$(huella "${COMP2}/.env")" == "${H7}" ]]; then
    pass U07 "con el código en manos del usuario de servicio, el instalador se detiene en vez de avisar y seguir"
else fail U07 "rc=${RC}; Postgres=$(llego_a_postgres && echo si || echo no)"; fi

rm -rf "${W}"
exit 0
