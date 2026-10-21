"""Genera los dos prototipos estáticos de U10 con datos sintéticos.

No es código de producto: vive en docs/design/ui-u10/ y solo produce HTML para
la simulación de usabilidad. No toca la base de datos, ni la app, ni la Pi.

Uso:
    python docs/design/ui-u10/generar_prototipos.py
"""
from __future__ import annotations

from html import escape
from pathlib import Path

DOC = Path(__file__).parent
OUT = DOC / "prototipos"

SERIES = [
    ("Flash (1987)", 155, "Flash (1987)", 94),
    ("Mortadelo y Filemón", 128, "Mortadelo y Filemón (1958)", 91),
    ("Dragon Ball", 96, "Dragon Ball (1984)", 97),
    ("Batman", 84, "Batman (1940)", 88),
    ("Astérix", 72, "Astérix el Galo (1961)", 93),
    ("Tintín", 64, "Las aventuras de Tintín (1929)", 90),
    ("One Piece", 61, "One Piece (1997)", 96),
    ("Spider-Man", 58, "The Amazing Spider-Man (1963)", 87),
    ("Watchmen", 42, "Watchmen (1986)", 95),
    ("Mafalda", 38, "Mafalda (1964)", 92),
    ("Corto Maltés", 35, "Corto Maltés (1967)", 89),
    ("Blueberry", 33, "Blueberry (1963)", 86),
    ("Judge Dredd", 31, "Judge Dredd (1977)", 84),
    ("Hellboy", 29, "Hellboy (1993)", 90),
    ("Spawn", 27, "Spawn (1992)", 83),
    ("The Sandman", 25, "The Sandman (1989)", 91),
    ("Preacher", 23, "Preacher (1995)", 88),
    ("Sin City", 21, "Sin City (1991)", 92),
    ("Scott Pilgrim", 19, "Scott Pilgrim (2004)", 94),
    ("Saga", 18, "Saga (2012)", 85),
]

# 108 carpetas: las 20 primeras con datos "reales" de la muestra y el resto
# generadas de forma determinista, hasta sumar 1.308 pendientes en carpetas.
FOLDERS = list(SERIES)
for i in range(21, 109):
    # 88 carpetas pequeñas que, con las 20 de la muestra, suman exactamente
    # 1.308 pendientes en carpetas (+14 sueltos = 1.322, la referencia real).
    n = 1 + (i * 3) % 6
    if i <= 49:
        n += 1
    FOLDERS.append((f"Carpeta de serie {i:03d}", n, f"Serie sugerida {i:03d}", 55 + (i * 3) % 40))

TOTAL_FOLDERS = sum(n for _, n, _, _ in FOLDERS)
LOOSE = 14
TOTAL = TOTAL_FOLDERS + LOOSE

FILES = [
    ("Flash 001 (1987).cbz", "Flash (1987)", "97%"),
    ("Flash 002 (1987).cbz", "Flash (1987)", "96%"),
    ("Flash 003 (1987).cbz", "Flash (1987)", "95%"),
    ("Flash 004 (1987).cbz", "Flash (1987)", "94%"),
    ("Flash 005 (1987).cbz", "Flash (1987)", "94%"),
    ("Flash 006 (1987).cbz", "Flash (1987)", "93%"),
    ("Flash 007 (1987).cbz", "Flash (1987)", "93%"),
    ("Flash 008 (1987).cbz", "Flash (1987)", "92%"),
    ("Flash 009 (1987).cbz", "Flash (1987)", "92%"),
    ("Flash 010 (1987).cbz", "Flash (1987)", "91%"),
    ("Flash 011 (1987).cbz", "Flash (1987)", "91%"),
    ("Flash 012 (1987).cbz", "Flash (1987)", "90%"),
    ("Flash 013 (1987).cbz", "Flash (1987)", "90%"),
    ("Flash 014 (1987).cbz", "Flash (1987)", "89%"),
    ("Flash 015 (1987).cbz", "Flash (1987)", "89%"),
    ("Flash 016 (1987).cbz", "Flash (1987)", "88%"),
    ("Flash 017 (1987).cbz", "Flash (1987)", "88%"),
    ("Flash 018 (1987).cbz", "Flash (1987)", "87%"),
    ("Flash 019 (1987).cbz", "Flash (1987)", "87%"),
    ("Flash 020 (1987).cbz", "Flash (1987)", "86%"),
]

CSS = """
:root{--paper:#f6f3ec;--card:#fffdf8;--ink:#17171a;--soft:#4a4a50;--line:#17171a;--yellow:#f2c500;--blue:#0a6a96}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
header{border-bottom:3px solid var(--line);padding:14px 24px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
header strong{font-size:22px}header nav{display:flex;gap:14px;flex-wrap:wrap}header a{color:inherit;font-weight:600}
main{max-width:1000px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:34px;margin:0 0 6px}h2{font-size:19px;margin:0 0 4px}h3{font-size:16px;margin:18px 0 6px}
.lead{color:var(--soft);max-width:70ch}.summary{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.chip{border:2px solid var(--line);border-radius:999px;padding:2px 10px;font-size:14px;font-weight:700;background:var(--card)}
.primary,button.primary{display:inline-block;background:var(--yellow);border:3px solid var(--line);padding:10px 16px;font-weight:800;text-decoration:none;color:var(--ink);box-shadow:3px 3px 0 var(--line)}
.btn{display:inline-block;border:2px solid var(--line);padding:7px 12px;text-decoration:none;color:var(--ink);font-weight:700;background:var(--card)}
.muted{color:var(--soft);font-size:14px}
.folders{list-style:none;padding:0;display:grid;gap:12px}
.folder{background:var(--card);border:3px solid var(--line);padding:16px;box-shadow:4px 4px 0 var(--line)}
.folder p{margin:6px 0}.row-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.files{width:100%;border-collapse:collapse;background:var(--card);border:3px solid var(--line)}
.files th,.files td{border-bottom:2px solid var(--line);padding:8px;text-align:left;vertical-align:top}
.files th{background:#efeadf}.files tr:last-child td{border-bottom:0}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0;padding:12px;border:2px dashed var(--line)}
.pagination{display:flex;gap:12px;align-items:center;margin-top:18px}
details{margin-top:10px}summary{cursor:pointer;font-weight:700}
@media(max-width:600px){h1{font-size:28px}.files th:nth-child(3),.files td:nth-child(3){display:none}}
"""


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · prototipo U10</title><style>{CSS}</style></head>
<body>
<header><strong>ZascArr</strong><nav aria-label="Navegación principal">
<a href="#">Inicio</a><a href="#" aria-current="page">Por revisar</a><a href="#">Biblioteca</a><a href="#">Deseados</a><a href="#">Estado</a>
</nav></header>
<main>{body}</main>
</body></html>
"""


def variante_a() -> str:
    folders = []
    for name, count, suggested, score in FOLDERS:
        folders.append(f"""
<li class="folder">
  <h2>{escape(name)}</h2>
  <p><b>{count}</b> archivos · <span class="chip">Serie sugerida: {escape(suggested)} · {score}%</span></p>
  <p class="muted">Es una sugerencia: no está elegida ni asignada.</p>
  <div class="row-actions">
    <a class="primary" href="#">Elegir la serie de esta carpeta</a>
    <a class="btn" href="#">Ver archivos</a>
  </div>
</li>""")
    body = f"""
<h1>Por revisar</h1>
<p class="lead">{TOTAL:,} pendientes en {len(FOLDERS)} carpetas. Empieza por una carpeta: eliges su serie y revisas sus archivos juntos.</p>
<div class="summary"><span class="chip">{TOTAL:,} pendientes</span><span class="chip">{len(FOLDERS)} carpetas</span><span class="chip">{LOOSE} archivos sueltos</span></div>
<p><a class="btn" href="#">Ver los {LOOSE} archivos sueltos</a></p>
<ul class="folders">{''.join(folders[:20])}</ul>
<div class="pagination"><span class="muted">Carpetas 1–20 de {len(FOLDERS)}</span><a class="btn" href="#">Siguientes →</a></div>
"""
    return page("Variante A · carpetas primero", body)


def variante_b() -> str:
    rows = []
    for name, suggested, score in FILES:
        rows.append(f"""
<tr>
  <td><input type="checkbox" aria-label="Seleccionar {escape(name)}"></td>
  <td>{escape(name)}</td>
  <td>{escape(suggested)} · {score}</td>
  <td><button type="button">Asignar…</button></td>
</tr>""")
    body = f"""
<h1>Por revisar</h1>
<p class="lead">{TOTAL:,} pendientes. Revisa los archivos de esta página y asígnalos a una serie.</p>
<div class="summary"><span class="chip">{TOTAL:,} pendientes</span><span class="chip">Mostrando 1–20</span></div>
<div class="toolbar">
  <label><input type="checkbox"> Marcar todos los vinculables de esta página</label>
  <button class="primary" type="button">Asignar…</button>
  <span class="muted">Solo se marca lo que se puede vincular.</span>
</div>
<table class="files">
<thead><tr><th></th><th>Archivo</th><th>Serie sugerida</th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<div class="pagination"><span class="muted">Mostrando 1–20 de {TOTAL:,}</span><a class="btn" href="#">Siguientes →</a></div>
<details><summary>¿Qué hace «Asignar…»?</summary><p>Prepara la asignación de los archivos marcados. Antes de mover nada verás una revisión y tendrás que confirmar.</p></details>
"""
    return page("Variante B · lista compacta con lotes", body)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "variante-a-carpetas.html").write_text(variante_a(), encoding="utf-8")
    (OUT / "variante-b-lista.html").write_text(variante_b(), encoding="utf-8")
    print(f"Generados {OUT/'variante-a-carpetas.html'} y {OUT/'variante-b-lista.html'}")
    print(f"Datos: {TOTAL:,} pendientes ({TOTAL_FOLDERS:,} en {len(FOLDERS)} carpetas + {LOOSE} sueltos)")


if __name__ == "__main__":
    main()
