"""#689: tokens de tipografía, forma y espaciado en web.css (parseo real, sin navegador)."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static" / "web.css"

TOKENS_TEXTO = {
    "--text-titulo-pagina": "clamp(30px, 4.4vw, 48px)",
    "--text-cifra": "clamp(30px, 3.4vw, 42px)",
    "--text-titulo-seccion": "clamp(19px, 2.4vw, 26px)",
    "--text-marca": "1.4rem",
    "--text-numero-paso": "1.25rem",
    "--text-titulo-bloque": "1.05rem",
    "--text-cuerpo": "1rem",
    "--text-titulo-frase": "1.05rem",
    "--text-estado-resumen": "1.15rem",
    "--text-didascalia": ".9rem",
    "--text-nav": ".95rem",
    "--text-boton": ".88rem",
    "--text-secundario": ".875rem",
    "--text-chip": ".875rem",
    "--text-etiqueta": ".875rem",
    "--text-nav-movil": "clamp(.75rem, 3.3vw, .875rem)",
}
TOKENS_FORMA = {
    "--border-panel": "3px",
    "--border-control": "2.5px",
    "--border-chip": "2px",
    "--border-line": "1px",
}
TOKENS_ESPACIO = {
    "--space-1": "4px",
    "--space-2": "8px",
    "--space-3": "12px",
    "--space-4": "16px",
    "--space-5": "24px",
    "--space-6": "32px",
}


def _sin_comentarios() -> str:
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _root(css: str) -> dict[str, str]:
    bloque = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    assert bloque, "no encuentro :root"
    return {k: " ".join(v.split()) for k, v in
            re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", bloque.group(1))}


def _declaraciones(css: str) -> list[tuple[str, str, str]]:
    salida = []
    for selector, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        for prop, valor in re.findall(r"([\w-]+)\s*:\s*([^;]+);?", cuerpo):
            salida.append((" ".join(selector.split()), prop.strip(), " ".join(valor.split())))
    return salida


def _fuera_de_root(css: str) -> str:
    return re.sub(r":root\s*\{.*?\n\}", "", css, flags=re.S)


def test_tokens_de_tipografia_forma_y_espacio():
    css = _sin_comentarios()
    tokens = _root(css)
    for nombre, valor in {**TOKENS_TEXTO, **TOKENS_FORMA, **TOKENS_ESPACIO}.items():
        assert tokens.get(nombre) == valor, f"{nombre}: {tokens.get(nombre)!r}"


def test_fuera_de_root_no_queda_ningun_font_size_literal():
    css = _sin_comentarios()
    declaraciones = _declaraciones(_fuera_de_root(css))
    tam = [(sel, v) for sel, prop, v in declaraciones if prop == "font-size"]
    assert len(tam) == 140, f"declaraciones font-size: {len(tam)}"
    malas = [(sel, v) for sel, v in tam if not re.fullmatch(r"var\(--text-[\w-]+\)", v)]
    assert not malas, "font-size sin token:\n" + "\n".join(f"{s}: {v}" for s, v in malas)


def test_fuera_de_root_no_quedan_grosores_de_borde_literales():
    css = _sin_comentarios()
    malas = []
    for sel, prop, valor in _declaraciones(_fuera_de_root(css)):
        if not prop.startswith("border") or prop == "border-radius":
            continue
        if re.search(r"\b(?:3px|2\.5px|2px|1px)\b", valor):
            malas.append(f"{sel} {{ {prop}: {valor} }}")
    assert not malas, "bordes sin token:\n" + "\n".join(malas)


def test_la_excepcion_de_nav_movil_es_un_token_declarado():
    tokens = _root(_sin_comentarios())
    assert tokens["--text-nav-movil"] == "clamp(.75rem, 3.3vw, .875rem)"
    assert "font-size: var(--text-nav-movil)" in CSS.read_text(encoding="utf-8")


def test_los_tokens_se_usan_y_el_espaciado_no_es_solo_un_adorno():
    css = _sin_comentarios()
    for nombre in TOKENS_TEXTO:
        assert re.search(rf"var\({re.escape(nombre)}\)", css), nombre
    for nombre in ("--space-1", "--space-2", "--space-3", "--space-4", "--space-5"):
        assert re.search(rf"var\({re.escape(nombre)}\)", css), nombre
