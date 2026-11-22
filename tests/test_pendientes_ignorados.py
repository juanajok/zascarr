"""#1123 (UXA-06): confirmar, recibir y recuperar un «Ignorar» de «Por revisar».

Contrato del modelo: ignorar solo pone `files.review_dismissed`; la ruta y los bytes no se tocan. La
bandeja «Ignorados» lo revierte, y solo eso. Todo es idempotente (un doble envío no hace nada más).
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests.test_pendientes import FakeExecResult, FakeSession, cola_de, use_fake_session
from zascarr.models import File, FileFormat
from zascarr.services.review import ReviewService

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


def _archivo(tmp_path: Path, nombre: str = "x.cbz", **extra) -> File:
    ruta = tmp_path / nombre
    ruta.write_bytes(b"PK\x03\x04 contenido que no se debe tocar")
    datos = dict(id=uuid4(), file_path=str(ruta), file_name=nombre, file_format=FileFormat.CBZ,
                 review_dismissed=False, metadata_={"match_status": "unsorted"})
    datos.update(extra)
    return File(**datos)


def _sesion(*archivos: File, cola=None) -> FakeSession:
    return FakeSession(get_map={(File, a.id): a for a in archivos}, exec_queue=cola)


class TestConfirmacion:

    def test_confirmar_dice_que_archivo_que_pasa_y_ofrece_cancelar_sin_escribir(self, tmp_path):
        f = _archivo(tmp_path, "Batman 001.cbz")
        sesion = _sesion(f)
        with use_fake_session(sesion) as client:
            r = client.get(f"/ui/pendientes/{f.id}/ignorar/confirmar")
        assert r.status_code == 200
        assert "¿Ignorar «Batman 001.cbz»?" in r.text                       # identidad
        assert "no se mueve ni se borra" in r.text and "«Ignorados»" in r.text  # efecto y salida
        assert f'hx-post="/ui/pendientes/{f.id}/ignorar"' in r.text
        assert f'hx-get="/ui/pendientes/{f.id}/ignorar/cancelar"' in r.text
        antes_de_volver = r.text.split("Volver sin ignorar")[0][-200:]
        assert r.text.count("autofocus") == 1 and "autofocus" in antes_de_volver
        # Pedir confirmación no escribe nada.
        assert f.review_dismissed is False and sesion.commit.await_count == 0

    def test_cancelar_devuelve_el_boton_con_el_foco_y_no_cambia_nada(self, tmp_path):
        f = _archivo(tmp_path)
        sesion = _sesion(f)
        with use_fake_session(sesion) as client:
            r = client.get(f"/ui/pendientes/{f.id}/ignorar/cancelar")
        assert f'id="ignorar-boton-{f.id}"' in r.text and "autofocus" in r.text
        assert f'hx-get="/ui/pendientes/{f.id}/ignorar/confirmar"' in r.text
        assert f.review_dismissed is False and sesion.commit.await_count == 0

    @pytest.mark.parametrize("ruta", ["ignorar/confirmar", "ignorar/cancelar"])
    def test_un_archivo_inexistente_da_404(self, ruta):
        with use_fake_session(FakeSession()) as client:
            assert client.get(f"/ui/pendientes/{uuid4()}/{ruta}").status_code == 404

    def test_la_tarjeta_ya_no_usa_el_dialogo_nativo(self, tmp_path):
        """El botón abre la confirmación integrada, no un `hx-confirm` nativo."""
        tarjeta = (PLANTILLAS / "_tarjeta_pendiente.html").read_text("utf-8")
        assert "hx-confirm" not in tarjeta
        assert '_ignorar_boton.html' in tarjeta and 'id="ignorar-{{ c.file.id }}"' in tarjeta
        f = _archivo(tmp_path)
        with use_fake_session(FakeSession(exec_queue=cola_de([f]))) as client:
            pagina = client.get("/ui/pendientes").text
        assert f'hx-get="/ui/pendientes/{f.id}/ignorar/confirmar"' in pagina
        assert 'href="/ui/pendientes/ignorados"' in pagina and "Ver los ignorados" in pagina


class TestIgnorarEsIdempotenteYNoTocaElArchivo:

    def test_un_doble_envio_no_hace_nada_mas_y_los_bytes_y_la_ruta_se_conservan(self, tmp_path):
        f = _archivo(tmp_path)
        ruta, bytes_antes = Path(f.file_path), Path(f.file_path).read_bytes()
        with use_fake_session(_sesion(f)) as client:
            primero = client.post(f"/ui/pendientes/{f.id}/ignorar")
            segundo = client.post(f"/ui/pendientes/{f.id}/ignorar")
        assert primero.status_code == segundo.status_code == 200
        assert primero.text == segundo.text                  # el mismo recibo, sin efectos extra
        assert f.review_dismissed is True
        assert f.file_path == str(ruta) and ruta.read_bytes() == bytes_antes
        assert f.issue_id is None and f.metadata_ == {"match_status": "unsorted"}


class TestRestaurar:

    def test_restaurar_solo_revierte_review_dismissed(self, tmp_path):
        f = _archivo(tmp_path, review_dismissed=True)
        ruta, bytes_antes = Path(f.file_path), Path(f.file_path).read_bytes()
        sesion = _sesion(f, cola=[FakeExecResult(0)])
        with use_fake_session(sesion) as client:
            r = client.post(f"/ui/pendientes/{f.id}/restaurar")
        assert r.status_code == 200
        assert f.review_dismissed is False and sesion.commit.await_count >= 1
        assert "vuelve a" in r.text and 'href="/ui/pendientes"' in r.text
        assert f.file_path == str(ruta) and ruta.read_bytes() == bytes_antes
        assert f.metadata_ == {"match_status": "unsorted"}
        assert "autofocus" in r.text and 'hx-get="/ui/_nav/estado"' in r.text
        assert '<span id="ignorados-total" hx-swap-oob="true">0</span>' in r.text

    def test_un_doble_envio_de_restaurar_no_hace_nada_mas(self, tmp_path):
        f = _archivo(tmp_path, review_dismissed=True)
        with use_fake_session(_sesion(f, cola=[FakeExecResult(0), FakeExecResult(0)])) as client:
            a = client.post(f"/ui/pendientes/{f.id}/restaurar")
            b = client.post(f"/ui/pendientes/{f.id}/restaurar")
        assert a.text == b.text and f.review_dismissed is False

    def test_si_no_esta_sin_clasificar_no_promete_volver_a_por_revisar(self, tmp_path):
        f = _archivo(tmp_path, review_dismissed=True, metadata_={"match_status": "matched"})
        with use_fake_session(_sesion(f, cola=[FakeExecResult(0)])) as client:
            r = client.post(f"/ui/pendientes/{f.id}/restaurar")
        assert "no entra en" in r.text and "vuelve a" not in r.text

    def test_un_archivo_con_numero_no_se_toca(self, tmp_path):
        f = _archivo(tmp_path, review_dismissed=True, issue_id=uuid4())
        with use_fake_session(_sesion(f, cola=[FakeExecResult(0)])) as client:
            client.post(f"/ui/pendientes/{f.id}/restaurar")
        assert f.review_dismissed is True            # no es un pendiente: la bandeja no lo gestiona

    def test_archivo_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            assert client.post(f"/ui/pendientes/{uuid4()}/restaurar").status_code == 404


class TestBandeja:

    def test_lista_los_ignorados_con_su_total_y_la_accion_de_volver(self, tmp_path):
        a, b = _archivo(tmp_path, "A 01.cbz", review_dismissed=True), _archivo(
            tmp_path, "B 02.cbz", review_dismissed=True)
        cola = [FakeExecResult(2), FakeExecResult([a, b])]
        with use_fake_session(FakeSession(exec_queue=cola)) as c:
            r = c.get("/ui/pendientes/ignorados")
        assert r.status_code == 200 and "Cache-Control" in r.headers
        assert "A 01.cbz" in r.text and "B 02.cbz" in r.text
        assert 'id="ignorados-total">2<' in r.text and "Ignorados 1–2 de" in r.text
        assert f'hx-post="/ui/pendientes/{a.id}/restaurar"' in r.text
        assert "Volver a «Por revisar»" in r.text and "siguen en tu disco" in r.text.lower()

    def test_sin_ignorados_dice_que_no_hay_en_vez_de_una_lista_vacia(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult(0), FakeExecResult([])])) as c:
            r = c.get("/ui/pendientes/ignorados")
        assert r.status_code == 200 and "No hay archivos ignorados" in r.text

    def test_pagina_de_50_con_enlaces_de_anterior_y_siguiente(self, tmp_path):
        fs = [_archivo(tmp_path, f"S {i:03}.cbz", review_dismissed=True) for i in range(3)]
        cola = [FakeExecResult(120), FakeExecResult(fs)]
        with use_fake_session(FakeSession(exec_queue=cola)) as c:
            r = c.get("/ui/pendientes/ignorados?pagina=2")
        assert 'href="/ui/pendientes/ignorados?pagina=1"' in r.text
        assert 'href="/ui/pendientes/ignorados?pagina=3"' in r.text
        assert "Ignorados 51–53 de" in r.text

    def test_un_fallo_de_lectura_da_503_sin_recuentos_a_medias(self):
        class _Rota(FakeSession):
            async def execute(self, _s):
                raise RuntimeError("bd caída")
        with use_fake_session(_Rota()) as c:
            r = c.get("/ui/pendientes/ignorados")
        assert r.status_code == 503 and "No se pudieron leer los ignorados" in r.text

    def test_el_filtro_de_la_bandeja_es_el_que_cuenta_inicio(self):
        """Un solo filtro: si la bandeja e Inicio contaran distinto, «N ignorados» no cuadraría."""
        condiciones = " ".join(str(c) for c in ReviewService._condiciones_ignorados())
        assert "is_missing" in condiciones and "issue_id IS NULL" in condiciones
        assert "review_dismissed" in condiciones
        inicio = (RAIZ / "src" / "zascarr" / "services" / "inicio.py").read_text("utf-8")
        assert ("func.count().filter(presente, File.issue_id.is_(None), "
                "File.review_dismissed.is_(True))") in inicio


def test_el_glosario_define_ignorado_y_prohibe_descartado_para_este_concepto():
    glosario = (RAIZ / "CLAUDE.md").read_text("utf-8")
    fila = next(linea for linea in glosario.splitlines() if linea.startswith("| **ignorado** |"))
    assert "Ignorados" in fila and "«Descartado»" in fila and "copias descartadas" in fila
