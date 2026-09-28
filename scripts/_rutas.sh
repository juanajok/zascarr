#!/usr/bin/env bash
# =============================================================================
# _rutas.sh — A9: rutas EFECTIVAS del instalador (biblioteca vs. cola de entrada).
#
# NO se ejecuta solo: se carga con `source`. NO toca nada — ni rutas, ni
# permisos, ni montajes. Solo resuelve, compara e informa; el que decide es
# quien lo llama.
#
# Por qué existe (A9). Si la biblioteca y las descargas son la misma carpeta
# —o una está dentro de la otra—, el importador mira como "cola de entrada"
# algo que ya es la tebeoteca organizada: el dedupe por SHA256 evita importar
# dos veces el mismo fichero, pero la distinción "ya organizado" vs. "por
# importar" deja de existir. La instalación es el momento de decirlo, porque
# es cuando se puede corregir sin haber tocado nada todavía.
#
# Por qué se comprueban DOS cosas y no solo el inodo, que es lo que decía el
# backlog: dos carpetas ANIDADAS tienen inodos distintos y aun así se solapan
# (el importador escanea recursivamente), así que la igualdad de `(st_dev,
# st_ino)` no las vería. Y al revés: dos rutas de texto distinto pueden ser la
# MISMA carpeta por un bind mount, cosa que el texto no dice. Se comprueban
# las dos, sobre la ruta ya resuelta.
#
# Todo se compara sobre la ruta EFECTIVA (symlinks resueltos), no sobre lo que
# el usuario tecleó: `/mnt/tebeos` y `/media/tebeoteca` pueden ser la misma
# carpeta y el texto no lo dice.
# =============================================================================

# resolver_ruta RUTA
#   Imprime la ruta canónica: symlinks resueltos, "." y ".." normalizados.
#   Acepta un sufijo que todavía no exista (instalación nueva), pero **todos
#   los componentes que ya están —symlinks incluidos— tienen que resolverse de
#   verdad**. Devuelve 1 con el motivo por stderr si no puede.
resolver_ruta() {
    local ruta="$1" absoluta prefijo componente destino
    local resuelta ancestro
    local -a partes=()

    if [[ -z "${ruta}" ]]; then
        echo "ruta vacía" >&2
        return 1
    fi

    absoluta="${ruta}"
    if [[ "${absoluta}" != /* ]]; then
        # Ruta relativa: se resuelve contra el cwd. No hace falta más, porque
        # esto solo se usa para INSPECCIONAR los componentes (el resultado
        # canónico lo da `realpath` sobre la ruta original).
        absoluta="${PWD:-/}/${absoluta}"
    fi

    # 1) Symlinks que no llevan a ninguna parte. `realpath -m` **no** sirve para
    #    esto: está pensado justamente para canonicalizar rutas con componentes
    #    ausentes o no disponibles, así que sigue un symlink roto y devuelve su
    #    destino inexistente como si fuera una carpeta nueva perfectamente
    #    válida. Hay que mirarlo sobre la ruta ORIGINAL, componente a
    #    componente: `[[ -L ]]` dice si el componente ES un symlink (lstat, no
    #    sigue) y `[[ -e ]]` si además se puede seguir (stat, sí sigue).
    local IFS=/
    read -r -a partes <<< "${absoluta}"
    prefijo=""
    for componente in "${partes[@]}"; do
        [[ -n "${componente}" ]] || continue
        prefijo="${prefijo}/${componente}"

        if [[ -L "${prefijo}" && ! -e "${prefijo}" ]]; then
            # Un solo mensaje para los dos casos: `-L` sin `-e` es un enlace que
            # no se puede seguir, sea porque su destino no existe o porque da
            # vueltas. Distinguirlos exigiría seguir la cadena a mano, y para
            # el coleccionista la acción es la misma: arreglar el enlace.
            destino="$(readlink -- "${prefijo}" 2>/dev/null || echo "?")"
            echo "«${prefijo}» es un symlink roto (o en bucle): apunta a «${destino}» y no lleva a ninguna carpeta" >&2
            return 1
        fi

        # Primer componente que no existe: de aquí en adelante es sufijo nuevo,
        # y que no exista es legítimo (una biblioteca recién indicada). Todo lo
        # ANTERIOR ya se ha comprobado.
        if [[ ! -e "${prefijo}" ]]; then
            break
        fi
    done

    # 2) Canonicalización. -m: sigue aceptando el sufijo nuevo.
    if ! resuelta="$(realpath -m -- "${ruta}" 2>/dev/null)"; then
        echo "no puedo resolver «${ruta}»: ¿hay un symlink en bucle o te falta permiso en alguna carpeta por encima?" >&2
        return 1
    fi
    if [[ -z "${resuelta}" ]]; then
        echo "no puedo resolver «${ruta}»" >&2
        return 1
    fi

    # 3) El ancestro más profundo que YA existe tiene que ser una carpeta: si es
    #    un fichero, la ruta no se podrá crear después y es mejor decirlo aquí,
    #    con el nombre de la ruta, que dejar que reviente un `mkdir`.
    ancestro="${resuelta}"
    while [[ ! -e "${ancestro}" && "${ancestro}" != "/" ]]; do
        ancestro="$(dirname -- "${ancestro}")"
    done
    if [[ -e "${ancestro}" && ! -d "${ancestro}" ]]; then
        echo "«${ruta}» no puede ser una carpeta: «${ancestro}» ya existe y es un fichero" >&2
        return 1
    fi

    printf '%s\n' "${resuelta}"
}

# motivo_solapamiento A B
#   A y B tienen que venir YA resueltas. Si se solapan, imprime el motivo y
#   devuelve 0; si son independientes, no imprime nada y devuelve 1.
motivo_solapamiento() {
    local a="$1" b="$2" ia ib

    if [[ "${a}" == "${b}" ]]; then
        echo "es la misma carpeta"
        return 0
    fi

    # Dos rutas distintas, la misma carpeta: bind mount, o el mismo
    # directorio alcanzado por caminos que `realpath` no unifica. Solo se
    # compara si las DOS existen — si no, `stat` falla en ambas y dos
    # cadenas vacías darían un falso positivo.
    if [[ -d "${a}" && -d "${b}" ]]; then
        ia="$(stat -c '%d:%i' -- "${a}" 2>/dev/null || true)"
        ib="$(stat -c '%d:%i' -- "${b}" 2>/dev/null || true)"
        if [[ -n "${ia}" && "${ia}" == "${ib}" ]]; then
            echo "es la misma carpeta (mismo dispositivo e inodo, por otra ruta)"
            return 0
        fi
    fi

    # Anidamiento. La barra final es lo que hace que esto sea por COMPONENTES
    # y no por texto: "/media/lib" NO está dentro de "/media/library", aunque
    # la cadena "/media/lib" sea un prefijo de "/media/library".
    if [[ "${a}/" == "${b}/"* ]]; then
        echo "está dentro de la otra («${a}» dentro de «${b}»)"
        return 0
    fi
    if [[ "${b}/" == "${a}/"* ]]; then
        echo "está dentro de la otra («${b}» dentro de «${a}»)"
        return 0
    fi

    return 1
}

# _linea_ruta ETIQUETA ORIGINAL RESUELTA
_linea_ruta() {
    if [[ "$2" == "$3" ]]; then
        printf '  %-16s %s\n' "$1" "$3"
    else
        printf '  %-16s %s  (lo que escribiste: %s)\n' "$1" "$3" "$2"
    fi
}

# _pareja_solapada ETIQUETA_A A ETIQUETA_B B
#   Imprime el aviso si A y B se solapan. Devuelve 0 si lo hizo.
_pareja_solapada() {
    local motivo
    motivo="$(motivo_solapamiento "$2" "$4")" || return 1
    echo "  ⚠ ${1} y ${3}: ${motivo}"
    return 0
}

# comprobar_solapamiento BIBLIOTECA DESCARGAS AMULE
#   Imprime el informe con las rutas EFECTIVAS y, si las hay, las parejas que
#   se solapan. Devuelve:
#     0 → sin solapamiento
#     1 → hay solapamiento (el que llama decide si pide confirmación)
#     2 → no se pudo resolver alguna ruta (el motivo ya está en stderr)
#
#   Se compara la BIBLIOTECA contra cada cola de entrada, y NO las dos colas
#   entre sí: `bootstrap.sh` da a descargas y a aMule la MISMA carpeta a
#   propósito (son dos montajes —/media/downloads y /media/incoming— del mismo
#   sitio), así que avisar de esa pareja sería avisar en todas las
#   instalaciones. Lo que rompe la distinción es que la biblioteca se solape
#   con una cola, que es justo lo que se comprueba.
comprobar_solapamiento() {
    local bib desc amule avisos=0

    bib="$(resolver_ruta "$1")" || return 2
    desc="$(resolver_ruta "$2")" || return 2
    amule="$(resolver_ruta "$3")" || return 2

    echo "Rutas efectivas (con los symlinks ya resueltos):"
    _linea_ruta "biblioteca:" "$1" "${bib}"
    _linea_ruta "descargas:" "$2" "${desc}"
    _linea_ruta "aMule (entrada):" "$3" "${amule}"

    echo ""
    # `if` explícito y no `cond && accion`: este script se carga en un shell con
    # `set -e`, y una lista `&&` cuyo lado izquierdo falla deja un estado que no
    # conviene dejar a la interpretación de errexit.
    if _pareja_solapada "la biblioteca" "${bib}" "las descargas" "${desc}"; then
        avisos=$((avisos + 1))
    fi
    if _pareja_solapada "la biblioteca" "${bib}" "la entrada de aMule" "${amule}"; then
        avisos=$((avisos + 1))
    fi

    if [[ "${avisos}" -gt 0 ]]; then
        return 1
    fi
    echo "  Sin solapamiento."
    return 0
}

# pedir_confirmacion_solapamiento
#   Pregunta por stdin. Devuelve 0 solo si el usuario escribe exactamente "s"
#   (o "S"): la respuesta por defecto es NO, y sin terminal (EOF) también.
pedir_confirmacion_solapamiento() {
    local respuesta=""
    read -rp "¿Continuar de todas formas? [s/N]: " respuesta || true
    [[ "${respuesta}" == "s" || "${respuesta}" == "S" ]]
}
