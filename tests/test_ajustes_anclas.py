"""UXA-14 (#1131): destinos estables de Ajustes, índice y nota de alcance de «Probar»."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "src" / "zascarr"
AJUSTES = (RAIZ / "web" / "templates" / "ajustes.html").read_text(encoding="utf-8")
IDS = re.findall(r'\bid="([^"{}]+)"', AJUSTES)


def test_los_id_de_ajustes_no_se_repiten():
    repetidos = sorted({i for i in IDS if IDS.count(i) > 1})
    assert repetidos == [], repetidos


def test_todo_enlace_del_indice_apunta_a_un_id_que_existe():
    indice = re.search(r'class="ajustes-indice".*?</ul>', AJUSTES, re.S).group(0)
    destinos = re.findall(r'href="#([^"]+)"', indice)
    assert len(destinos) >= 14
    assert [d for d in destinos if d not in IDS] == []


def test_cada_tarjeta_de_integracion_tiene_su_id_estable():
    for ident in ("ajustes-prowlarr", "ajustes-transmission", "ajustes-amule", "ajustes-foro",
                  "ajustes-comic-vine", "ajustes-metron", "ajustes-metadatos", "blog-rss",
                  "ajustes-fuentes", "ajustes-descargas", "ajustes-propio"):
        assert ident in IDS, ident


def test_todo_enlace_a_ajustes_con_ancla_desde_el_resto_de_la_aplicacion_tiene_destino():
    """Regresión: un `/ui/ajustes#algo` hacia un `id` inexistente se queda en lo alto."""
    patron = re.compile(r'/ui/ajustes#([A-Za-z0-9_-]+)')
    malos = []
    for fichero in list(RAIZ.rglob("*.py")) + list(RAIZ.rglob("*.html")):
        if fichero.name == "ajustes.html":
            continue
        for ancla in patron.findall(fichero.read_text(encoding="utf-8")):
            if ancla not in IDS:
                malos.append((fichero.name, ancla))
    assert malos == [], malos


def test_los_avisos_que_mandan_a_ajustes_van_a_la_tarjeta_concreta():
    """UXA-14: Prowlarr incompleto lleva a su tarjeta, no a lo alto de Ajustes."""
    wishlist = (RAIZ / "web" / "templates" / "wishlist.html").read_text(encoding="utf-8")
    assert 'href="/ui/ajustes#ajustes-prowlarr"' in wishlist
    pasos = (RAIZ / "services" / "primeros_pasos.py").read_text(encoding="utf-8")
    assert '"/ui/ajustes#ajustes-descargas"' in pasos and '"/ui/ajustes", ' not in pasos


def test_cada_probar_conexion_dice_que_usa_lo_que_se_ve_sin_guardar():
    pruebas = len(re.findall(r'hx-post="/ui/ajustes/probar/', AJUSTES))
    notas = AJUSTES.count("{{ nota_probar() }}")
    assert pruebas >= 6 and notas == pruebas
    patron = r"\{% macro nota_probar\(\) -%\}(.*?)\{%- endmacro %\}"
    macro = re.search(patron, AJUSTES, re.S).group(1)
    assert "usa lo que ves ahora en el formulario, aunque aún no lo hayas guardado" in macro
    assert "no guarda nada" in macro


def test_los_destinos_de_las_causas_de_deseados_existen_en_ajustes():
    """`causa_deseo` los arma por concatenación (el rastreo anterior no los ve): se importan."""
    from zascarr.services import causa_deseo
    anclas = {c.destino.split("#", 1)[1] for c in causa_deseo._POR_MOTIVO.values()
              if c.destino and c.destino.startswith("/ui/ajustes#")}
    assert anclas >= {"ajustes-descargas", "ajustes-prowlarr", "ajustes-transmission", "ajustes-amule"}
    assert [a for a in anclas if a not in IDS] == []
