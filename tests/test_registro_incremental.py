# ruff: noqa: E501
"""Registro incremental (#326) — lo que se comprueba SIN base de datos: la huella del alcance, las cuentas del estado y lo que la pantalla le dice al
coleccionista. El comportamiento con ficheros y Postgres reales está en `tests/test_registro_incremental_pg.py`.
"""
from __future__ import annotations

import re

from zascarr.services.library_adopter import EstadoAdopcion, InventarioBiblioteca
from zascarr.services.registro_biblioteca import EstadoRegistro, FaseRegistro
from zascarr.web.routes import crear_templates

PLANTILLA = "_auditoria_registro.html"


def _inv(nuevas=(), **kw) -> InventarioBiblioteca:
    base = dict(en_disco=10, cbz=8, cbr=2, otros_formatos=0, ya_registrados=10 - len(nuevas), nuevos=len(nuevas), registrados_sin_fichero=0,
                carpeta_accesible=True, rutas_nuevas=frozenset(nuevas))
    base.update(kw)
    return InventarioBiblioteca(**base)


def _render(**ctx) -> str:
    contexto = {"reg": EstadoRegistro(), "estado": EstadoAdopcion.HECHA, "inv": None, "series": 0, "inc": None, "cambio": False}
    contexto.update(ctx)
    return crear_templates().env.get_template(PLANTILLA).render(**contexto)


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class TestHuella:

    def test_no_depende_del_orden_y_cambia_con_el_conjunto(self):
        assert _inv(["/b", "/a"]).huella == _inv(["/a", "/b"]).huella
        assert _inv(["/a"]).huella != _inv(["/a", "/b"]).huella != _inv([]).huella

    def test_no_incluye_las_rutas_en_claro(self):
        assert "/a/secreto" not in _inv(["/a/secreto"]).huella and len(_inv(["/a"]).huella) == 64


class TestEstadoDelRegistro:

    def test_las_filas_nuevas_no_cuentan_los_reenlaces(self):
        e = EstadoRegistro(registrados=5, reenlazados=2, sin_identificar=3)
        assert e.filas_nuevas == 6 and e.anadidos == 8        # `anadidos` (registro inicial) no cambia: se conserva su significado


class TestPantallaIncremental:

    def test_con_el_registro_hecho_ofrece_buscar_y_no_promete_que_no_haya_nada(self):
        t = _texto(_render())
        assert "Tu biblioteca ya está registrada" in t and "Buscar archivos sin registrar" in t
        assert "No hay nada nuevo" not in t                                    # ya no se afirma sin mirar

    def test_la_revision_dice_que_solo_mira_nombres_y_que_no_toca_nada(self):
        t = _texto(_render(inc=_inv(["/a", "/b"])))
        assert "no se ha abierto ninguno ni se ha escrito nada" in t and "ninguna fuente de internet" in t
        assert "no se vincula nada solo por el nombre de su carpeta" in t
        assert "Registrar los 2 archivos sin registrar" in t and 'name="huella"' in _render(inc=_inv(["/a", "/b"]))
        assert "no se añade dos veces" in t                                    # y que una copia idéntica seguirá saliendo

    def test_sin_nuevos_no_hay_boton_de_registrar(self):
        h = _render(inc=_inv([]))
        assert "No hay archivos sin registrar" in _texto(h) and "Registrar los" not in _texto(h)

    def test_carpeta_inaccesible_no_ofrece_registrar_ni_da_nada_por_perdido(self):
        h = _render(inc=_inv([], carpeta_accesible=False, en_disco=0, nuevos=0, ya_registrados=0))
        t = _texto(h)
        assert "No se puede leer la carpeta" in t and "no se da por nuevo ni por perdido" in t and "Registrar los" not in t

    def test_carpeta_vacia_avisa_en_vez_de_decir_que_todo_esta_registrado(self):
        t = _texto(_render(inc=_inv([], en_disco=0, nuevos=0, ya_registrados=0)))
        assert "No hemos visto ningún tebeo" in t and "ningún archivo por perdido" in t and "todo lo que hay en la carpeta ya está registrado" not in t

    def test_si_la_carpeta_cambio_lo_dice(self):
        t = _texto(_render(inc=_inv(["/a"]), cambio=True))
        assert "ha cambiado desde que lo revisaste" in t and "no se ha registrado nada" in t

    def test_el_resultado_separa_las_categorias_y_no_llama_nueva_a_una_ficha_reenlazada(self):
        reg = EstadoRegistro(fase=FaseRegistro.TERMINADO, incremental=True, total=10, procesados=10, registrados=4, reenlazados=1, sin_identificar=2,
                             repetidos=2, ambiguos=["X.cbz — su contenido coincide con 2 archivos que ya no están"], omitidos=["Y.cbz — desapareció antes de leerlo"])
        t = _texto(_render(reg=reg))
        assert "<strong>5</strong> filas nuevas" not in t and "5 filas nuevas" in t        # 4 - 1 + 2
        assert "3 con serie sugerida" in t and "2 sin identificar" in t
        assert "1 eran un archivo que ya conocías" in t and "no son filas nuevas" in t
        assert "2 repetidos" in t and "No se ha borrado ni movido ninguna copia" in t
        assert "1 que ZascArr no ha podido atribuir con seguridad" in t
        assert "1 de la lista que confirmaste no se han tratado" in t and "no son un error, pero tampoco están registrados" in t.lower()
        assert "Buscar archivos sin registrar otra vez" in t and "Continuar el registro" not in t

    def test_con_errores_no_se_dice_revisados_a_secas(self):
        reg = EstadoRegistro(fase=FaseRegistro.TERMINADO, incremental=True, total=3, procesados=3, errores=["X.cbz: no se pudo registrar (RuntimeError)"])
        t = _texto(_render(reg=reg))
        assert "ha quedado incompleto" in t and "Archivos sin registrar revisados" not in t

    def test_el_texto_no_usa_palabras_internas(self):
        textos = [_texto(_render(inc=_inv(["/a"]))), _texto(_render(reg=EstadoRegistro(fase=FaseRegistro.TERMINADO, incremental=True)))]
        for t in textos:
            for interna in ("sha256", "huella", "alcance", "savepoint", "inventario", "firma", "contenedor"):
                assert not re.search(rf"\b{interna}\b", t.lower()), interna


class TestPantallaRecorridoIncompleto:
    """Revisión de #329: un recorrido que no pudo leer parte de la biblioteca no se presenta como completo ni se confirma en global."""

    def test_con_ilegibles_avisa_no_ofrece_confirmar_y_no_fabrica_bajas(self):
        inv = _inv(["/a"], ilegibles=2, registrados_sin_fichero=0)
        assert inv.recorrido_completo is False and inv.se_puede_confirmar is False
        h = _render(inc=inv)
        t = _texto(h)
        assert "No se ha podido leer 2 carpetas o archivos" in t and "puede estar incompleta" in t and "No se da por perdido ningún archivo" in t
        assert "Registrar los" not in t and "No hay archivos sin registrar" not in t

    def test_con_el_recorrido_completo_si_se_puede_confirmar(self):
        assert _inv(["/a"]).se_puede_confirmar is True and _inv([]).se_puede_confirmar is False

    def test_antes_de_confirmar_avisa_de_que_se_leera_cada_archivo_y_de_lo_que_no_cambia(self):
        t = _texto(_render(inc=_inv(["/a"])))
        assert "lee cada archivo" in t and "puede tardar" in t and "Sigue en segundo plano" in t
        assert "Si alguno cambia mientras se lee, no se registra" in t
        assert "descartados o de una serie retirada: no se vuelven a registrar ni se reactivan" in t
        assert "aún no se sabe si son tebeos distintos" in t                 # la búsqueda no leyó contenido: no afirma «nuevos tebeos»

    def test_otro_registro_en_marcha_lo_dice_y_no_hace_nada(self):
        t = _texto(_render(reg=EstadoRegistro(fase=FaseRegistro.OCUPADO)))
        assert "El catálogo estaba ocupado" in t and "una importación de descargas" in t and "Lo que ya estuviera guardado se conserva" in t


class TestRecorrerComics:
    """`recorrer_comics` dice lo que no pudo mirar; `Path.rglob` lo saltaba en silencio."""

    def test_cuenta_ilegibles_y_no_los_oculta(self, tmp_path):
        import os

        import pytest

        from zascarr.utils.fs import recorrer_comics
        (tmp_path / "ok").mkdir()
        (tmp_path / "ok" / "a.cbz").write_bytes(b"x")
        cerrada = tmp_path / "cerrada"
        cerrada.mkdir()
        (cerrada / "b.cbz").write_bytes(b"y")
        cerrada.chmod(0)
        try:
            if os.access(cerrada, os.R_OK):
                pytest.skip("se ejecuta como root: los permisos no impiden listar")
            r = recorrer_comics([tmp_path], {".cbz"})
        finally:
            cerrada.chmod(0o755)
        assert [p.name for p in r.archivos] == ["a.cbz"] and r.ilegibles == 1 and not r.completo

    def test_raiz_inexistente_es_ilegible_y_completa_si_no_hay_problemas(self, tmp_path):
        from zascarr.utils.fs import recorrer_comics
        assert recorrer_comics([tmp_path / "no-existe"], {".cbz"}).ilegibles == 1
        (tmp_path / "x.cbz").write_bytes(b"x")
        assert recorrer_comics([tmp_path], {".cbz"}).completo

    def test_mismos_criterios_que_listar_comics(self, tmp_path):
        from zascarr.utils.fs import listar_comics, recorrer_comics
        for n in ("a.cbz", "B.CBZ", "c.cbr", "d.txt", ".oculto.cbz"):
            (tmp_path / n).write_bytes(n.encode())
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "e.cbz").write_bytes(b"e")
        (tmp_path / "enlace.cbz").hardlink_to(tmp_path / "a.cbz")           # mismo inodo: no se repite
        exts = {".cbz", ".cbr"}
        def inodos(archivos):
            return sorted(p.stat().st_ino for p in archivos)       # qué ficheros, no qué nombre elige cada uno de los dos al deduplicar el enlace
        assert inodos(recorrer_comics([tmp_path], exts).archivos) == inodos(listar_comics([tmp_path], exts))


class TestLimiteVisibleDeIncidencias:
    """Si solo se listan 50, la pantalla dice cuántas hay en total y que el listado está limitado."""

    def test_con_mas_de_50_incidencias_dice_el_total_y_que_se_limita(self):
        errores = [f"F{i}.cbz: no se pudo registrar (RuntimeError)" for i in range(73)]
        omitidos = [f"G{i}.cbz — desapareció antes de leerlo" for i in range(51)]
        reg = EstadoRegistro(fase=FaseRegistro.TERMINADO, incremental=True, total=130, procesados=130, errores=errores, omitidos=omitidos)
        t = _texto(_render(reg=reg))
        assert "(73)" in t and "Se muestran los 50 primeros de 73" in t
        assert "(51)" in t and "Se muestran los 50 primeros de 51" in t
        assert "F49.cbz" in t and "F50.cbz" not in t

    def test_con_pocas_incidencias_no_hay_aviso_de_limite(self):
        reg = EstadoRegistro(fase=FaseRegistro.TERMINADO, incremental=True, total=3, procesados=3, errores=["F0.cbz: x"], omitidos=["G0.cbz — x"])
        assert "Se muestran los 50 primeros" not in _texto(_render(reg=reg))
