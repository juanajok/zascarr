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
import unicodedata
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
    (r"c(\d{3,4})\b", False),  # One Piece c1054
    # Astérix T01: BD de tomo único, el tomo ES el número de cara a catalogación (no un volumen
    # de trade paperback americano).
    (r"\bT(\d{2})\b", False),
    # "nº 03", "n° 5", "núm. 7" y su mojibake "n║05" — la numeración
    # española, que no estaba cubierta. El "║" no es un error de copia:
    # media biblioteca real viene de scans con nombres en CP437 releídos
    # como Latin-1 ("Espa±a", "Traducci≤n"), y ahí "º" aparece así.
    # `(?<![A-Za-zÀ-ÿ])`: el marcador NO puede ir pegado a una letra por la izquierda. Sin esto,
    # el "no" final de "Inferno 01" o "La Cosa del Pantano 01" se leía como «nº 01» y el título se
    # truncaba ("Infer", "La Cosa del Panta"). Medido en la biblioteca real: 14 de 1.542 nombres.
    (
        r"(?<![A-Za-zÀ-ÿ])(?:Issue|No\.?|N[úu]m(?:ero)?\.?|[Nn][ºo°º║])\s*(\d{1,4}[a-zA-Z]?)\b",
        False,
    ),
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
    r"\b(?P<numero>\d+|[IVXL]+)\s*(?:º|ª|°|o|mo|er|to)?\s*aniversario\b",
    re.IGNORECASE,
)


def _quitar_numero_de_aniversario(texto: str) -> str:
    """Quita «20 aniversario» sin comerse un número de grapa explícito.

    Bug real de la biblioteca (2026-11-11): «Batman #400 Aniversario» se
    quedaba sin número porque el patrón borraba «400 Aniversario» entero. Si
    delante del número hay un marcador de grapa (#, nº, num.), el número es
    del cómic; solo se quita la palabra «aniversario». En «Iberia Inc. -
    Integral 20 aniversario» no hay marcador y se quita la efeméride completa,
    que es lo que se pretendía.
    """
    def _repl(match: re.Match[str]) -> str:
        antes = texto[max(0, match.start() - 8):match.start()]
        if re.search(r"(?:#|№|\bn[ºo]|\bnum(?:ero)?\.?)\s*$", antes, re.IGNORECASE):
            return match.group("numero") + " "
        return " "

    return ANIVERSARIO_PATTERN.sub(_repl, texto)

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

# «#25 - Anual»: no es el anual nº25, es un pack con el issue #25 y el anual.
# «Batman Annual #25» (marca delante) sí es un anual normal y no entra aquí.
PACK_ISSUE_ANNUAL_PATTERN = re.compile(
    r"#\s*\d{1,4}[a-zA-Z]?\s*-\s*(?:Annual|Anual)\b", re.IGNORECASE)

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

# Formatos de edición que NO son una grapa. Se capturan antes de buscar el
# número: «Batman Omnibus Vol 1» debe conservar el formato y no convertirse
# en una grapa #1 sin más. La etiqueta se mapea a IssueFormat en models.
EDITION_FORMAT_NUMBER_PATTERN = re.compile(
    r"\b(?P<formato>Omnibus|TPB|Trade\s+Paperback|Hardcover|HC|Graphic\s+Novel|GN)"
    r"\s+(?P<numero>\d{1,3})\b",
    re.IGNORECASE,
)
EDITION_FORMAT_PATTERN = re.compile(
    r"\b(?:Omnibus|TPB|Trade\s+Paperback|Hardcover|HC|Graphic\s+Novel|GN)\b",
    re.IGNORECASE,
)
EDITION_FORMAT_KIND = {
    "omnibus": "omnibus",
    "tpb": "trade_paperback",
    "trade paperback": "trade_paperback",
    "hardcover": "hardcover",
    "hc": "hardcover",
    "graphic novel": "graphic_novel",
    "gn": "graphic_novel",
}
# «1 of 4» / «1 de 4»: cuenta de la miniserie. El número de issue, si lo hay,
# lo sigue extrayendo el buscador normal; esto solo guarda el total.
ISSUE_COUNT_PATTERN = re.compile(r"\b(\d{1,3})\s+(?:of|de)\s+(\d{1,3})\b", re.IGNORECASE)

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

# «Crossover 07 - Dinastía de X 04»: el 07 es orden de lectura del evento;
# la serie y el número reales van después. No se aplica a un título que
# simplemente empiece por «Crossover».
CROSSOVER_PREFIX_PATTERN = re.compile(r"^\s*Crossover\s+\d{1,3}\s*-\s*", re.IGNORECASE)

# Prefijo numérico sin guion: "13. Nightwing #73", "14  JLD #11", "16 Catwoman".
# Si detrás hay otro número/marcador, el prefijo es orden de lectura; si no,
# el prefijo ES el número y el resto es la serie ("51 Catwoman").
LEADING_NUMBER_PREFIX_PATTERN = re.compile(
    r"^\s*(?P<num>\d{1,3}(?:\.\d+)?)(?P<suf>[a-zA-Z]?)(?P<sep>[\.\)]\s*|\s+)"
    r"(?P<rest>[^\W\d_].*)$",
    re.UNICODE,
)
# Annual/Anual y Especial NO son la misma cosa. Un anual es una publicación
# con numeración propia dentro de la colección (Metron, GCD y Comic Vine lo
# publican como serie/volumen propio); «Especial» es una marca de edición que,
# por ahora, sigue colgando de la serie madre. Mezclarlos fue lo que convirtió
# «Batman Annual 01» en el nº 1 de «Batman».
ANNUAL_PATTERN = re.compile(r"\b(?:Annual|Anual)\b", re.IGNORECASE)
# El número del anual va inmediatamente detrás de la marca. Si se deja al
# buscador genérico, un año suelto del nombre ("Shadow_..._Annual_01_..._1993")
# gana por ser de 4 cifras y el anual acaba con el número 1993. Se prueba
# antes que `_buscar_numero`, solo cuando el nombre ya se marcó como anual.
ANNUAL_NUMBER_PATTERN = re.compile(
    r"\b(?:Annual|Anual)\b\s*#?\s*(\d{1,4}[a-zA-Z]?)\b", re.IGNORECASE
)
SPECIAL_PATTERN = re.compile(r"\bEspecial\b", re.IGNORECASE)
FILE_EXT_PATTERN = re.compile(r"\.(cbz|cbr|cb7|pdf|epub)$", re.IGNORECASE)


@dataclass
class ParsedComicName:
    series: str = ""
    issue_number: str = ""
    volume: int | None = None
    year: int | None = None
    #: Total de la miniserie si el nombre lo dice («1 of 4», «1 de 4»).
    #: Es contexto para validar, no el número del archivo.
    issue_count: int | None = None
    format: str = ""
    #: `Annual`/`Anual`: publicación con numeración propia; el título conserva
    #: la palabra porque «Batman Annual» es la serie que hay que buscar.
    is_annual: bool = False
    #: `Especial`: marca de edición que hoy sigue colgando de la serie madre.
    is_special: bool = False
    extra_info: list[str] = field(default_factory=list)
    #: Parte que se descartaba como «título del número» cuando iba ANTES del número
    #: ("Superman - Godfall #01"). Sirve para no confundir colecciones distintas;
    #: vacío si el subtítulo iba después del número ("Superman #01 - El origen").
    subtitulo: str = ""
    #: Serie completa antes de partir por " - " ("Green Lantern - Origenes
    #: Secretos"). El matcher la prueba como alternativa si la serie corta no
    #: encuentra candidato; no sustituye a `series` ni crea identidad sola.
    series_alternativa: str = ""
    original_filename: str = ""
    confidence: float = 0.0
    # B15 (2026-09-26): cuando issue_number viene de un marcador de
    # edición/tomo ("omnigold", "integral", "tomo", "volumen") y no de un
    # "#NNN" o numeración estándar, se deja constancia aquí. None significa
    # grapa estándar (el caso normal). Nunca lo usa el matcher para decidir
    # la serie — solo informa qué `Issue.format` corresponde al confirmar
    # la asignación, y qué no debe contar como grapa suelta en los huecos.
    edition_kind: str | None = None


def _separar_prefijo_numerico(working: str) -> tuple[str, str | None]:
    """Separa un prefijo numérico inicial de serie/número.

    Devuelve (texto_sin_prefijo, numero). Si el prefijo es orden de lectura
    (hay otro número detrás, o va con punto/paréntesis) devuelve numero=None
    y solo lo quita; si no, el prefijo es el número del tebeo y el resto es
    la serie. Los títulos que empiezan por cifra ("100 Balas", "1963", "52")
    no entran: el prefijo de 3 cifras se deja intacto.
    """
    m = LEADING_NUMBER_PREFIX_PATTERN.match(working)
    if not m:
        return working, None
    num = m.group("num")
    if len(num.split(".")[0]) > 2:
        return working, None
    resto = m.group("rest").strip()
    sep = m.group("sep")
    if not resto:
        return working, None
    if "." in num:
        # "22.1 Catwoman": decimal explícito, es el número del tebeo.
        return resto, num.lstrip("0") or "0"
    if sep.strip() in (".", ")"):
        # "13. Nightwing": prefijo de orden de lectura, no de grapa.
        return resto, None
    if re.search(r"#\s*\d", resto) or re.search(r"(?<!New )\b\d{1,3}\b", resto):
        # "14 JLD #11" / "73 Dreadstar ... 61": hay otro número en el resto.
        return resto, None
    # Prefijo suelto sin más evidencia: no se inventa si es número o parte del
    # título ("12 Monkeys"). Se deja como estaba.
    return working, None


def _serie_desde_carpeta(series: str, alternativa: str, carpeta: str | None) -> str:
    """Ajusta la serie usando la carpeta padre, sin inventar.

    - Si la carpeta (limpia de volumen/año) coincide con la alternativa del
      nombre partido, se prefiere la alternativa.
    - Si la carpeta empieza por la serie y añade una palabra editorial
      («Joe Kubert» + «Presents»), se prefiere la carpeta.
    """
    if not carpeta:
        return series
    limpia = re.sub(r"\b(?:vol(?:umen)?\.?\s*\d+|v\s*\d+)\b", " ", carpeta, flags=re.IGNORECASE)
    limpia = re.sub(r"\b(?:19|20)\d{2}\b", " ", limpia)
    limpia = _limpiar_titulo_serie(limpia)
    limpia_norm = normalize_series_name(limpia)
    if not limpia_norm:
        return series
    alternativa_norm = normalize_series_name(alternativa)
    if alternativa_norm and alternativa_norm == limpia_norm:
        return alternativa
    # Solo una extensión editorial explícita («Joe Kubert» + «Presents»).
    series_norm = normalize_series_name(series)
    if series_norm and limpia_norm == series_norm + " presents":
        return limpia
    return series


def _quitar_credito_con_carpeta(working: str, carpeta: str | None) -> str:
    """Quita «Hiroaki Samura - » cuando el resto coincide con la carpeta.

    Solo actúa con un separador « - », un prefijo que parece crédito (varias
    palabras o «&») y una carpeta que contiene el título restante. Nunca
    convierte una serie de una palabra en subtítulo.
    """
    if not carpeta or " - " not in working:
        return working
    m = re.match(r"^(.+?)\s+-\s+(.+)$", working)
    if not m:
        return working
    credito, resto = m.group(1).strip(), m.group(2).strip()
    parece_credito = (
        "&" in credito
        or bool(re.match(r"^[A-ZÁÉÍÓÚÑ][\wÀ-ÿ.'-]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÀ-ÿ.'-]+)+$", credito))
    )
    if not parece_credito:
        return working
    sin_numero = re.sub(r"\s+\d{1,4}[a-zA-Z]?\s*$", "", resto).strip()
    if not sin_numero:
        return working
    resto_norm = normalize_series_name(sin_numero)
    carpeta_norm = normalize_series_name(carpeta)
    if resto_norm and (resto_norm in carpeta_norm or carpeta_norm in resto_norm):
        return resto
    if "&" in credito:
        return resto
    return working


def _prefijo_de_issue_con_carpeta(working: str, carpeta: str | None) -> tuple[str, str | None]:
    """«16 Catwoman» + carpeta Catwoman → issue 16, serie Catwoman.

    Solo si el resto coincide con la carpeta y la carpeta no empieza por ese
    mismo número (para no romper series como «12 Monkeys»).
    """
    if not carpeta:
        return working, None
    m = re.match(r"^\s*(\d{1,3})\s+([^\W\d_].*)$", working, re.UNICODE)
    if not m:
        return working, None
    numero, resto = m.group(1), m.group(2).strip()
    if len(numero) > 2:
        return working, None
    resto_limpio = re.sub(r"\([^)]*\)", " ", resto).strip()
    resto_norm = normalize_series_name(resto_limpio)
    carpeta_norm = normalize_series_name(carpeta)
    if not resto_norm or resto_norm not in carpeta_norm:
        return working, None
    if carpeta_norm.startswith(numero + " "):
        return working, None
    return resto, numero.lstrip("0") or "0"


YEAR_IN_TITLE_NUMBER_PATTERN = re.compile(
    r"^\s*(?P<title>.+?)\s+(?P<year>(?:19|20)\d{2})\s+"
    r"(?P<num>\d{1,3}[a-zA-Z]?)\s*$",
    re.IGNORECASE,
)


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


def _limpiar_titulo_serie(texto: str) -> str:
    """Limpieza final del título: separadores, sufijos de edición y bordes."""
    series = texto.strip()
    series = re.sub(r"[\.\-_]+", " ", series)
    series = re.sub(r"\s+", " ", series)
    series = re.sub(r"\s*[-\u2013\u2014]\s*$", "", series)
    # Sufijo de edición que no forma parte del título de la serie.
    series = re.sub(r"\s+The\s+New\s+52!?$", "", series, flags=re.IGNORECASE)
    # La coma y los dos puntos finales sobran igual que el guion: quedan
    # de haber cortado por el número ("Patrulla-X, nº 03" → "Patrulla X,").
    return series.strip(" -\u2013\u2014(),;:#")


def parse_comic_filename(filename: str, carpeta: str | None = None) -> ParsedComicName:
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
    working = CROSSOVER_PREFIX_PATTERN.sub("", working, count=1)

    working, numero_de_prefijo = _prefijo_de_issue_con_carpeta(working, carpeta)
    if numero_de_prefijo is None:
        working, numero_de_prefijo = _separar_prefijo_numerico(working)
    if numero_de_prefijo is not None:
        result.issue_number = numero_de_prefijo

    working = DOT_SEPARATOR_PATTERN.sub(" ", working)
    working = CREDITS_PATTERN.sub("", working, count=1)
    working = _quitar_credito_con_carpeta(working, carpeta)

    # Formato de edición: Omnibus/TPB/HC/GN. Primero la variante con número
    # inmediato («Omnibus 1»), que además resuelve el número; si no, solo se
    # marca el formato y se quita la palabra del título.
    formato_con_numero = EDITION_FORMAT_NUMBER_PATTERN.search(working)
    if formato_con_numero:
        etiqueta = re.sub(r"\s+", " ", formato_con_numero.group("formato").lower())
        result.edition_kind = EDITION_FORMAT_KIND.get(etiqueta, etiqueta)
        result.issue_number = formato_con_numero.group("numero").lstrip("0") or "0"
        working = EDITION_FORMAT_NUMBER_PATTERN.sub(" ", working, count=1)
    else:
        formato = EDITION_FORMAT_PATTERN.search(working)
        if formato:
            etiqueta = re.sub(r"\s+", " ", formato.group(0).lower())
            result.edition_kind = EDITION_FORMAT_KIND.get(etiqueta, etiqueta)
            working = EDITION_FORMAT_PATTERN.sub(" ", working, count=1)

    # Cuenta de la miniserie («1 of 4»): contexto, no identidad. Se mide antes
    # de que el patrón de posición de arco quite «N de M».
    cuenta = ISSUE_COUNT_PATTERN.search(working)
    if cuenta:
        result.issue_count = int(cuenta.group(2))

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

    # «American Vampire 1976 10»: el año forma parte del título de la serie,
    # no es el número. Solo si queda un número corto al final.
    anio_titulo = YEAR_IN_TITLE_NUMBER_PATTERN.match(working)
    if anio_titulo and not result.issue_number:
        result.issue_number = anio_titulo.group("num").lstrip("0") or "0"
        working = f"{anio_titulo.group('title')} {anio_titulo.group('year')}"

    # Rangos ("144-158", y su forma en palabra "170 al 173"): un pack no
    # tiene UN número. Se quitan antes de extraer el número para no
    # quedarse con el primero del rango. Se registra SI hubo rango
    # (`era_pack`): más abajo decide si el volumen puede sustituir al
    # número que falta, o si eso fabricaría una identidad falsa para un
    # pack (ver ese bloque).
    era_pack = bool(
        NUMBER_RANGE_PATTERN.search(working)
        or NUMBER_RANGE_WORD_PATTERN.search(working)
        or PACK_ISSUE_ANNUAL_PATTERN.search(working)
    )
    working = NUMBER_RANGE_PATTERN.sub(" ", working)
    working = NUMBER_RANGE_WORD_PATTERN.sub(" ", working)

    # "1 de 4": posición dentro de un arco en fascículos, nunca el número
    # de grapa — ver docstring de ARC_POSITION_PATTERN.
    working = ARC_POSITION_PATTERN.sub(" ", working)

    # El número de aniversario ("20 aniversario") se quita ANTES de mirar
    # si hay marcador de edición: si no, "Integral 20 aniversario" hace
    # que EDITION_NUMBER_PATTERN capture el 20 de la efeméride como si
    # fuera el tomo de la recopilación.
    working = _quitar_numero_de_aniversario(working)

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
        # NO se quita del título. «Batman Annual 01» es el nº 1 de la serie
        # «Batman Annual», no el nº 1 de «Batman»: la palabra forma parte del
        # título que el matcher tiene que buscar. Que sea anual lo dice el
        # flag y, más adelante, la clasificación de la serie (no el número).
        # Cambiar esto sin el flag haría que la serie anual no se encontrara
        # nunca y el archivo volviera a caer en la madre.

    if SPECIAL_PATTERN.search(working):
        result.is_special = True
        # «Superman Vol2 Especial 2» sigue siendo el especial nº 2 de
        # Superman, no una serie llamada «Superman Especial». Hasta que la
        # clasificación de series separe los especiales, se mantiene el
        # comportamiento histórico: la marca se quita del título.
        working = SPECIAL_PATTERN.sub(" ", working)

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
    encontrado = None
    if not result.issue_number:
        # Un pack del tipo «#647-650 y anual 25» no debe quedarse con el 25:
        # el rango ya dice que no hay una grapa única. Pero un pack que
        # además identifica una edición («(122-143) Omnigold nº 2») sí puede
        # llevar su número de tomo; por eso el bloqueo es solo para el anual.
        if result.is_annual and not era_pack:
            annual_match = ANNUAL_NUMBER_PATTERN.search(working)
            if annual_match:
                encontrado = (annual_match, True)
        if encontrado is None and not (result.is_annual and era_pack):
            encontrado = _buscar_numero(working)
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
    if (not result.issue_number and marcador_volumen is not None
            and result.volume is not None and not era_pack):
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
        if result.edition_kind is None:
            result.edition_kind = marcador_volumen

    # "Serie - Subtítulo" y "Serie #001 - Título del número": todo lo que
    # sigue a un separador " - " (con espacios a los dos lados, a diferencia
    # de un guion pegado como en "Spider-Man") es el título del propio
    # número, no parte del nombre de la serie.
    # El espacio tras el guion es opcional: la escena escribe tanto
    # "Serie - Subtítulo" como "Serie -Subtítulo" ("La liga de los hombres
    # extraordinarios -La Tempestad"). El espacio DELANTE sí se exige, que
    # es lo que distingue el separador de un guion interno ("Spider-Man").
    serie_completa = working
    partes_subtitulo = re.split(r"\s+-\s*", working, maxsplit=1)
    working = partes_subtitulo[0]
    if len(partes_subtitulo) > 1:
        result.subtitulo = partes_subtitulo[1].strip()

    series = _limpiar_titulo_serie(working)
    if len(partes_subtitulo) > 1:
        alternativa = _limpiar_titulo_serie(serie_completa)
        if alternativa and alternativa != series:
            result.series_alternativa = alternativa
    series = _serie_desde_carpeta(series, result.series_alternativa, carpeta)
    result.series = series
    result.confidence = _confidence(result)
    return result


def normalize_series_name(name: str) -> str:
    """Para comparación: **sin acentos**, sin artículo inicial, sin puntuación,
    lowercase.

    El **plegado de acentos es simétrico** (se aplica al mismo tiempo a los dos
    extremos de la comparación) y es lo que arregla el falso negativo hispano: un
    release sin tildes («Asterix», «Filemon», «Dona Urraca») tiene que encontrar
    el título del catálogo («Astérix», «Filemón», «Doña Urraca»). **Precio
    aceptado:** plegar `ñ` a `n` une palabras distintas («año»/«ano»).

    **Artículo:** solo se quita el **inicial** (`the|a|an|el|la|los|las|le|les`),
    que es el comportamiento de siempre — «Batman» y «The Batman» ya colapsaban
    aquí, y sigue siendo la decisión. NO se quita el pospuesto («Sandman, The»)
    ni se amplía la lista (`die/der/das/il/lo`): eso es cosa de
    `core.matcher.normalize_title`, y traerlo aquí ampliaría el alcance del filtro
    de D8 sin una necesidad medida.

    Los dos normalizadores siguen existiendo a propósito: este compara títulos de
    release (fuzzy, para puntuar), y `normalize_title` compara contra el catálogo
    (con artículos pospuestos y abreviaciones). Lo que **no** puede pasar es que
    la mitad del filtro de D8 use uno y la otra mitad el otro.

    **Límite conocido, fuera del alfabeto latino:** `unicodedata.combining` no
    distingue un diacrítico latino de una marca de kana, así que el dakuten y el
    handakuten también se caen: `が` y `か` (o `ガ` y `カ`) normalizan igual. Los
    releases que maneja el proyecto son casi siempre latinos, así que se acepta y
    se documenta (hay prueba) en vez de complicar el plegado.
    """
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"^(the|a|an|el|la|los|las|le|les)\s+", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _confidence(p: ParsedComicName) -> float:
    score = 0.0
    if p.series:
        score += 0.4
    if p.issue_number:
        score += 0.3
    if p.year:
        score += 0.15
    if p.format:
        score += 0.1
    if p.volume:
        score += 0.05
    return min(score, 1.0)


#: Marcas de edición/formato que no distinguen una colección de otra.
_MARCAS_DE_EDICION = re.compile(
    r"\b(?:vol(?:umen)?|tomo|integral|omnigold|deluxe|edicion|especial|annual|anual|extra|"
    r"variant|variante|coleccion|serie)\b\.?\s*\d*",
    re.IGNORECASE,
)


def clave_de_coleccion(nombre: str) -> str:
    """La parte del nombre que identifica la COLECCIÓN, sin número ni marcas de edición.

    "Superman - Godfall #01" -> "superman godfall"; "Superman #01" -> "superman";
    "Superman Vol2 001 [SC]" -> "superman". Dos archivos de la misma colección
    (CBR/CBZ, copia) comparten clave; dos tebeos distintos con el mismo número,
    no. Vacío si no se puede afirmar nada: quien la use no debe bloquear por ello.
    """
    parsed = parse_comic_filename(nombre)
    base = " ".join(parte for parte in (parsed.series, parsed.subtitulo) if parte)
    base = normalize_series_name(base)
    base = _MARCAS_DE_EDICION.sub(" ", base)
    base = re.sub(r"\b\d+\b", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    if parsed.is_annual:
        base = (base + " anual").strip()
    if parsed.is_special:
        base = (base + " especial").strip()
    return base


def es_titulo_de_anual(titulo: str) -> bool:
    """¿El título de una serie es una línea anual («Batman Annual»)?

    Es una heurística de TÍTULO, no una identidad: mientras no exista la
    clasificación explícita de series (fase 1), el matcher la usa para no
    aceptar la serie madre como candidata de un archivo anual. Una serie que
    se llame «Annual» sin serlo se resolverá a mano; nunca se autoasigna.
    """
    return bool(ANNUAL_PATTERN.search(titulo or ""))
