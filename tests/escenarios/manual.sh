#!/usr/bin/env bash
# Escenario «instalación manual»: quien instala con Docker Compose a mano usa la inicialización EXPLÍCITA
# (`scripts/credenciales.sh`), que hace lo mismo que el instalador. Se ejecuta el script real como root.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo

RAIZ="${W}/opt/zascarr"; mkdir -p "${RAIZ}"; copiar_repo "${RAIZ}"
CRED="${RAIZ}/zascarr/scripts/credenciales.sh"
iniciar() { env ZASCARR_DATA_DIR="${W}/datos" bash "${CRED}" "$@" >"${W}/m.out" 2>"${W}/m.err"; MRC=$?; }

iniciar iniciar
V1="$(valor_de "${RAIZ}/.env")"
if [[ "${MRC}" -eq 0 && ${#V1} -ge 32 ]]; then pass M01 "sin .env: lo crea y genera una DB_PASSWORD propia"; else fail M01 "rc=${MRC}"; fi
if [[ "$(modo "${RAIZ}/.env")" == "600 root:root" && "$(readlink "${RAIZ}/zascarr/.env")" == "${RAIZ}/.env" ]]; then
    pass M02 "queda 600 root:root y con el enlace del repo apuntando a él"; else fail M02 "$(modo "${RAIZ}/.env")"; fi
iniciar iniciar
if [[ "${MRC}" -eq 0 && "$(valor_de "${RAIZ}/.env")" == "${V1}" ]]; then pass M03 "reejecutar la conserva (idempotente)"; else fail M03 "cambió"; fi
if ! grep -qF -- "${V1}" "${W}/m.out" "${W}/m.err"; then pass M04 "no imprime la contraseña"; else fail M04 "la imprime"; fi
afirmar M05 "comprobar: en orden" bash "${CRED}" comprobar

# Un .env heredado (644) se detecta y se corrige sin cambiar la contraseña
chmod 644 "${RAIZ}/.env"
negar M06 "comprobar detecta un .env legible por otros (sale con error)" bash "${CRED}" comprobar
iniciar iniciar
if [[ "${MRC}" -eq 0 && "$(modo "${RAIZ}/.env")" == "600 root:root" && "$(valor_de "${RAIZ}/.env")" == "${V1}" ]]; then
    pass M07 "iniciar lo corrige sin cambiar la contraseña"; else fail M07 "$(modo "${RAIZ}/.env")"; fi

# Base ya creada y sin contraseña conocida: se detiene y explica; no inventa otra
RAIZ2="${W}/opt2/zascarr"; mkdir -p "${RAIZ2}"; copiar_repo "${RAIZ2}"
mkdir -p "${W}/datos/postgres"; echo 15 > "${W}/datos/postgres/PG_VERSION"
(umask 077; cp "${RAIZ2}/zascarr/.env.example" "${RAIZ2}/.env")
H="$(huella "${RAIZ2}/.env")"
env ZASCARR_DATA_DIR="${W}/datos" bash "${RAIZ2}/zascarr/scripts/credenciales.sh" iniciar >"${W}/m.out" 2>"${W}/m.err"; MRC=$?
if [[ "${MRC}" -ne 0 && "$(huella "${RAIZ2}/.env")" == "${H}" ]] && grep -q 'No he cambiado ninguna contraseña' "${W}/m.err"; then
    pass M08 "con una base ya creada y sin contraseña: se detiene con mensaje de recuperación y no cambia el .env"
else fail M08 "rc=${MRC}"; fi

rm -rf "${W}"
exit 0
