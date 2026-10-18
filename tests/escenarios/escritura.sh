#!/usr/bin/env bash
# Escenario «escritura» (C4): el secreto nuevo NUNCA vive en un fichero abierto. Una instalación HEREDADA tiene el
# `.env` en 644 y del usuario de servicio; se pasa por el instalador real y por `credenciales.sh iniciar` con un `mv`
# de envoltorio que anota el modo y el propietario de todo lo que se renombra EN ESE INSTANTE. Antes de la corrección
# el temporal heredaba el modo 644 del original y la contraseña generada quedaba legible por todos hasta que otra
# función cerraba el fichero, más tarde.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo
poner_docker_de_pega

cat > "${W}/bin/mv" <<'STUB'
#!/bin/sh
for a in "$@"; do
    case "$a" in -*) ;; *) [ -e "$a" ] && [ ! -L "$a" ] && echo "$(basename "$a") $(stat -c '%a %U:%G' "$a")" >> "$MV_LOG" ;; esac
done
exec /bin/mv "$@"
STUB
chmod 755 "${W}/bin/mv"

verificar_registro() {
    local id="$1" texto="$2" malas
    [[ -s "${MV_LOG}" ]] || { fail "${id}" "${texto}: el envoltorio no anotó ningún renombrado (la prueba no observó nada)"; return; }
    malas="$(grep -v ' 600 root:root$' "${MV_LOG}" | sed 's/ [0-9a-f]\{48\}//' || true)"
    malas="$(awk '$2 != "600" || $3 != "root:root"' "${MV_LOG}")"
    if [[ -z "${malas}" ]]; then pass "${id}" "${texto}"; else fail "${id}" "${texto}: $(echo "${malas}" | tr '\n' ';')"; fi
}

# ── W01-W04: el instalador sobre un .env heredado (644, del usuario de servicio, con el marcador) ─────────
RAIZ="${W}/opt/zascarr"
instalacion_heredada "${RAIZ}" "cambia_esto_ahora"
chmod 666 "${RAIZ}/.env"                                          # peor aún que 644: lo escribe cualquiera
export MV_LOG="${W}/mv.log"; : > "${MV_LOG}"
printf '%s\n%s\n%s\n' "${W}/biblioteca" "${W}/descargas" es | \
    env PATH="${W}/bin:${PATH}" STUB_LOG="${W}/docker.log" MV_LOG="${MV_LOG}" _ZASCARR_YA_ACTUALIZADO=1 \
        ZASCARR_DATA_DIR="${W}/datos" ZASCARR_USER="${SVC}" ZASCARR_GROUP="${SVC}" \
        bash "${RAIZ}/zascarr/bootstrap.sh" >"${W}/salida.out" 2>"${W}/salida.err"
RC=$?
V="$(valor_de "${RAIZ}/.env")"
if [[ ${#V} -ge 32 && "${V}" != "cambia_esto_ahora" ]]; then pass W01 "el instalador generó la contraseña sobre un .env heredado en 666"
else fail W01 "no se generó contraseña (rc=${RC}): $(tail -c 200 "${W}/salida.err" | tr '\n' ' ')"; fi
verificar_registro W02 "al renombrarse, el temporal y el .env de destino ya eran 600 root:root (nunca 666/644 del usuario de servicio)"
if [[ "$(modo "${RAIZ}/.env")" == "600 root:root" ]]; then pass W03 "el .env final es 600 root:root"
else fail W03 "el .env final es $(modo "${RAIZ}/.env")"; fi
if ! ls -a "${RAIZ}" | grep -q '^\.env\.tmp\.'; then pass W04 "no queda ningún temporal junto al .env"
else fail W04 "queda un temporal"; fi

# ── W05-W06: lo mismo con la herramienta de la instalación manual ────────────────────────────────────
RAIZ2="${W}/opt2/zascarr"
instalacion_heredada "${RAIZ2}" "changeme"
chmod 644 "${RAIZ2}/.env"
: > "${MV_LOG}"
env PATH="${W}/bin:${PATH}" MV_LOG="${MV_LOG}" ZASCARR_DATA_DIR="${W}/datos2" \
    bash "${RAIZ2}/zascarr/scripts/credenciales.sh" iniciar >"${W}/man.out" 2>"${W}/man.err"
V2="$(valor_de "${RAIZ2}/.env")"
if [[ ${#V2} -ge 32 && "${V2}" != "changeme" ]]; then pass W05 "credenciales.sh iniciar generó la contraseña sobre un .env heredado en 644"
else fail W05 "no se generó (rc=$?): $(tail -c 200 "${W}/man.err" | tr '\n' ' ')"; fi
verificar_registro W06 "y también ahí el secreto nuevo nunca estuvo en un fichero abierto"

rm -rf "${W}"
exit 0
