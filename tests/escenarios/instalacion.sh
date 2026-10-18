#!/usr/bin/env bash
# Escenario «instalación» de las pruebas de credenciales: ejecuta el bootstrap.sh REAL (con un `docker` de pega que
# se detiene al ir a crear PostgreSQL) sobre instalaciones sintéticas y comprueba qué `.env` queda y qué ve Compose.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo
poner_docker_de_pega

# ── I01-I04: instalación NUEVA, sin tocar nada a mano ────────────────────────────────────────────
RAIZ="${W}/opt/zascarr"; mkdir -p "${RAIZ}"; copiar_repo "${RAIZ}"
ejecutar_instalador "${RAIZ}"
if llego_a_postgres; then pass I01 "una instalación nueva llega a crear PostgreSQL sin editar el .env a mano"
else fail I01 "no llegó a crear PostgreSQL (rc=${RC}): $(tail -c 220 "${W}/salida.err" | tr '\n' ' ')"; fi
LON="$(cat "${W}/docker.log.visto" 2>/dev/null | head -1)"
if [[ "${LON}" =~ ^len=([0-9]+)$ && "${BASH_REMATCH[1]}" -ge 32 ]]; then
    pass I02 "la contraseña que ve Compose se generó sola (${LON})"
else
    fail I02 "la contraseña que ve Compose no es una generada (${LON:-sin dato})"
fi
if [[ "$(modo "${RAIZ}/.env")" == "600 root:root" ]]; then pass I03 "el .env queda 600 root:root"
else fail I03 "el .env queda $(modo "${RAIZ}/.env")"; fi
H1="$(huella "${RAIZ}/.env")"; V1="$(valor_de "${RAIZ}/.env")"; HP1="$(printf '%s' "${V1}" | sha256sum | cut -c1-16)"
: > "${W}/docker.log"; rm -f "${W}/docker.log.visto" "${W}/docker.log.huellas"
ejecutar_instalador "${RAIZ}"
V2="$(valor_de "${RAIZ}/.env")"
if [[ ${#V1} -ge 32 && "${V1}" == "${V2}" ]]; then pass I04 "reejecutar conserva la contraseña generada (huella ${HP1})"
else fail I04 "reejecutar cambió o perdió la contraseña"; fi
# I07 (parte 1): ni la salida del instalador ni lo que vio Docker contienen el valor generado.
if [[ ${#V1} -ge 32 ]] && ! grep -qF -- "${V1}" "${W}/salida.out" "${W}/salida.err" "${W}/docker.log" 2>/dev/null; then
    pass I07a "la contraseña generada no aparece en la salida del instalador ni en las órdenes a Docker"
else fail I07a "la contraseña generada aparece (o no había) en la salida"; fi

# ── I05: base YA inicializada y sin contraseña conocida → parar, no inventar otra ─────────────────
RAIZ2="${W}/opt2/zascarr"; mkdir -p "${RAIZ2}"; copiar_repo "${RAIZ2}"
mkdir -p "${W}/datos/postgres" && echo 15 > "${W}/datos/postgres/PG_VERSION"
: > "${W}/docker.log"
ejecutar_instalador "${RAIZ2}"
if [[ "${RC}" -ne 0 ]] && ! llego_a_postgres && grep -q 'No he cambiado ninguna contraseña' "${W}/salida.err"; then
    pass I05 "con una base ya creada y sin contraseña, el instalador se detiene con mensaje de recuperación"
else fail I05 "rc=${RC}; llegó a Postgres=$(llego_a_postgres && echo si || echo no)"; fi
if grep -q '^DB_PASSWORD=cambia_esto_ahora$' "${RAIZ2}/.env"; then pass I05b "y no inventó una contraseña nueva en el .env"
else fail I05b "el .env cambió"; fi
rm -rf "${W}/datos/postgres"

# ── I06: una credencial válida y existente se conserva ───────────────────────────────────────────
SINT="Sint3tica-Valida-0001-$$"
RAIZ3="${W}/opt3"; instalacion_heredada "${RAIZ3}" "${SINT}"
: > "${W}/docker.log"; rm -f "${W}/docker.log.visto" "${W}/docker.log.huellas"
ejecutar_instalador "${RAIZ3}"
if llego_a_postgres && [[ "$(valor_de "${RAIZ3}/.env")" == "${SINT}" ]]; then pass I06 "la credencial válida existente se conserva tal cual"
else fail I06 "la credencial válida no se conservó o no llegó a Postgres"; fi
if ! grep -qF -- "${SINT}" "${W}/salida.out" "${W}/salida.err" "${W}/docker.log" 2>/dev/null; then
    pass I07b "la credencial sintética no aparece en la salida ni en las órdenes a Docker"
else fail I07b "la credencial sintética aparece en la salida"; fi

# ── I09: ausente, vacía, con comillas, ejemplo de otra época → todas se sustituyen por una generada ─
i=0
for caso in 'vacia|DB_PASSWORD=' 'ausente|' 'comillas|DB_PASSWORD="cambia_esto_ahora"' 'compose|DB_PASSWORD=SuperSecretPassword123' \
            'mayusculas|DB_PASSWORD=CAMBIA_ESTO_AHORA' 'espacios|DB_PASSWORD=  changeme  '; do
    i=$((i+1)); nombre="${caso%%|*}"; linea="${caso#*|}"
    R="${W}/caso${i}"; mkdir -p "${R}"; copiar_repo "${R}"
    grep -v '^DB_PASSWORD=' "${R}/zascarr/.env.example" > "${R}/.env"
    [[ -n "${linea}" ]] && echo "${linea}" >> "${R}/.env"
    chmod 600 "${R}/.env"
    : > "${W}/docker.log"; rm -f "${W}/docker.log.visto"
    ejecutar_instalador "${R}"
    N="$(valor_de "${R}/.env")"
    if llego_a_postgres && [[ ${#N} -ge 32 && "${N,,}" != *cambia_esto_ahora* && "${N,,}" != *supersecret* && "${N,,}" != *changeme* ]]; then
        pass "I09-${nombre}" "valor ${nombre}: se genera una contraseña propia"
    else fail "I09-${nombre}" "valor ${nombre}: no se corrigió (rc=${RC})"; fi
done

# ── I08: la plantilla no lleva secretos reales ───────────────────────────────────────────────────
PL="$(grep '^DB_PASSWORD=' "${REPO}/.env.example" | cut -d= -f2-)"
if [[ -z "${PL}" || "${PL}" == "cambia_esto_ahora" ]]; then pass I08 ".env.example: DB_PASSWORD vacío o placeholder obvio"
else fail I08 ".env.example lleva un valor que no es un placeholder"; fi

rm -rf "${W}"
exit 0
