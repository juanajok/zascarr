#!/usr/bin/env bash
# Escenario «guion de la fase 1 bis»: el propio guion del ensayo (docs/design/m4-fase1bis/vm-ejecutar.sh) tiene que medir bien.
# Se carga su sección de identidades y se prueba contra (G01) una instalación REAL protegida por el bootstrap.sh del repo y
# (G02) una instalación HEREDADA y expuesta: el guion tiene que dar todo PASS en la primera y PARARSE (código 3, sin reparar)
# en la segunda. Un guion que no detecta una exposición real no sirve para validar una instalación real.
source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"
preparar_usuarios
nuevo_trabajo
poner_docker_de_pega
GUION="${REPO}/docs/design/m4-fase1bis/vm-ejecutar.sh"
[[ -f "${GUION}" ]] || { fail G00 "no existe ${GUION}"; exit 0; }

# ejecutar_identidades RAIZ → salida en ${W}/guion.out, código en GRC
ejecutar_identidades() {
    local raiz="$1"
    ( export EV="${W}/ev" RAIZ="${raiz}" SVC="${SVC}" OTRO="${OTRO}" BIBLIOTECA="${W}/biblioteca"
      mkdir -p "${W}/ev" "${W}/biblioteca"
      source "${GUION}"
      PATH="${W}/bin:${PATH}" seccion_credenciales ) > "${W}/guion.out" 2>&1
    GRC=$?
}

# G01: instalación real y protegida
RAIZ="${W}/opt/zascarr"; mkdir -p "${RAIZ}"; copiar_repo "${RAIZ}"
echo "# stub" > "${RAIZ}/zascarr/Dockerfile"
ejecutar_instalador "${RAIZ}"
SINT="$(valor_de "${RAIZ}/.env")"
H0="$(huella "${RAIZ}/.env")"
ejecutar_identidades "${RAIZ}"
NPASS="$(grep -c '^PASS' "${W}/guion.out")"; NFAIL="$(grep -c '^FAIL' "${W}/guion.out")"
if [[ "${GRC}" -eq 0 && "${NFAIL}" -eq 0 && "${NPASS}" -ge 38 ]]; then
    pass G01 "sobre una instalación real protegida, la sección de credenciales (estáticas + identidades) da ${NPASS} PASS y 0 FAIL"
else fail G01 "rc=${GRC} PASS=${NPASS} FAIL=${NFAIL}: $(grep '^FAIL' "${W}/guion.out" | head -n 3 | tr '\n' ';')"; fi
if grep -q 'C-11 ' "${W}/guion.out" && grep -q 'C-10-' "${W}/guion.out"; then pass G01b "incluye los controles positivos (C-10, C-11, C-12)"
else fail G01b "faltan controles positivos"; fi
if [[ "$(huella "${RAIZ}/.env")" == "${H0}" && "$(modo "${RAIZ}/.env")" == "600 root:root" ]]; then pass G01c "el guion no tocó el .env"
else fail G01c "el .env cambió durante el guion"; fi
if [[ -n "${SINT}" ]] && ! grep -qF -- "${SINT}" "${W}/guion.out"; then pass G01d "el guion no imprime la credencial"
else fail G01d "la salida del guion contiene la credencial (o no había)"; fi

# G01e: las comprobaciones ESTÁTICAS usan órdenes de Debian 12 que no se prueban de otro modo (p. ej. `stat` sobre el enlace)
ESTATICAS_OK=1
for c in C-01 C-02 C-03 C-04 C-05 C-06 C-07; do grep -q "^PASS ${c} " "${W}/guion.out" || { ESTATICAS_OK=0; echo "# falta PASS ${c}" >&2; }; done
if [[ "${ESTATICAS_OK}" -eq 1 ]]; then pass G01e "las comprobaciones estáticas C-01…C-07 (propietario, modo, repo, enlace con stat, contraseña, compose) dan PASS en Debian 12"
else fail G01e "alguna comprobación estática no dio PASS: $(grep -E '^(FAIL|NOT_RUN) C-0' "${W}/guion.out" | head -n 3 | tr '\n' ';')"; fi

# G02: instalación heredada y expuesta (todo del usuario de servicio, .env legible por todos)
RAIZ2="${W}/opt2/zascarr"; instalacion_heredada "${RAIZ2}" "Sint3tica-Expuesta-0006-$$"
echo "# stub" > "${RAIZ2}/zascarr/Dockerfile"; chown "${SVC}:${SVC}" "${RAIZ2}/zascarr/Dockerfile"
H2="$(huella "${RAIZ2}/.env")"; M2="$(modo "${RAIZ2}/.env")"
ejecutar_identidades "${RAIZ2}"
if [[ "${GRC}" -eq 3 ]] && grep -q 'PARADA DE SEGURIDAD' "${W}/guion.out" && grep -q '^FAIL' "${W}/guion.out"; then
    pass G02 "sobre una instalación expuesta el guion SE PARA (código 3) en el primer intento que tiene éxito"
else fail G02 "no se paró: rc=${GRC}; $(tail -n 3 "${W}/guion.out" | tr '\n' ';')"; fi
if [[ "$(huella "${RAIZ2}/.env")" == "${H2}" && "$(modo "${RAIZ2}/.env")" == "${M2}" ]]; then pass G02b "y no repara nada para que parezca PASS (el .env sigue exactamente como estaba)"
else fail G02b "el guion modificó el .env"; fi
if ! grep -qF -- "Sint3tica-Expuesta-0006-$$" "${W}/guion.out"; then pass G02c "tampoco imprime la credencial al fallar"
else fail G02c "imprime la credencial"; fi

rm -rf "${W}"
exit 0
