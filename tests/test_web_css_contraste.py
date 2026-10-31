"""
tests/test_web_css_contraste.py

V1 (Épica V): `web.css` es legible en AMBOS temas. Sin navegador: se lee la hoja, se resuelven las
variables (`var(--x)`, `#hex`, `color-mix(in srgb, …)`) y se calcula la razón de contraste WCAG 2.x
de cada par texto/fondo que la propia hoja declara.

Umbrales (WCAG 2.2, criterio 1.4.3 y 1.4.11):
  · texto normal ......................... ≥ 4,5 : 1  (se aplica a TODO el texto: es más estricto
                                                       que el 3:1 del texto grande, a propósito)
  · foco, bordes de controles, iconos .... ≥ 3 : 1
  · tamaño mínimo de texto informativo ... 14 px (decisión de producto, no de WCAG); un `clamp` cuenta
                                            por su mínimo y las excepciones van declaradas con su motivo
                                            (`EXCEPCIONES_DE_TAMANO`)
  · objetivo táctil de controles ......... 40 px; casillas y radios 24 px

ALCANCE (qué garantiza esta prueba y qué no):
  · Es una HEURÍSTICA POR REGLAS: toma cada regla de la hoja que fija `color` (con su `background`
    o `--btn-bg` si los tiene) y, si no tiene fondo propio, lo contrasta con los fondos de contexto
    de `FONDOS_DE_CONTEXTO`. NO resuelve la cascada ni los colores heredados del DOM, ni sabe sobre
    qué fondo cae realmente cada elemento.
  · Comprueba los pares que la hoja DECLARA; no certifica el contraste real renderizado (tramas,
    sombras, imágenes) ni el color de texto que fije una plantilla en línea (hoy ninguna lo hace;
    ver `test_las_plantillas_no_fijan_colores`). Se complementa con la verificación en navegador.
  · NADA SE OMITE EN SILENCIO: un color o un fondo que el resolvedor no entiende (`hsl()`,
    `oklch()`, `rgba()`, degradados con texto…) HACE FALLAR la prueba, salvo que esté en
    `EXCLUSIONES` con su motivo. Esa lista está vacía a propósito.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CSS_RUTA = RAIZ / "src" / "zascarr" / "static" / "web.css"
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"

TEXTO = 4.5
NO_TEXTO = 3.0


# ── lectura de la hoja ────────────────────────────────────────────────────────────────────
def _hoja(css: str | None = None) -> str:
    texto = CSS_RUTA.read_text(encoding="utf-8") if css is None else css
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _variables(bloque: str) -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", bloque)}


def _temas() -> dict[str, dict[str, str]]:
    css = _hoja()
    raiz = _variables(re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1))
    oscuro = re.search(
        r"@media \(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\n  \}", css, re.S)
    assert oscuro, "no encuentro el bloque :root del tema oscuro"
    return {"claro": raiz, "oscuro": {**raiz, **_variables(oscuro.group(1))}}


def _reglas(css: str | None = None) -> list[tuple[str, dict[str, str]]]:
    """(selector, declaraciones) de cada regla, incluidas las de @media."""
    salida = []
    for selector, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", _hoja(css)):
        decl = {k.strip(): v.strip() for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+);?", cuerpo)}
        salida.append((" ".join(selector.split()), decl))
    return salida


# ── tamaño mínimo del texto ───────────────────────────────────────────────────────────────
MINIMO_PX = 14.0

#: Excepciones DECLARADAS al mínimo de 14 px: selector → (mínimo en px que se tolera, motivo).
#: Una excepción vale solo mientras el selector siga bajando de 14 px y no baje de lo declarado;
#: si deja de bajar, la prueba falla (excepción obsoleta) para que no se pudra.
EXCEPCIONES_DE_TAMANO: dict[str, tuple[float, str]] = {
    ".nav-enlace": (
        12.0,
        "U16: que «Deseados» quepa a 320 px en la barra inferior del móvil. Medido con la fuente real "
        "(Archivo 600, Chromium): ocupa 56,1 px a 12 px, 60,8 a 13 y 65,5 a 14; la columna a 320 px "
        "mide 64 px y con el padding quedan 62, así que a 14 px no cabe. clamp(.75rem, 3.3vw, "
        ".875rem) da 12 px a 320-360, 12,9 a 390, 13,7 a 414 y 14 desde 424 px: la etiqueta mide "
        "menos de 14 px en cualquier pantalla de menos de 424 px. No se acorta «Deseados»."),
}

#: `font-size` con `var(...)` o `inherit`: no se puede saber su valor leyendo la hoja, así que FALLAN
#: salvo que el selector esté aquí con su motivo. Vacía a propósito (hoy ninguna regla los usa).
TAMANOS_NO_COMPROBABLES: dict[str, str] = {}

#: `font-size` proporcional a su contenedor (`cqw`): sin mínimo en px que leer; cada uno con su motivo.
TAMANOS_PROPORCIONALES: dict[str, str] = {
    ".portada-marca": "la inicial decorativa y aria-hidden de ui.portada: 46 % del ancho de su tarjeta, "
                      "≥ 37 px incluso en la más pequeña (80 px de ancho); el título va en texto debajo",
}


def minimo_px(valor: str) -> float | None:
    """Tamaño mínimo en px de un `font-size` (un `clamp` cuenta por su primer argumento).

    Devuelve None si el valor es relativo (`em`), y LANZA ValueError si no se puede leer: nada se omite."""
    v = " ".join(valor.split())
    if v.startswith("clamp("):
        m = re.fullmatch(r"clamp\(\s*([\d.]+)(rem|px)\s*,\s*[^,()]+,\s*([\d.]+)(rem|px)\s*\)", v)
        if not m:
            raise ValueError(f"clamp no reconocido: {valor!r}")
        v = m.group(1) + m.group(2)
    m = re.fullmatch(r"([\d.]+)(rem|em|px)", v)
    if not m:
        raise ValueError(f"font-size no reconocido: {valor!r}")
    n, u = float(m.group(1)), m.group(2)
    return n * 16 if u == "rem" else n if u == "px" else None


def problemas_de_tamano(reglas, excepciones=None, no_comprobables=None, proporcionales=None) -> list[str]:
    """Todo lo que incumple el mínimo de 14 px. Vacía = bien. No omite nada en silencio."""
    excepciones = EXCEPCIONES_DE_TAMANO if excepciones is None else excepciones
    no_comprobables = TAMANOS_NO_COMPROBABLES if no_comprobables is None else no_comprobables
    proporcionales = TAMANOS_PROPORCIONALES if proporcionales is None else proporcionales
    problemas, usadas = [], set()
    for selector, motivo in {**excepciones_motivos(excepciones), **no_comprobables, **proporcionales}.items():
        if not motivo.strip():
            problemas.append(f"{selector}: una excepción necesita motivo")
    for selector, d in reglas:
        v = d.get("font-size")
        if not v:
            continue
        if v.endswith("cqw"):
            if selector not in proporcionales:
                problemas.append(f"{selector}: font-size {v!r} proporcional sin declarar")
            continue
        if v.startswith(("var(", "inherit")):
            if selector not in no_comprobables:
                problemas.append(f"{selector}: font-size {v!r} no se puede comprobar leyendo la hoja")
            continue
        try:
            px = minimo_px(v)
        except ValueError as e:
            problemas.append(f"{selector}: {e}")
            continue
        if px is None:                       # `em`: relativo al elemento padre
            if float(v.removesuffix("em")) < 1:
                problemas.append(f"{selector}: {v} (em < 1)")
            continue
        if px >= MINIMO_PX:
            continue
        if selector not in excepciones:
            problemas.append(f"{selector}: {v} baja de {MINIMO_PX:g} px ({px:g} px)")
            continue
        usadas.add(selector)
        if px < excepciones[selector][0]:
            problemas.append(f"{selector}: {v} baja de lo declarado en su excepción "
                             f"({px:g} < {excepciones[selector][0]:g} px)")
    for selector in excepciones:
        if selector not in usadas:
            problemas.append(f"{selector}: excepción obsoleta (ya no baja de {MINIMO_PX:g} px)")
    return problemas


def excepciones_motivos(excepciones) -> dict[str, str]:
    return {selector: motivo for selector, (_minimo, motivo) in excepciones.items()}


# ── color ─────────────────────────────────────────────────────────────────────────────────
def _rgb(hexa: str) -> tuple[float, float, float]:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in rgb)


def _partir(texto: str) -> list[str]:
    """Separa por comas del nivel superior (las de var() y color-mix() quedan dentro)."""
    partes, nivel, actual = [], 0, ""
    for c in texto:
        nivel += c == "("
        nivel -= c == ")"
        if c == "," and nivel == 0:
            partes.append(actual)
            actual = ""
        else:
            actual += c
    partes.append(actual)
    return [p.strip() for p in partes]


def resolver(expr: str, tema: dict[str, str]) -> str | None:
    """Devuelve '#rrggbb' o None si la expresión no es un color sólido resoluble."""
    expr = expr.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", expr):
        return _hex(_rgb(expr))
    m = re.fullmatch(r"var\((--[\w-]+)(?:,.*)?\)", expr)
    if m:
        return resolver(tema[m.group(1)], tema) if m.group(1) in tema else None
    m = re.fullmatch(r"color-mix\(in srgb,(.*)\)", expr, re.S)
    if m:
        (a, pa), (b, pb) = [
            (p.rsplit(" ", 1)[0], p.rsplit(" ", 1)[1]) if p.endswith("%") else (p, None)
            for p in _partir(m.group(1))]
        ca, cb = resolver(a, tema), resolver(b, tema)
        if not ca or not cb:
            return None
        peso = float(pa[:-1]) / 100 if pa else 1 - float(pb[:-1]) / 100
        mezcla = zip(_rgb(ca), _rgb(cb), strict=True)
        return _hex(tuple(x * peso + y * (1 - peso) for x, y in mezcla))
    return None


def _luminancia(hexa: str) -> float:
    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in _rgb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ── fondos sobre los que puede caer texto «sin fondo propio» ─────────────────────────────
FONDOS_DE_CONTEXTO = [
    "var(--paper)", "var(--paper-2)", "var(--caption-bg)",
    "color-mix(in srgb, var(--ok) 12%, var(--paper))",     # .suggestion, .audit-ok
    "color-mix(in srgb, var(--cyan) 14%, var(--paper))",   # .legal-notice-info
]
FG_BASE_DEL_BOTON = "var(--ink)"   # `button { color: var(--ink) }`; --btn-bg solo cambia el fondo


# Selectores de elementos que NO llevan texto (indicadores y rellenos de barra): su fondo se prueba
# como no texto (3:1 por el borde de tinta), no con la regla de 4,5:1 del texto heredado.
SIN_TEXTO = ("dot", "progress-value", "progress-bar")

# Pares que el resolvedor no debe tener que entender y que se excluyen A PROPÓSITO:
# {(selector, fg, bg): motivo}. Vacío: cada entrada nueva exige su justificación.
EXCLUSIONES: dict[tuple[str, str, str], str] = {
    # La inicial de la portada que falta (ui.portada): una letra de ~46 % del ancho de la tarjeta (≥ 37 px
    # incluso en la más pequeña), decorativa y aria-hidden (el título va en texto debajo). Es texto
    # grande: le vale 3:1, y el caso peor, magenta en claro, mide 3,68:1
    # (test_portada_marca.py::TestContrasteDeLaInicial lo comprueba en las tres tintas y los dos temas).
    (".portada-m", "var(--on-yellow)", "var(--magenta)"):
        "inicial decorativa y enorme de la portada que falta (texto grande, 3:1; 3,68:1 medido)",
}


def _pares_de_la_hoja(css: str | None = None) -> list[tuple[str, str, str, str, str]]:
    """(tema, selector, fg, bg, origen) de todos los pares que la hoja determina.

    Un fondo que no es un color resoluble NO se sustituye por el contexto: se devuelve tal cual para
    que `comprobar_pares` lo marque como «sin resolver» (solo `none`/`transparent` significan «sin
    fondo propio»)."""
    pares = []
    for nombre in _temas():
        for selector, d in _reglas(css):
            fg = d.get("color")
            bg = d.get("background") or d.get("background-color")
            if bg in ("none", "transparent"):
                bg = None
            btn = d.get("--btn-bg")
            if btn in ("none", "transparent"):
                # Botón «fantasma»: sin relleno propio, el texto cae sobre el contexto.
                for f in FONDOS_DE_CONTEXTO:
                    pares.append(
                        (nombre, selector, fg or FG_BASE_DEL_BOTON, f, "--btn-bg sin relleno"))
                continue
            if btn:
                pares.append((nombre, selector, fg or FG_BASE_DEL_BOTON, btn, "--btn-bg"))
                continue
            if fg and fg not in ("inherit", "currentColor"):
                fondos = [bg] if bg else FONDOS_DE_CONTEXTO
                for f in fondos:
                    pares.append((nombre, selector, fg, f, "propio" if bg else "contexto"))
            elif (bg and not fg and not any(x in selector for x in SIN_TEXTO)
                  and "gradient" not in bg and "url(" not in bg):
                # Elemento con fondo y sin color propio: el texto hereda --ink. (Los «puntos»
                # de estado no llevan texto: se prueban como indicador no textual, abajo; un
                # fondo decorativo sin texto, como una trama, no tiene par que medir.)
                pares.append((nombre, selector, "var(--ink)", bg, "texto heredado"))
    return pares


def comprobar_pares(pares, temas) -> None:
    """Falla si un par no llega a 4,5:1 O no se puede resolver (y no está excluido)."""
    fallos, sin_resolver = [], []
    for nombre, selector, fg, bg, origen in pares:
        if (selector, fg, bg) in EXCLUSIONES:
            assert EXCLUSIONES[(selector, fg, bg)].strip(), "una exclusión necesita motivo"
            continue
        f, b = resolver(fg, temas[nombre]), resolver(bg, temas[nombre])
        if f is None or b is None:
            sin_resolver.append(f"[{nombre}] {selector}  {fg} sobre {bg} ({origen})")
            continue
        r = contraste(f, b)
        if r < TEXTO:
            fallos.append(f"{r:4.2f}:1 [{nombre}] {selector}  {fg} sobre {bg} ({origen})")
    mensajes = []
    if sin_resolver:
        mensajes.append(
            "pares SIN RESOLVER (añade soporte al resolvedor o una exclusión con motivo):"
            "\n  " + "\n  ".join(sorted(set(sin_resolver))))
    if fallos:
        mensajes.append("pares por debajo de 4,5:1:\n  " + "\n  ".join(sorted(set(fallos))))
    assert not mensajes, "\n".join(mensajes)


# ── 1. contraste de TODO par que la hoja declara ──────────────────────────────────────────
class TestParesDeLaHoja:

    def test_se_extraen_pares_en_los_dos_temas(self):
        """Salvaguarda del propio test: si el parser no ve pares, la prueba pasaría vacía."""
        pares = _pares_de_la_hoja()
        assert len(pares) > 150
        assert {p[0] for p in pares} == {"claro", "oscuro"}

    def test_todo_texto_declarado_cumple_4_5_en_ambos_temas(self):
        comprobar_pares(_pares_de_la_hoja(), _temas())

    def test_no_hay_exclusiones_sin_justificar(self):
        assert all(motivo.strip() for motivo in EXCLUSIONES.values())

    def test_el_boton_amarillo_lleva_texto_oscuro_tambien_en_el_tema_oscuro(self):
        """Bug medido en la línea base: `--ink` es CLARO en oscuro (1,2:1 sobre el amarillo)."""
        for nombre, tema in _temas().items():
            assert contraste(resolver("var(--on-yellow)", tema),
                             resolver("var(--yellow)", tema)) >= TEXTO, nombre
        regla = next(d for s, d in _reglas() if s.startswith('button.primary,'))
        assert regla["color"] == "var(--on-yellow)"


# ── 2. pares declarados a mano (tokens que aún no usa ninguna regla) ──────────────────────
PARES_DE_TOKENS = [
    # (nombre, fg, bg, mínimo)
    ("--ink-faint sobre --paper", "--ink-faint", "--paper", TEXTO),
    ("--ink-faint sobre --paper-2", "--ink-faint", "--paper-2", TEXTO),
    ("--ink-soft sobre --paper-2", "--ink-soft", "--paper-2", TEXTO),
    ("--cyan-t sobre --paper", "--cyan-t", "--paper", TEXTO),
    ("--cyan-t sobre --paper-2", "--cyan-t", "--paper-2", TEXTO),
    ("--ok-t sobre --paper-2", "--ok-t", "--paper-2", TEXTO),
    ("--warn-t sobre --paper-2", "--warn-t", "--paper-2", TEXTO),
    ("--amber-t sobre --caption-bg", "--amber-t", "--caption-bg", TEXTO),
    ("--amber-t sobre --paper", "--amber-t", "--paper", TEXTO),
    ("--mag-t sobre --paper", "--mag-t", "--paper", TEXTO),
    ("--mag-t sobre --paper-2", "--mag-t", "--paper-2", TEXTO),
    ("relleno verde con su texto", "--on-ok-solid", "--ok-solid", TEXTO),
    ("relleno rojo con su texto", "--on-warn-solid", "--warn-solid", TEXTO),
    ("texto sobre amarillo", "--on-yellow", "--yellow", TEXTO),
    # La insignia «caliente» (.badge.hot de la maqueta). V3 usará estos dos tokens.
    ("insignia caliente (.badge.hot)", "--on-hot", "--hot", TEXTO),
    # V2: texto de cada matiz sobre su fondo teñido (chip) y texto de tinta sobre él (aviso).
    ("chip ok", "--ok-t", "--ok-bg", TEXTO),
    ("chip warn", "--warn-t", "--warn-bg", TEXTO),
    ("chip amber", "--amber-t", "--amber-bg", TEXTO),
    ("chip info", "--cyan-t", "--info-bg", TEXTO),
    ("aviso/hero ok (tinta)", "--ink", "--ok-bg", TEXTO),
    ("aviso/hero warn (tinta)", "--ink", "--warn-bg", TEXTO),
    ("aviso/hero amber (tinta)", "--ink", "--amber-bg", TEXTO),
    ("aviso/hero info (tinta)", "--ink", "--info-bg", TEXTO),
    # No texto (1.4.11): foco, bordes de controles, icono de estado.
    ("anillo de foco sobre --paper", "--cyan-t", "--paper", NO_TEXTO),
    ("anillo de foco sobre --paper-2", "--cyan-t", "--paper-2", NO_TEXTO),
    ("borde de control (--ink) sobre --paper", "--ink", "--paper", NO_TEXTO),
    ("borde discreto (--ink-faint) sobre --paper-2", "--ink-faint", "--paper-2", NO_TEXTO),
    ("casilla marcada (--mag-t) sobre --paper", "--mag-t", "--paper", NO_TEXTO),
]


class TestParesDeTokens:

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize(
        "nombre,fg,bg,minimo", PARES_DE_TOKENS, ids=[p[0] for p in PARES_DE_TOKENS])
    def test_par(self, tema, nombre, fg, bg, minimo):
        t = _temas()[tema]
        r = contraste(resolver(f"var({fg})", t), resolver(f"var({bg})", t))
        assert r >= minimo, f"{nombre} [{tema}]: {r:.2f}:1 < {minimo}:1"

    def test_la_insignia_de_la_maqueta_en_oscuro_no_se_copia_tal_cual(self):
        """La maqueta usa blanco sobre #f04d97 en oscuro: 3,38:1. Por eso el token cambia el
        color del TEXTO (--on-hot) y no se copia el par."""
        assert contraste("#ffffff", "#f04d97") < TEXTO
        oscuro = _temas()["oscuro"]
        assert contraste(resolver("var(--on-hot)", oscuro), resolver("var(--hot)", oscuro)) >= TEXTO


# ── 3. estructura: lo que el contraste no ve ──────────────────────────────────────────────
RELLENOS = {"--cyan", "--magenta", "--yellow", "--ok", "--warn"}


class TestEstructura:

    def test_ningun_relleno_se_usa_como_color_de_texto(self):
        """cyan/ok/warn/magenta/yellow son RELLENO y BORDE; como texto van las variantes `-t`."""
        malos = []
        for selector, d in _reglas():
            m = re.fullmatch(r"var\((--[\w-]+)\)", d.get("color", ""))
            if m and m.group(1) in RELLENOS:
                malos.append(f"{selector}: color {d['color']}")
        assert not malos, "texto con color de relleno:\n  " + "\n  ".join(malos)

    def test_ningun_texto_lleva_un_color_literal(self):
        """`color: #fff` no cambia con el tema: usa un par (--on-*)."""
        malos = [f"{s}: color {d['color']}" for s, d in _reglas()
                 if re.match(r"#[0-9a-fA-F]{3,6}\b", d.get("color", ""))]
        assert not malos, "colores literales de texto:\n  " + "\n  ".join(malos)

    def test_las_plantillas_no_fijan_colores(self):
        """Si una plantilla fijara `style="color:…"`, esta prueba de la hoja no la vería."""
        malos = [f.name for f in PLANTILLAS.glob("*.html")
                 if re.search(r'style="[^"]*(?<![-\w])(color|background)\s*:',
                              f.read_text("utf-8"))]
        assert not malos, f"estilos de color en línea en: {malos}"

    def test_ningun_texto_baja_de_14_px(self):
        """Un `clamp` cuenta por su mínimo (la etiqueta de la barra inferior baja a 12 px y está
        declarada en EXCEPCIONES_DE_TAMANO); `var()`/`inherit` y `cqw` fallan salvo declarados."""
        problemas = problemas_de_tamano(_reglas())
        assert not problemas, "texto por debajo de 14 px o sin poder comprobarse:\n  " + "\n  ".join(problemas)

    @pytest.mark.parametrize("selector", [
        ".topnav a", ".series-search", ".issue-input", ".search-input",
        ".politica-form select", '.ajustes-card input[type="text"]',
        '.login-form input[type="text"]', ".page-link", ".back-link",
    ])
    def test_controles_con_altura_minima_de_40_px(self, selector):
        alturas = [d.get("min-height") for s, d in _reglas()
                   if selector in [x.strip() for x in s.split(",")] and "min-height" in d]
        assert alturas, f"{selector}: sin min-height"
        assert all(float(re.match(r"([\d.]+)px", a).group(1)) >= 40 for a in alturas), alturas

    def test_botones_con_altura_minima_de_40_px(self):
        regla = next(d for s, d in _reglas() if s.startswith("button,") and "min-height" in d)
        assert float(re.match(r"([\d.]+)px", regla["min-height"]).group(1)) >= 40

    def test_casillas_y_radios_de_24_px(self):
        regla = next(d for s, d in _reglas() if s.startswith('input[type="checkbox"]'))
        assert regla["width"] == "24px" and regla["height"] == "24px"

    def test_el_marcador_de_posicion_tiene_color_de_texto(self):
        regla = next((d for s, d in _reglas() if s == "::placeholder"), None)
        assert regla and regla["color"] == "var(--ink-faint)" and regla["opacity"] == "1"

    def test_los_puntos_de_estado_se_distinguen_del_fondo_por_su_borde(self):
        """Sin texto, su relleno amarillo apenas contrasta con el papel (1,4:1): el borde de tinta
        (≥ 3:1, ver PARES_DE_TOKENS) es lo que los hace perceptibles."""
        punto = next(d for s, d in _reglas() if s == ".estado-dot")
        assert punto["border"] == "2px solid var(--ink)"

    def test_el_estado_de_un_numero_no_depende_solo_del_color(self):
        css = _hoja()
        assert '.issue-chip.issue-present::before { content: "✓ "; }' in css
        faltante = next(d for s, d in _reglas() if s == ".issue-chip.issue-missing")
        assert faltante.get("border-style") == "dashed"


# ── 4. tema oscuro completo y alias conservado ────────────────────────────────────────────
TOKENS_QUE_CAMBIAN_EN_OSCURO = [
    "--ink-faint", "--cyan-t", "--ok-t", "--warn-t", "--amber-t", "--mag-t",
    "--ok-solid", "--on-ok-solid", "--warn-solid", "--on-warn-solid", "--hot", "--on-hot",
    "--ok-bg", "--warn-bg", "--amber-bg", "--info-bg",     # V2: fondos teñidos de chip/aviso
]
TOKENS_IGUALES_EN_AMBOS_TEMAS = ["--on-yellow"]   # texto oscuro sobre amarillo en los dos temas


class TestTemas:

    @pytest.mark.parametrize("token", TOKENS_QUE_CAMBIAN_EN_OSCURO)
    def test_el_token_tiene_valor_propio_en_oscuro(self, token):
        t = _temas()
        assert token in t["claro"], f"{token} no existe en :root"
        assert t["oscuro"][token] != t["claro"][token], f"{token} no se redefine en el tema oscuro"

    @pytest.mark.parametrize("token", TOKENS_IGUALES_EN_AMBOS_TEMAS)
    def test_el_token_es_el_mismo_en_ambos_temas_a_proposito(self, token):
        t = _temas()
        assert t["claro"][token] == t["oscuro"][token]

    def test_ink_faint_conserva_su_nombre(self):
        """Las plantillas y reglas existentes lo usan: renombrarlo rompería el alias de V1."""
        assert "--ink-faint" in _temas()["claro"]
        assert "var(--ink-faint)" in _hoja()

    def test_los_rellenos_conservan_la_identidad_cmyk(self):
        """V1 separa texto de relleno, no cambia la paleta: los cinco rellenos no se mueven."""
        claro = _temas()["claro"]
        assert {k: claro[k] for k in ("--cyan", "--magenta", "--yellow", "--ok", "--warn")} == {
            "--cyan": "#0d9bd6", "--magenta": "#d81a75", "--yellow": "#f2c500",
            "--ok": "#2e8b57", "--warn": "#c0392b"}


# ── 4b. sombra dura: visible en los dos temas y de un solo color ──────────────────────────
SOMBRAS_DURAS = ("--shadow-ink", "--shadow-ink-sm", "--shadow-ink-hover", "--shadow-ink-active")


class TestSombraDura:
    """Regresión de dos mecanismos del tema oscuro: la sombra era negro al 55 % (`rgba`, 1,13:1
    sobre --paper: no se veía) y el hover/active de los botones escribían `var(--ink)` a mano, que
    en oscuro es crema: el botón sin sombra la ganaba en crema al pasar. La sombra es la señal de
    «esto se pulsa» (CLAUDE.md §6), así que se le pide el 3:1 de lo que no es texto (WCAG 1.4.11)."""

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("fondo", ["--paper", "--paper-2"])
    def test_la_sombra_dura_se_ve_sobre_el_papel(self, tema, fondo):
        t = _temas()[tema]
        color = resolver("var(--shadow-color)", t)
        assert color, f"--shadow-color [{tema}] no es un color sólido: {t.get('--shadow-color')!r}"
        r = contraste(color, resolver(f"var({fondo})", t))
        assert r >= NO_TEXTO, f"sombra sobre {fondo} [{tema}]: {r:.2f}:1 < {NO_TEXTO}:1"

    def test_en_oscuro_la_sombra_no_es_la_tinta_crema(self):
        """Con la tinta crema la sombra se leería como un segundo borde, más grueso."""
        t = _temas()["oscuro"]
        r = contraste(resolver("var(--shadow-color)", t), resolver("var(--ink)", t))
        assert r >= NO_TEXTO, f"sombra frente a la tinta en oscuro: {r:.2f}:1"

    @pytest.mark.parametrize("token", SOMBRAS_DURAS)
    def test_cada_desplazamiento_usa_el_color_de_sombra_del_tema(self, token):
        """Un solo color: el tema oscuro cambia --shadow-color y no redefine los desplazamientos."""
        t = _temas()
        assert t["claro"][token].endswith("0 var(--shadow-color)"), t["claro"][token]
        assert t["oscuro"][token] == t["claro"][token], f"{token} se redefine en oscuro"

    def test_ninguna_sombra_dura_lleva_el_color_escrito_a_mano(self):
        permitidas = {"none"} | {f"var({s})" for s in SOMBRAS_DURAS}
        malas = [f"{s}: box-shadow: {d['box-shadow']}" for s, d in _reglas()
                 if "box-shadow" in d and d["box-shadow"] not in permitidas]
        assert not malas, "sombras fuera de los tokens:\n" + "\n".join(malas)


class TestElMinimoDeTamanoNoOmiteNada:
    """Pruebas de la propia prueba del mínimo de 14 px. Antes saltaba todo `clamp`, `var()` e `inherit`,
    así que la etiqueta de la barra inferior (12 px) no se comprobaba y un `clamp(.5rem, …)` habría pasado."""

    SIN = {}      # sin excepciones, para probar la regla pelada

    def _p(self, reglas, **kw):
        kw.setdefault("excepciones", self.SIN)
        kw.setdefault("no_comprobables", self.SIN)
        kw.setdefault("proporcionales", self.SIN)
        return problemas_de_tamano(reglas, **kw)

    def test_un_clamp_cuenta_por_su_minimo(self):
        assert minimo_px("clamp(.75rem, 3.3vw, .875rem)") == 12.0
        assert minimo_px("clamp(30px, 4.4vw, 48px)") == 30.0

    def test_un_clamp_que_baja_de_14_sin_excepcion_falla(self):
        p = self._p([(".etiqueta", {"font-size": "clamp(.5rem, 3vw, 1rem)"})])
        assert len(p) == 1 and ".etiqueta" in p[0] and "8 px" in p[0]

    def test_un_clamp_que_no_baja_de_14_pasa(self):
        assert self._p([(".h", {"font-size": "clamp(19px, 2.4vw, 26px)"})]) == []

    @pytest.mark.parametrize("valor", [
        "clamp(1vw, 3vw, 2rem)", "clamp(.75rem, 3vw)", "clamp(var(--a), 3vw, 2rem)", "min(1rem, 2vw)",
        "smaller", "large",
    ])
    def test_un_valor_ilegible_falla_en_vez_de_saltarse(self, valor):
        p = self._p([(".x", {"font-size": valor})])
        assert len(p) == 1 and ".x" in p[0]

    def test_var_e_inherit_fallan_salvo_lista_explicita_y_hoy_la_lista_esta_vacia(self):
        assert TAMANOS_NO_COMPROBABLES == {}
        for valor in ("var(--tam)", "inherit"):
            assert len(self._p([(".v", {"font-size": valor})])) == 1
            assert self._p([(".v", {"font-size": valor})], no_comprobables={".v": "motivo"}) == []

    def test_el_tamano_proporcional_se_declara_con_motivo(self):
        regla = [(".inicial", {"font-size": "46cqw"})]
        assert len(self._p(regla)) == 1
        assert self._p(regla, proporcionales={".inicial": "decorativa"}) == []

    def test_la_excepcion_vale_con_su_minimo_y_su_motivo(self):
        regla = [(".nav", {"font-size": "clamp(.75rem, 3.3vw, .875rem)"})]
        assert self._p(regla, excepciones={".nav": (12.0, "U16")}) == []

    def test_una_excepcion_no_deja_bajar_de_lo_declarado(self):
        regla = [(".nav", {"font-size": "clamp(.6rem, 3.3vw, .875rem)"})]
        p = self._p(regla, excepciones={".nav": (12.0, "U16")})
        assert len(p) == 1 and "lo declarado" in p[0]

    def test_una_excepcion_obsoleta_falla(self):
        """Si la regla vuelve a 14 px o desaparece, la excepción sobra y se tiene que borrar."""
        for reglas in ([(".nav", {"font-size": ".875rem"})], []):
            p = self._p(reglas, excepciones={".nav": (12.0, "U16")})
            assert len(p) == 1 and "obsoleta" in p[0]

    def test_una_excepcion_sin_motivo_falla(self):
        regla = [(".nav", {"font-size": "clamp(.75rem, 3.3vw, .875rem)"})]
        assert any("motivo" in x for x in self._p(regla, excepciones={".nav": (12.0, "  ")}))

    def test_la_hoja_real_solo_tiene_la_excepcion_de_la_barra_inferior(self):
        """La excepción declarada se usa de verdad y lleva las medidas que la justifican."""
        assert list(EXCEPCIONES_DE_TAMANO) == [".nav-enlace"]
        minimo, motivo = EXCEPCIONES_DE_TAMANO[".nav-enlace"]
        assert minimo == 12.0
        for dato in ("56,1", "60,8", "65,5", "62", "424"):
            assert dato in motivo, dato
        assert problemas_de_tamano(_reglas()) == []


class TestLoNoSoportadoNoPasaInadvertido:
    """Regresión del mecanismo: antes `if f is None or b is None: continue` dejaba fuera, sin
    avisar, cualquier color que el resolvedor no entendiera."""

    @pytest.mark.parametrize("css", [
        ".x { color: hsl(0 0% 40%); background: var(--paper); }",          # texto no soportado
        ".x { color: oklch(40% 0 0); background: var(--paper); }",
        ".x { color: var(--ink); background: rgba(0, 0, 0, .1); }",          # fondo no soportado
        ".x { color: var(--ink); background: linear-gradient(red, blue); }",  # degradado con texto
        ".x { color: var(--no-existe); background: var(--paper); }",         # variable inexistente
        ".x { color: var(--ink); background: var(--no-existe); }",
    ])
    def test_una_expresion_no_soportada_hace_fallar(self, css):
        with pytest.raises(AssertionError, match="SIN RESOLVER"):
            comprobar_pares(_pares_de_la_hoja(css), _temas())

    def test_un_par_resoluble_que_no_llega_sigue_fallando_por_contraste(self):
        with pytest.raises(AssertionError, match="por debajo de 4,5:1"):
            comprobar_pares(_pares_de_la_hoja(".x { color: #777; background: #888; }"), _temas())

    def test_un_par_correcto_pasa(self):
        comprobar_pares(_pares_de_la_hoja(".x { color: var(--ink); background: var(--paper); }"),
                        _temas())

    def test_none_y_transparent_significan_sin_fondo_propio(self):
        """Antes `background: none` hacía saltar el par en silencio (`.btn-logout`)."""
        for fondo in ("none", "transparent"):
            pares = _pares_de_la_hoja(f".x {{ color: var(--ink-soft); background: {fondo}; }}")
            assert {p[4] for p in pares} == {"contexto"}
            comprobar_pares(pares, _temas())

    def test_una_exclusion_solo_vale_con_motivo(self, monkeypatch):
        css = ".x { color: hsl(0 0% 40%); background: var(--paper); }"
        clave = (".x", "hsl(0 0% 40%)", "var(--paper)")
        monkeypatch.setitem(EXCLUSIONES, clave, "")
        with pytest.raises(AssertionError, match="necesita motivo"):
            comprobar_pares(_pares_de_la_hoja(css), _temas())
        monkeypatch.setitem(EXCLUSIONES, clave, "componente de terceros, revisado a mano")
        comprobar_pares(_pares_de_la_hoja(css), _temas())

    def test_la_hoja_real_no_tiene_pares_sin_resolver(self):
        temas = _temas()
        for nombre, selector, fg, bg, _ in _pares_de_la_hoja():
            if (selector, fg, bg) in EXCLUSIONES:
                continue
            assert resolver(fg, temas[nombre]) and resolver(bg, temas[nombre]), (selector, fg, bg)


# ── 5. la fila de Deseados no desborda por culpa del texto de 14 px (medido en navegador) ─────
class TestFilaDeDeseados:
    """V1 subió el texto mínimo a 14 px y, sin `flex-wrap`, la fila de Deseados se salía de la
    pantalla en móvil (731 → 756 px de ancho de página a 390 px). La medición real está en
    `docs/design/ui-v1/README.md`; aquí se fija el mecanismo."""

    def _regla(self, selector: str) -> dict[str, str]:
        return next(d for s, d in _reglas() if s == selector)

    def test_la_fila_puede_partirse_en_varias_lineas(self):
        assert self._regla(".wishlist-row")["flex-wrap"] == "wrap"

    def test_el_titulo_tiene_una_base_propia_y_no_se_aplasta(self):
        assert self._regla(".wishlist-title")["flex"].startswith("1 1 ")

    def test_el_panel_de_candidatos_ocupa_linea_propia_solo_si_tiene_contenido(self):
        """Vacío no debe forzar una línea vacía (12 px de hueco) en cada fila."""
        regla = self._regla(".wishlist-row .candidatos-wishlist:not(:empty)")
        assert regla["flex"] == "1 1 100%"
        assert not any(s == ".wishlist-row .candidatos-wishlist" for s, _ in _reglas())
