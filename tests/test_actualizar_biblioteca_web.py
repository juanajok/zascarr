# ruff: noqa: E501
"""«Actualizar la biblioteca» en Biblioteca (#1160) — pantalla, sin base de datos."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import rescan_biblioteca
from zascarr.services.library_adopter import RescanReport
from zascarr.web import actualizar_biblioteca as web


class _Ejec:
    def scalar_one_or_none(self):
        return None


class _Sesion:
    async def execute(self, _st):
        return _Ejec()


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    rescan_biblioteca.reiniciar_para_pruebas()

    async def _get_db():
        yield _Sesion()
    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(rescan_interval_minutes=1440))
    yield
    app.dependency_overrides.pop(get_db, None)
    rescan_biblioteca.reiniciar_para_pruebas()


def _get(ruta="/ui/biblioteca/actualizar"):
    return TestClient(app).get(ruta)


def _terminado(**campos):
    base = dict(started_at=datetime.now(UTC), disparador="manual")
    base.update(campos)
    informe = RescanReport(**base)
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.TERMINADO
    rescan_biblioteca._estado.informe = informe
    rescan_biblioteca.anotar_ultima(informe.started_at)


def test_biblioteca_pide_el_bloque_al_cargar_y_fuera_del_modo():
    """La franja va en Gestión y en Escaparate: el marcador está antes del `if modo` de la plantilla."""
    from pathlib import Path

    from tests.test_biblioteca_barra import _index
    html = _index("/ui/biblioteca")
    assert 'hx-get="/ui/biblioteca/actualizar"' in html and 'hx-trigger="load"' in html
    fuente = (Path(web.__file__).parent / "templates" / "biblioteca.html").read_text(encoding="utf-8")
    assert fuente.index("/ui/biblioteca/actualizar") < fuente.index('{% if modo == "escaparate" %}')


def test_en_reposo_boton_neutro_garantia_y_lineas():
    r = _get()
    assert r.status_code == 200
    assert "Actualizar la biblioteca" in r.text
    boton = r.text.split("<button", 1)[1].split(">", 1)[0]
    assert "primary" not in boton and "disabled" not in boton
    assert "Mira tu disco: no mueve, no renombra ni borra nada." in r.text
    assert "Todavía no se ha actualizado." in r.text and "Próxima:" in r.text
    assert 'aria-live="polite"' in r.text


def test_sin_palabras_prohibidas_en_superficie():
    texto = _get().text.lower()
    for prohibida in ("rescan", "reescan", "catálogo", "sincroniz", "cerrojo", "importador", "tarea"):
        assert prohibida not in texto, prohibida


def test_apagada_dice_que_no_se_actualiza_sola_y_enlaza_a_ajustes(monkeypatch):
    monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(rescan_interval_minutes=0))
    r = _get()
    assert "No se actualiza sola" in r.text and "/ui/ajustes#actualizar-biblioteca" in r.text
    assert "Próxima:" not in r.text


def test_vencida_dice_en_unos_minutos_y_nunca_una_fecha_pasada():
    rescan_biblioteca.anotar_ultima(datetime.now(UTC) - timedelta(days=3))
    assert "Próxima: en unos minutos" in _get().text


def test_en_curso_deshabilita_sondea_y_avisa_de_la_primera_vez():
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.CORRIENDO
    rescan_biblioteca._estado.iniciado = datetime.now(UTC)
    r = _get()
    assert "Actualizando…" in r.text and "disabled" in r.text
    assert 'hx-trigger="every 5s"' in r.text
    assert "Puedes seguir usando ZascArr" in r.text
    assert "La primera vez tarda más" in r.text
    assert "Próxima:" not in r.text


def test_sin_nada_en_curso_no_sondea():
    assert "every 5s" not in _get().text


def test_el_sondeo_devuelve_solo_el_contenido_y_el_resto_fuera_de_banda():
    r = _get("/ui/biblioteca/actualizar/estado")
    assert 'id="actualizar-contenido"' in r.text
    assert 'id="actualizar-estado"' not in r.text            # la región viva no se sustituye nunca
    assert r.text.count('hx-swap-oob="true"') == 2           # botón y líneas


def test_terminado_con_cambios_da_resumen_y_enlaces():
    _terminado(nuevos_registrados=12, nuevos_a_revisar=3)
    r = _get()
    assert "Biblioteca al día" in r.text and "15 nuevos, 12 a su serie y 3 a «Por revisar»" in r.text
    assert 'href="/ui/pendientes"' in r.text and 'href="/ui/auditoria#rescan-biblioteca"' in r.text


def test_terminado_sin_cambios_lo_dice():
    _terminado()
    assert "Tu biblioteca ya estaba al día" in _get().text


def test_los_desaparecidos_se_anuncian():
    _terminado(desaparecidos=2)
    r = _get()
    assert "2 archivos ya no están en su sitio" in r.text and 'href="/ui/no-disponibles"' in r.text


def test_una_revision_parcial_no_dice_que_esta_al_dia():
    _terminado(no_revisado=True, unreadable=4)
    r = _get()
    assert "No se pudo revisar todo" in r.text
    assert "ya estaba al día" not in r.text


def test_ocupado_es_informacion_y_deja_el_boton_habilitado():
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.OCUPADO
    r = _get()
    assert "ZascArr está importando descargas ahora" in r.text
    boton = r.text.split("<button", 1)[1].split(">", 1)[0]
    assert "disabled" not in boton
    assert "ha fallado" not in r.text.lower() and 'role="alert"' not in r.text


def test_el_error_es_un_aviso_con_alerta_y_enlace_a_estado():
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.ERROR
    r = _get()
    assert "No se ha podido actualizar la biblioteca" in r.text and 'role="alert"' in r.text
    assert 'href="/estado"' in r.text


def test_el_post_lanza_una_vez_y_el_segundo_dice_que_ya_se_esta_actualizando(monkeypatch):
    lanzadas = []

    def _iniciar(fabrica):
        if rescan_biblioteca._estado.en_curso:
            return False
        rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.CORRIENDO
        rescan_biblioteca._estado.iniciado = datetime.now(UTC)
        lanzadas.append(1)
        return True

    monkeypatch.setattr(rescan_biblioteca, "iniciar_manual", _iniciar)
    c = TestClient(app)
    r1 = c.post("/ui/biblioteca/actualizar", headers={"HX-Request": "true"})
    r2 = c.post("/ui/biblioteca/actualizar", headers={"HX-Request": "true"})
    assert len(lanzadas) == 1
    assert "Ya se está actualizando" not in r1.text and "Actualizando tu biblioteca" in r1.text
    assert "Ya se está actualizando" in r2.text and "No se ha lanzado otra" in r2.text
    assert 'tabindex="-1" autofocus' in r1.text               # el foco pasa al mensaje (el botón se deshabilita)


def test_el_post_sin_htmx_redirige_a_biblioteca(monkeypatch):
    monkeypatch.setattr(rescan_biblioteca, "iniciar_manual", lambda f: True)
    r = TestClient(app).post("/ui/biblioteca/actualizar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ui/biblioteca"


def test_el_get_no_lanza_nada(monkeypatch):
    monkeypatch.setattr(rescan_biblioteca, "iniciar_manual",
                        lambda f: pytest.fail("un GET no puede lanzar el rescan"))
    assert _get().status_code == 200


def test_cadencias_de_ajustes_y_valor_fijado_por_la_instalacion():
    assert [o["valor"] for o in web.opciones_cadencia(1440)] == [0, 1440, 10080]
    assert [o["valor"] for o in web.opciones_cadencia(1440) if o["marcada"]] == [1440]
    extra = web.opciones_cadencia(720)
    assert len(extra) == 4 and extra[-1]["marcada"] and "fijado en la instalación" in extra[-1]["etiqueta"]
    assert "Cada 12 horas" in extra[-1]["etiqueta"]


def test_mensaje_de_guardado_apagado_y_con_proxima():
    assert "Ya no se actualiza sola" in web.mensaje_guardado(0)
    assert web.mensaje_guardado(1440).startswith("Guardado. La próxima será ")
