#!/usr/bin/env python3
"""Genera `catalogo.html`: todas las variantes de los componentes de V2, renderizadas con las
macros REALES (`templates/_componentes.html`) y el CSS REAL (`static/web.css`). No es una pantalla
de la aplicación ni añade ninguna ruta: sirve para revisar los componentes a ojo, en claro y oscuro,
y para las capturas de `README.md`.

    PYTHONPATH=src python3 docs/design/ui-v2/catalogo.py
"""
from __future__ import annotations

from pathlib import Path

from zascarr.web.routes import crear_templates

AQUI = Path(__file__).resolve().parent

PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catálogo de componentes (V2)</title>
<!-- GENERADO por catalogo.py con las macros reales; no editar a mano. -->
<link rel="stylesheet" href="../../../src/zascarr/static/web.css">
<style>.fila{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:10px 0}
.toast{animation:none}</style></head>
<body><main class="content">
<h1>Componentes</h1>
<p class="subtitle">Todas las variantes, con las macros y el CSS reales. Cambia el tema del sistema para ver el oscuro.</p>

<h2>Botones</h2>
<div class="fila">
  <button type="button">Botón</button>
  <button type="button" class="btn primary">.btn.primary</button>
  <button type="button" class="btn ghost">.btn.ghost</button>
  <button type="button" class="btn sm">.btn.sm</button>
  <button type="button" class="btn sm primary">sm primary</button>
  <button type="button" disabled>Desactivado</button>
  <a class="btn" href="#">Enlace .btn</a>
  <a class="btn primary" href="#">Enlace primary</a>
</div>
<div class="fila"><button type="submit">submit (antiguo)</button> <button type="button" class="btn-primary">.btn-primary (alias)</button> <button type="button" class="btn-ignorar">.btn-ignorar</button> <button type="button" class="btn-reintentar">.btn-reintentar</button></div>

<h2>Chips</h2>
<div class="fila">
{% for e, t in [("neutro","En cola"),("ok","Conectada"),("warn","Falló"),("amber","Sin resultados"),("info","Buscando")] %}{{ chip(e, t) }}{% endfor %}
{{ chip("neutro", 0) }}
</div>

<h2>Tarjeta</h2>
<div class="card"><h3>.card</h3><p>Comparte regla con las viñetas existentes (pendientes, deseados, biblioteca).</p></div>

<h2>Grupo</h2>
{% call grupo("Los Guardianes del Alba · Omnigold", 3) %}<div style="padding:14px 16px">Contenido del grupo.</div>{% endcall %}
{% call grupo("Otros", 0) %}<div style="padding:14px 16px">Un grupo con recuento 0.</div>{% endcall %}

<h2>Avisos</h2>
{{ aviso("nota", "Nota: la didascalia de siempre.") }}
{{ aviso("info", "Información: todo está bien, solo te lo contamos.") }}
{{ aviso("ok", "Hecho: se ha guardado.") }}
{{ aviso("amber", "Atención: falta una fuente de búsqueda.") }}
{{ aviso("warn", "Error: no se pudo conectar con el servidor.") }}
{% call aviso("info") %}Con enlace: <a href="#">abre Ajustes</a>.{% endcall %}

<h2>Estado vacío</h2>
{{ estado_vacio("¡Todo clasificado!", "No queda nada por revisar.", ("Volver al inicio", "#")) }}
{{ estado_vacio("No has ignorado nada", "Lo que ignores aparecerá aquí.") }}
{{ estado_vacio("Sin resultados") }}

<h2>Estado grande</h2>
<div class="hero-state ok"><div class="big" aria-hidden="true">✓</div><div><h2>Todo bien</h2><p>Todo funciona.</p></div></div>
<div class="hero-state amber"><div class="big" aria-hidden="true">?</div><div><h2>Atención</h2><p>Una cosa necesita tu revisión.</p></div></div>
<div class="hero-state warn"><div class="big" aria-hidden="true">!</div><div><h2>Error</h2><p>Algo no funciona.</p></div></div>
<div class="hero-state info"><div class="big" aria-hidden="true">i</div><div><h2>Información</h2><p>Para tu conocimiento.</p></div></div>

<h2>Progreso</h2>
{{ progreso(0, 100, "Sin empezar") }}
{{ progreso(30, 100, "Leyendo archivos") }}
{{ progreso(100, 100, "Terminado") }}

<h2>Aviso temporal (.toast)</h2>
<div class="toast" role="status">Guardado. Se aplica al instante. <small>(En la app se desvanece solo por CSS.)</small></div>

<h2>Región viva</h2>
<p class="subtitle">Invisible: <code>aria-live="polite"</code> para lo que cambia tras una acción HTMX.</p>
{{ region_viva("resultado") }}
</main></body></html>
"""


def main() -> None:
    env = crear_templates().env
    html = env.from_string(PAGINA).render()
    (AQUI / "catalogo.html").write_text(html, encoding="utf-8")
    print(f"escrito {AQUI / 'catalogo.html'} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
