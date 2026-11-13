"""Compara las declaraciones de web.css antes/después de tokenizar (#689).

Uso:
    python scripts/comparar_tokens_css.py ANTES.css [DESPUES.css]

Resuelve los `var(--text-*)`, `var(--border-*)` y `var(--space-*)` del después
y comprueba que cada valor conserva el original. Las únicas diferencias
permitidas son las de la tabla de redondeos documentada.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NUEVOS = re.compile(r"--(?:text|border|space)-[\\w-]+")
REDONDEOS = {(".92rem", ".9rem"), ("1.02rem", "1.05rem")}
PROPS_ESPACIO = re.compile(
    r"^(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left))?$")


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _root(css: str) -> dict[str, str]:
    m = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    assert m, "falta :root"
    return {k: " ".join(v.split()) for k, v in
            re.findall(r"(--[\\w-]+)\s*:\s*([^;]+);", m.group(1))}


def _declaraciones(css: str) -> list[tuple[str, str, str]]:
    salida = []
    for selector, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        sel = " ".join(selector.split())
        for prop, valor in re.findall(r"([\\w-]+)\\s*:\\s*([^;]+);?", cuerpo):
            salida.append((sel, prop.strip(), " ".join(valor.split())))
    return salida


def _resolver(valor: str, tokens: dict[str, str]) -> str:
    def uno(m):
        return tokens.get(m.group(1), m.group(1))
    return re.sub(r"var\\((--[\\w-]+)\\)", uno, valor)


def _comparar(antes: list, despues: list, tokens: dict[str, str]) -> list[str]:
    # La tokenización solo añade declaraciones nuevas dentro de :root.
    limpio = [(s, p, v) for s, p, v in despues
              if not (s == ":root" and p.startswith("--") and NUEVOS.fullmatch(p))]
    problemas = []
    if len(antes) != len(limpio):
        problemas.append(f"número de declaraciones: antes {len(antes)}, después {len(limpio)}")
    for i, (a, d) in enumerate(zip(antes, limpio, strict=False)):
        if a[:2] != d[:2]:
            problemas.append(f"#{i}: {a[:2]} != {d[:2]}")
            continue
        sel, prop, valor_antes = a
        valor_despues = _resolver(d[2], tokens)
        if prop == "font-size":
            if valor_antes == valor_despues:
                continue
            if (valor_antes, valor_despues) in REDONDEOS:
                continue
        elif prop.startswith("border") and prop != "border-radius" or PROPS_ESPACIO.fullmatch(prop):
            if valor_antes == valor_despues:
                continue
        else:
            if valor_antes == valor_despues:
                continue
            problemas.append(f"{sel} {{{prop}}}: {valor_antes!r} -> {valor_despues!r}")
            continue
        problemas.append(f"{sel} {{{prop}}}: {valor_antes!r} -> {valor_despues!r}")
    return problemas


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    antes = Path(argv[1]).read_text(encoding="utf-8")
    ruta_despues = argv[2] if len(argv) == 3 else "src/zascarr/static/web.css"
    despues = Path(ruta_despues).read_text(encoding="utf-8")
    tokens = _root(_sin_comentarios(despues))
    problemas = _comparar(_declaraciones(_sin_comentarios(antes)),
                          _declaraciones(_sin_comentarios(despues)), tokens)
    if problemas:
        print("Diferencias no declaradas:")
        print("\n".join(problemas))
        return 1
    print("OK: todas las declaraciones conservan su valor (solo redondeos declarados).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
