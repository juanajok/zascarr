"""
Normalización de nombres de archivos de cómic.

Tres capas:
  1. Regex: extrae serie, número, volumen, año del filename (70% de casos)
  2. Normalización: elimina ruido, artículos, puntuación (20%)
  3. Fuzzy (pg_trgm en DB, ver matcher.py): 10% restante

NOTA: parse_comic_filename es la función principal para la Capa 1.
Los tests en tests/test_naming_core.py cubren los filenames reales
de la escena que debe resolver.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NOISE_PATTERNS = [
    r"\(Digital\)", r"\(digital\)", r"\(Digital-\w+\)",
    r"\(Minutemen-\w+\)", r"\(Zone-\w+\)", r"\(Empire\)",
    r"\(Glorith-HD\)", r"\(F\)\s*", r"\(c2c\)", r"\(noads\)",
    r"\(HD\)", r"\(SD\)", r"\(Webrip\)", r"\(Scan\)",
    r"\((?:19|20)[0-9]{2}\)",   # año entre paréntesis: cubre 19xx Y 20xx
                                # (antes solo "20xx"; perdía años como 1989)
]

# Cada entrada es (patrón, cortar_en_el_numero). El corte marca dónde
# termina el título una vez encontrado el número:
#   False → se corta al principio de la coincidencia (lo normal: "AIDP 05
#           - La Llama Negra" deja "AIDP").
#   True  → se corta en el número capturado, conservando lo que haya
#           delante. Solo lo usa el caso "Serie NN - MM", donde el primer
#           número es parte del título ("Delta 99 - 04" es el número 4 de
#           la serie "Delta 99", no el 99 de "Delta").
ISSUE_PATTERNS = [
    # El sufijo de letra va en MAYÚSCULA O minúscula en todos los patrones
    # ("#22b", "019B", "123a", "176b"): la escena no es consistente y antes
    # solo se aceptaba minúscula. Con mayúscula, el patrón simplemente no
    # matcheaba y el número se perdía entero — o peor, el parser seguía
    # buscando y encontraba OTRO número más adelante en el nombre (bug real:
    # "Flash v2 019B Dc Bonus Book 09" daba #9, no #19B).
    (r"#\s*(\d+[a-zA-Z]?\.?\d*)", False),
    (r"c(\d{3,4})\b", False),                # One Piece c1054
    (r"\bT(\d{2})\b", False),                 # Astérix T01: BD de tomo único,
                                              # el tomo ES el número de cara
                                              # a catalogación (no un volumen
                                              # de trade paperback americano).
    # "nº 03", "n° 5", "núm. 7" y su mojibake "n║05" — la numeración
    # española, que no estaba cubierta. El "║" no es un error de copia:
    # media biblioteca real viene de scans con nombres en CP437 releídos
    # como Latin-1 ("Espa±a", "Traducci≤n"), y ahí "º" aparece así.
    (r"(?:Issue|No\.?|N[úu]m(?:ero)?\.?|[Nn][ºo°º║])\s*(\d{1,4}[a-zA-Z]?)\b", False),
    # El sufijo de letra es real y frecuente ("Superman Vol2 123a" son las
    # entregas partidas de Zinco); sin él, esos números se perdían enteros.
    (r"\b(\d{3,4}[a-zA-Z]?)\b(?!\s*\))", False),
    # "Serie NN - MM": los dos son números y el de la IZQUIERDA es parte
    # del título ("Delta 99 - 04" es el 4 de la serie "Delta 99"). Va
    # antes que el patrón de subtítulo de abajo, que si no se quedaría
    # con el 99 y dejaría la serie en "Delta".
    (r"\s\d{1,3}\s+-\s+(\d{1,3}[a-zA-Z]?)\b", True),
    # "Serie NN - Subtítulo": el idiom más común de la escena en español
    # ("AIDP 05 - La Llama Negra", "Astérix (DI) 01 - Astérix el galo",
    # "Gideon Falls 01 - El Granero Negro"). El número va ANTES del
    # separador de subtítulo, no al final del nombre, así que el patrón
    # de último recurso de abajo no lo veía: el número se quedaba pegado
    # al título ("Astérix 01") y ninguna serie igualaba nunca.
    (r"\s(\d{1,3}[a-zA-Z]?)\s+-\s+", False),
    # "Serie NN Subtítulo" sin separador ("XIII 01 El Dia del Sol Negro").
    # Se exige que detrás venga una PALABRA, no otra cifra: así "Top 10
    # 07" no confunde el 10 del título con el número, porque detrás del
    # 10 hay un 07 y no una letra.
    (r"\s(\d{1,3}[a-zA-Z]?)\s+(?=[^\W\d_])", False),
    # Último recurso: un número suelto de 1-3 cifras pegado al final del
    # nombre (sin "#", sin "T", sin años de 4 cifras que ya cubre el
    # patrón de arriba con \b(\d{3,4})\b). Bug real: "La Patrulla-X
    # Original 1.cbr" no llevaba NINGÚN marcador delante del número.
    (r"\s(\d{1,3}[a-zA-Z]?)\s*$", False),
]

# Créditos del uploader al final del nombre ("por TheRockJR", "By
# Spiderman2099", "Traducido por X"): no son parte del título y además
# tapaban el número, que quedaba a media cadena en vez de al final.
CREDITS_PATTERN = re.compile(
    r"\s+\(?(?:traducido\s+por|escaneado\s+por|por|by)\s+.+$", re.IGNORECASE
)

# Ediciones de aniversario de la escena ("Integral 20 aniversario", "8º
# Aniversario"): el número es de la efeméride, no del tebeo. Sin esto,
# "Iberia Inc. - Integral 20 aniversario" se registraba como el nº 20.
ANIVERSARIO_PATTERN = re.compile(
    r"\b(?:\d+|[IVXL]+)\s*(?:º|ª|°|o|mo|er|to)?\s*aniversario\b", re.IGNORECASE
)

# El punto como separador es habitual en los scans ("La.Mazmorra..
# Integral.6.-.Sfar"). Se convierte en espacio ANTES de extraer el
# número, no en la limpieza final: si no, ni "Integral 6" ni el corte de
# subtítulo " - " se reconocían y el título se quedaba con los autores
# pegados. No se toca el punto ENTRE CIFRAS, que es un número decimal
# real ("#1.5", los paquetes decimales que el modelo sí soporta).
DOT_SEPARATOR_PATTERN = re.compile(r"(?<!\d)\.|\.(?!\d)")

# Líneas editoriales de reedición que anteponen su propio nombre al de la
# serie real, con " - " como separador ("Marvel Gold - La Patrulla-X
# Original 1.cbr") — al revés que "Serie - Subtítulo". Sin esto, el split
# de subtítulo de más abajo se queda con el nombre de la línea editorial
# en vez de con la serie.
IMPRINT_PREFIX_PATTERN = re.compile(
    r"^(?:Marvel\s+Gold|Marvel\s+Deluxe|Biblioteca\s+Marvel|Panini\s+Cl[aá]sicos|EVENTOS)"
    r"\s*-\s*",
    re.IGNORECASE,
)

# Cada entrada es (patrón, etiqueta) — la etiqueta identifica qué tipo de
# marcador matcheó, para poder usarla como `edition_kind` cuando ese
# número resulta ser el ÚNICO identificador del archivo (ver más abajo,
# "sin otro número real: el propio tomo/volumen es el identificador").
VOLUME_PATTERNS = [
    (r"Vol\.?\s*(\d+)", "volumen"),
    (r"Volume\s*(\d+)", "volumen"),
    (r"\bv(\d+)\b", "volumen"),
    (r"Tomo\s*(\d+)", "tomo"),
]

YEAR_PATTERN = re.compile(r"\((\d{4})\)")

# Fecha de publicación "(AAAA-MM)" — idiom de los scans digitales de DCP/
# Novus ("JSA (2004-08) 62"). Bug real de producción (biblioteca del
# coleccionista, 2026-09-25): sin esto, "2004" caía en el patrón genérico
# \b(\d{3,4})\b y se registraba como NÚMERO DE GRAPA. Un JSA #2004 en la
# biblioteca es exactamente la "corrupción silenciosa" que matcher.py se
# propone evitar, y con la sugerencia de un clic (B12) el coleccionista
# la confirmaba sin verla venir. El mes se descarta: el modelo no tiene
# dónde guardarlo y el año ya desambigua la serie.
PUBLICATION_DATE_PATTERN = re.compile(r"\(((?:19|20)\d{2})-(?:0[1-9]|1[0-2])\)")

# Rango de números: "(144-158)", "049-051a", "(26-30)". Es un PACK o una
# recopilación que cubre varios números, no un número. Antes se quedaba
# con el primero del rango ("La Imposible Patrulla X (144-158)" → #144),
# inventando una pertenencia que el archivo no afirma. Sin número, el
# archivo va a Pendientes, que es la respuesta honesta. Va DESPUÉS de
# PUBLICATION_DATE_PATTERN: "(2004-08)" es una fecha, no un rango.
# El guion va pegado a propósito (nunca "\s*-\s*"): con espacios alrededor
# se tragaba el separador de subtítulo de "Serie 01 - 2 parte". Y solo se
# quitan las cifras, no los paréntesis que las rodean — quitar "(" sin
# poder quitar su ")" dejaba huérfano el cierre ("La Patrulla X (122-143
# usa)" → "La Patrulla X usa)"). El catch-all de paréntesis de más abajo
# ya se lleva el "( )" que queda.
NUMBER_RANGE_PATTERN = re.compile(r"\b\d{1,4}-\d{1,4}[a-zA-Z]?\b")

# El mismo rango, pero escrito con palabra en vez de guion: "170 al 173",
# "210 a 211". Bug real: sin esto, "Flash v2 210 a 211" se leía como el
# número 210 suelto — afirmando una sola grapa donde el archivo es un
# pack de dos. Va ANTES de la búsqueda de número, igual que el rango con
# guion.
NUMBER_RANGE_WORD_PATTERN = re.compile(r"\b\d{1,4}\s+al?\s+\d{1,4}\b", re.IGNORECASE)

# "1 de 4", "3 de 8": posición dentro de un arco publicado en fascículos
# (Transmetropolitan y similares), nunca el número de grapa. Sin esto no
# causaba daño en los casos ya vistos (el "#01" real se encuentra antes
# por prioridad de patrón), pero un archivo que tuviera SOLO "N de M" sin
# "#" delante lo habría tomado como número — se quita para que eso nunca
# pase, y de paso deja el título más limpio.
ARC_POSITION_PATTERN = re.compile(r"\b\d{1,3}\s+de\s+\d{1,3}\b", re.IGNORECASE)

# "[P1N1]", "[P2N9]": partes + número de un grupo concreto (GunSmith
# Cats/Mukankakuna). Se captura ANTES de la limpieza genérica de
# corchetes (más abajo), que si no se la comería sin dejar rastro.
PART_NUMBER_PATTERN = re.compile(r"\[P(\d+)N(\d+)\]", re.IGNORECASE)

# Ediciones de recopilación ("Omnigold 5", "Integral 01", "Edición
# Integral 01"): el número que traen es el TOMO de la recopilación, no
# necesariamente la grapa #NNN original que cubre — son cosas distintas,
# y afirmar la segunda a partir de la primera sería mentir
# (REQUISITOS_PARSER.md RF-07, 2026-09-25: "mejor Pendientes que un
# número falso").
#
# Decisión revisada (B15, 2026-09-26, con datos): el 25/09 se optó por
# quitar el número SIN capturarlo, dejando el archivo en Pendientes para
# siempre. Medido al día siguiente: eso mandaba a Pendientes TODOS los
# Omnigold/Integral de la biblioteca sin necesidad — el modelo ya tenía
# `Issue.format` (con valores `omnibus`/`trade_paperback`/etc, migración
# 0001) para distinguir "grapa suelta" de "recopilación" sin tocar el
# significado de `issue_number`. Ahora SÍ se captura como issue_number,
# marcando `edition_kind` para que quien cree el Issue (ReviewService, la
# única vía que crea Issues hoy) le ponga el `format` correcto en vez del
# valor por defecto SINGLE_ISSUE — y para que el cálculo de huecos
# (api/series.py) pueda excluirlo de contar como grapa suelta.
EDITION_NUMBER_PATTERN = re.compile(
    r"\b(Omnigold|Integral|Edici[oó]n\s+Integral)\s+(\d{1,3})\b", re.IGNORECASE
)

# Prefijo de ORDEN DE LECTURA al principio del nombre ("069.- Flash v2
# 62", "247.- Wonder Woman v2 214"): numera la colección/orden del
# coleccionista, no la grapa. Sin esto se llevaba el patrón genérico de
# 3 cifras y "Wonder Woman 214" se registraba como el número 247.
#
# El punto es OPCIONAL ("01 - Irredeemable #1", sin punto, es el mismo
# idiom que "069.- Flash..."), y el número admite sufijo de letra
# ("049b.- Hawkworld..."). Sin el punto opcional, "01 - Irredeemable #1"
# se leía entero como serie "01" — el guion sin más se confundía con el
# separador de subtítulo, que se queda con el primer trozo ("01").
SORT_PREFIX_PATTERN = re.compile(r"^\s*\d{1,3}[a-zA-Z]?\s*\.?\s*-\s*")
ANNUAL_PATTERN = re.compile(r"\b(?:Annual|Anual|Especial)\b", re.IGNORECASE)
FILE_EXT_PATTERN = re.compile(r"\.(cbz|cbr|cb7|pdf|epub)$", re.IGNORECASE)


@dataclass
class ParsedComicName:
    series: str = ""
    issue_number: str = ""
    volume: int | None = None
    year: int | None = None
    format: str = ""
    is_annual: bool = False
    extra_info: list[str] = field(default_factory=list)
    original_filename: str = ""
    confidence: float = 0.0
    # B15 (2026-09-26): cuando issue_number viene de un marcador de
    # edición/tomo ("omnigold", "integral", "tomo", "volumen") y no de un
    # "#NNN" o numeración estándar, se deja constancia aquí. None significa
    # grapa estándar (el caso normal). Nunca lo usa el matcher para decidir
    # la serie — solo informa qué `Issue.format` corresponde al confirmar
    # la asignación, y qué no debe contar como grapa suelta en los huecos.
    edition_kind: str | None = None


def _abre_el_titulo(working: str, m: re.Match) -> bool:
    """¿El número encontrado es en realidad el principio del título?

    "100 Balas", "1963", "52": series cuyo nombre EMPIEZA por una cifra.
    Tomarla como número de grapa deja la serie en "Balas" y el número en
    100 — serie equivocada y número equivocado a la vez, el peor de los
    resultados. La señal es que no haya nada de título por delante y sí
    palabras por detrás.
    """
    if working[: m.start(1)].strip():
        return False  # hay título delante: es un número normal
    return bool(re.search(r"[^\W\d_]", working[m.end(1):]))


def _buscar_numero(working: str) -> tuple[re.Match, bool] | None:
    """Primer patrón (por orden de fiabilidad) con una coincidencia que no
    sea el principio del título. Devuelve (coincidencia, cortar_en_numero)."""
    for pattern, cortar_en_numero in ISSUE_PATTERNS:
        for m in re.finditer(pattern, working):
            if not _abre_el_titulo(working, m):
                return m, cortar_en_numero
    return None


def parse_comic_filename(filename: str) -> ParsedComicName:
    """Parsea un nombre de archivo de cómic y extrae metadatos."""
    result = ParsedComicName(original_filename=filename)

    ext_match = FILE_EXT_PATTERN.search(filename)
    if ext_match:
        result.format = ext_match.group(1).lower()
        working = filename[: ext_match.start()]
    else:
        working = filename

    # "_" es un separador de facto en la escena ("Batman_v2_012"), pero \b
    # no lo trata como frontera de palabra (es \w igual que letras/dígitos):
    # sin este reemplazo, "v2"/"012" pegados a "_" nunca matchean \bv(\d+)\b
    # ni \b(\d{3,4})\b. Convertirlo a espacio antes de todo lo demás arregla
    # volumen/número a la vez que la limpieza de puntuación de más abajo.
    working = working.replace("_", " ")

    # Entidad HTML literal en el propio nombre de archivo (no es que el
    # navegador la deje sin decodificar: el fichero en disco se llama así,
    # "&amp;" tal cual). Cosmético pero real — sin esto "Jrgandalf &amp;
    # Tildoras" queda en el título de una serie mal cortada en vez de "&".
    working = working.replace("&amp;", "&")

    # Partes+número de un grupo concreto ("[P1N1]"): se captura ANTES de
    # la limpieza genérica de corchetes de más abajo, que si no se la
    # comería entera sin dejar rastro. RF-12: la parte va a volume, el
    # número de esa parte a issue_number — igual que cualquier otro caso
    # con volumen y número, sin inventar un campo compuesto nuevo.
    part_num_match = PART_NUMBER_PATTERN.search(working)
    if part_num_match:
        parte, numero = part_num_match.groups()
        result.volume = int(parte)
        result.issue_number = numero.lstrip("0") or "0"
        working = PART_NUMBER_PATTERN.sub("", working, count=1)

    # Tags de release entre corchetes ("[CRG]", "[MQ]", "[DI]", "[ML]"):
    # grupo/calidad/procedencia, nunca parte del título. A diferencia del
    # ruido entre paréntesis (NOISE_PATTERNS, más abajo, curado caso a
    # caso), esto es un corte genérico — en la práctica de la escena en
    # español, TODO corchete es metadata de release, nunca título. Debe
    # ir ANTES de extraer número/volumen: si no, un corchete a mitad de
    # cadena ("... [DI] by The Murdock [CRG]") deja basura pegada al
    # título o esconde un número final ("...Integral 01 [CRG]").
    working = re.sub(r"\[[^\]]*\]", "", working)

    # Líneas editoriales de reedición ANTES del nombre real de la serie
    # ("Marvel Gold - La Patrulla-X Original 1.cbr"): al revés que "Serie
    # - Subtítulo" (el split de subtítulo de más abajo se quedaría con
    # "Marvel Gold", no con la serie). Se descarta el prefijo entero y se
    # sigue procesando el resto como si fuera el nombre completo.
    working = IMPRINT_PREFIX_PATTERN.sub("", working, count=1)

    # Orden de lectura del coleccionista, no el número de la grapa. Va
    # ANTES de convertir los puntos en espacios, porque el patrón busca
    # el punto literal de "069.- ".
    working = SORT_PREFIX_PATTERN.sub("", working, count=1)

    working = DOT_SEPARATOR_PATTERN.sub(" ", working)
    working = CREDITS_PATTERN.sub("", working, count=1)

    # Fecha de publicación antes que nada: "(2004-08)" es un año, y si se
    # deja pasar hasta la extracción de número se convierte en una grapa
    # #2004 (ver PUBLICATION_DATE_PATTERN).
    fecha_match = PUBLICATION_DATE_PATTERN.search(working)
    if fecha_match:
        result.year = int(fecha_match.group(1))
        working = PUBLICATION_DATE_PATTERN.sub(" ", working, count=1)

    year_match = YEAR_PATTERN.search(working)
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2099:
            result.year = year

    # Rangos ("144-158", y su forma en palabra "170 al 173"): un pack no
    # tiene UN número. Se quitan antes de extraer el número para no
    # quedarse con el primero del rango. Se registra SI hubo rango
    # (`era_pack`): más abajo decide si el volumen puede sustituir al
    # número que falta, o si eso fabricaría una identidad falsa para un
    # pack (ver ese bloque).
    era_pack = bool(NUMBER_RANGE_PATTERN.search(working) or NUMBER_RANGE_WORD_PATTERN.search(working))
    working = NUMBER_RANGE_PATTERN.sub(" ", working)
    working = NUMBER_RANGE_WORD_PATTERN.sub(" ", working)

    # "1 de 4": posición dentro de un arco en fascículos, nunca el número
    # de grapa — ver docstring de ARC_POSITION_PATTERN.
    working = ARC_POSITION_PATTERN.sub(" ", working)

    # El número de aniversario ("20 aniversario") se quita ANTES de mirar
    # si hay marcador de edición: si no, "Integral 20 aniversario" hace
    # que EDITION_NUMBER_PATTERN capture el 20 de la efeméride como si
    # fuera el tomo de la recopilación.
    working = ANIVERSARIO_PATTERN.sub(" ", working)

    # "Omnigold 5" → captura issue_number="5" + edition_kind="omnigold",
    # y el título se queda solo con "Omnigold" (el número no forma parte
    # del nombre de la serie) — ver docstring de EDITION_NUMBER_PATTERN.
    edicion_match = EDITION_NUMBER_PATTERN.search(working)
    if edicion_match:
        palabra, numero = edicion_match.groups()
        result.issue_number = numero.lstrip("0") or "0"
        result.edition_kind = "omnigold" if palabra.lower() == "omnigold" else "integral"
        working = EDITION_NUMBER_PATTERN.sub(r"\1", working, count=1)

    # El ruido entre paréntesis se quita AQUÍ, antes de buscar el número.
    # Estaba después y tapaba una familia entera de casos: en "JSA 81
    # (2006) (Lightray-DCP)" el 81 no queda al final del nombre, así que
    # ningún patrón lo veía y la serie se quedaba en "JSA 81". El año ya
    # se ha leído más arriba, así que borrar los paréntesis no pierde nada.
    for noise in NOISE_PATTERNS:
        working = re.sub(noise, "", working, flags=re.IGNORECASE)
    # Catch-all: cualquier paréntesis que sobreviva a los patrones curados
    # de arriba es casi siempre metadata de release que no anticipamos
    # ("Batman (New 52) 012" — el reboot no es parte del título de la
    # serie), nunca parte legítima de un título de cómic real.
    working = re.sub(r"\([^)]*\)", "", working)

    if ANNUAL_PATTERN.search(working):
        result.is_annual = True
        # Y se quita del título: "Superman Vol2 Especial 2" es el especial
        # nº 2 de Superman, no una serie llamada "Superman Especial" que
        # no igualaría con nada. La condición de annual queda en el flag.
        working = ANNUAL_PATTERN.sub(" ", working)

    marcador_volumen: str | None = None
    if result.volume is None:
        for pattern, etiqueta in VOLUME_PATTERNS:
            vol_match = re.search(pattern, working, re.IGNORECASE)
            if vol_match:
                result.volume = int(vol_match.group(1))
                marcador_volumen = etiqueta
                working = re.sub(pattern, "", working, flags=re.IGNORECASE)
                break

    # Si "[P{n}N{m}]" o un marcador de edición ya resolvieron el número
    # (RF-12 / Omnigold-Integral), no se vuelve a buscar — el resto del
    # nombre es solo metadata de release que la limpieza de más abajo
    # ya se encarga de quitar.
    encontrado = None if result.issue_number else _buscar_numero(working)
    if encontrado:
        issue_match, cortar_en_numero = encontrado
        raw = issue_match.group(1)
        result.issue_number = str(raw).lstrip("0") or "0"
        # Cortar, no empalmar: empalmar los dos lados pegaba el título al
        # subtítulo cuando el número va en medio ("Astérix (DI) 01 -
        # Astérix el galo" → "Astérix (DI)" + "Astérix el galo"). Si el
        # número iba al principio del nombre, cortar dejaría la serie
        # vacía — solo en ese caso se empalma.
        corte = issue_match.start(1) if cortar_en_numero else issue_match.start()
        cortado = working[:corte]
        working = cortado if cortado.strip() else working[issue_match.end():]
    elif marcador_volumen is not None and result.volume is not None and not era_pack:
        # Ningún otro número en el nombre: el propio tomo/volumen ES el
        # identificador de este archivo (B15, 2026-09-26 — medido: 8/81
        # archivos reales de la muestra oficial perdían el número así,
        # "Nancy in Hell Tomo 1", "En un rayo de sol Vol.1/2" — se
        # guardaba solo en `volume`, y el matcher exige TAMBIÉN un número
        # para no mandar el archivo a Pendientes). Se marca `edition_kind`
        # para que quien cree el Issue (ReviewService) le ponga el
        # `format` correcto en vez de SINGLE_ISSUE por defecto, y para que
        # el cálculo de huecos no lo cuente como grapa suelta.
        #
        # Si en cambio SÍ hay otro número ("Sleeper Vol2 05", "Caballero
        # Luna Vol3 01"), `encontrado` no es None y esta rama no se toca
        # — volume y issue_number quedan separados, como ya funcionaba.
        #
        # `not era_pack` es la guarda que faltaba en el primer intento: en
        # "Superman Vol2 049-051a" el "Vol2" es el volumen DE LA SERIE
        # (Zinco años 90), no el identificador de este archivo — el
        # archivo es un pack de grapas 49-51 sin número único real. Usar
        # el "2" del volumen ahí habría sido fabricar una identidad falsa
        # para tapar el hueco, exactamente lo que este proyecto evita.
        result.issue_number = str(result.volume)
        result.edition_kind = marcador_volumen

    # "Serie - Subtítulo" y "Serie #001 - Título del número": todo lo que
    # sigue a un separador " - " (con espacios a los dos lados, a diferencia
    # de un guion pegado como en "Spider-Man") es el título del propio
    # número, no parte del nombre de la serie.
    # El espacio tras el guion es opcional: la escena escribe tanto
    # "Serie - Subtítulo" como "Serie -Subtítulo" ("La liga de los hombres
    # extraordinarios -La Tempestad"). El espacio DELANTE sí se exige, que
    # es lo que distingue el separador de un guion interno ("Spider-Man").
    working = re.split(r"\s+-\s*", working, maxsplit=1)[0]

    series = working.strip()
    series = re.sub(r"[\.\-_]+", " ", series)
    series = re.sub(r"\s+", " ", series)
    series = re.sub(r"\s*[-\u2013\u2014]\s*$", "", series)
    # La coma y los dos puntos finales sobran igual que el guion: quedan
    # de haber cortado por el n\u00famero ("Patrulla-X, n\u00ba 03" \u2192 "Patrulla X,").
    # El matcher los ignora al normalizar, pero este texto es el que ve el
    # coleccionista en Pendientes y el que aprende el alias local (B13).
    series = series.strip(" -\u2013\u2014(),;:")
    result.series = series
    result.confidence = _confidence(result)
    return result


def normalize_series_name(name: str) -> str:
    """Para comparación fuzzy: sin artículos, sin puntuación, lowercase."""
    name = name.lower()
    name = re.sub(r"^(the|a|an|el|la|los|las|le|les)\s+", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _confidence(p: ParsedComicName) -> float:
    score = 0.0
    if p.series:        score += 0.4
    if p.issue_number:  score += 0.3
    if p.year:          score += 0.15
    if p.format:        score += 0.1
    if p.volume:        score += 0.05
    return min(score, 1.0)
