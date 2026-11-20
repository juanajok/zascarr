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


def _resultado():
    """Lo que ve quien acaba de lanzar (sondeo de esa misma ejecución)."""
    return _get("/ui/biblioteca/actualizar/estado").text


def test_terminado_con_cambios_da_resumen_y_enlaces():
    _terminado(nuevos_registrados=12, nuevos_a_revisar=3)
    html = _resultado()
    assert "Biblioteca al día" in html and "15 nuevos, 12 a su serie y 3 a «Por revisar»" in html
    assert 'href="/ui/pendientes"' in html and 'href="/ui/auditoria#rescan-biblioteca"' in html


@pytest.mark.parametrize("campos,esperado", [
    ({"nuevos_a_revisar": 27}, "27 nuevos a «Por revisar»"),
    ({"nuevos_registrados": 4}, "4 nuevos a su serie"),
    ({"nuevos_a_revisar": 1}, "1 nuevo a «Por revisar»"),
])
def test_una_parte_que_vale_cero_no_se_pinta(campos, esperado):
    """M3 (Diseño): nunca «27 nuevos, 0 a su serie y 27 a «Por revisar»»."""
    _terminado(**campos)
    html = _resultado()
    assert esperado in html and " 0 a " not in html


def test_terminado_sin_cambios_lo_dice():
    _terminado()
    assert "Tu biblioteca ya estaba al día" in _resultado()


def test_los_desaparecidos_se_anuncian_y_no_contradicen_el_aviso_de_al_dia():
    """B1 (Diseño): «ya estaba al día: nada desaparecido» junto a «1 archivo ya no está» se contradice."""
    _terminado(desaparecidos=2)
    html = _resultado()
    assert "2 archivos ya no están en su sitio" in html and 'href="/ui/no-disponibles"' in html
    assert "nada desaparecido" not in html and "ya estaba al día" not in html


def test_los_reaparecidos_se_cuentan_y_no_se_callan():
    _terminado(reaparecidos=1)
    html = _resultado()
    assert "1 ha vuelto a su sitio" in html
    assert "nada desaparecido" not in html


def test_una_revision_parcial_no_dice_que_esta_al_dia():
    _terminado(no_revisado=True, unreadable=4)
    html = _resultado()
    assert "No se pudo revisar todo" in html
    assert "ya estaba al día" not in html


def test_al_cargar_la_pagina_no_queda_el_aviso_verde_de_una_ejecucion_vieja():
    """B2 (Diseño): el resultado es de la acción, no de la pantalla; recargar horas después no lo repite."""
    _terminado(nuevos_registrados=12, nuevos_a_revisar=3)
    html = _get().text
    assert "Biblioteca al día" not in html and "ya estaba al día" not in html
    assert "Última vez" in html                                        # las líneas sí
    _terminado()
    assert "ya estaba al día" not in _get().text


def test_al_cargar_la_pagina_lo_que_pide_atencion_sigue_con_su_fecha():
    _terminado(desaparecidos=1)
    html = _get().text
    assert "En la última actualización, 1 archivo ya no estaba en su sitio" in html
    _terminado(no_revisado=True)
    assert "En la última actualización no se pudo revisar todo" in _get().text


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
    assert 'id="actualizar-estado"' in r1.text and " autofocus" in r1.text   # el foco pasa a la región (el botón se deshabilita)


def test_el_post_sin_htmx_redirige_a_biblioteca(monkeypatch):
    monkeypatch.setattr(rescan_biblioteca, "iniciar_manual", lambda f: True)
    r = TestClient(app).post("/ui/biblioteca/actualizar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ui/biblioteca"


def test_el_get_no_lanza_nada(monkeypatch):
    monkeypatch.setattr(rescan_biblioteca, "iniciar_manual",
                        lambda f: pytest.fail("un GET no puede lanzar el rescan"))
    assert _get().status_code == 200


def test_cadencias_de_ajustes_y_valor_fijado_por_la_instalacion():
    assert [o["valor"] for o in web.opciones_cadencia(1440)] == [1440, 10080, 0]   # el diario, primero
    assert [o["valor"] for o in web.opciones_cadencia(1440) if o["marcada"]] == [1440]
    extra = web.opciones_cadencia(720)
    assert len(extra) == 4 and extra[-1]["marcada"] and "fijado en la instalación" in extra[-1]["etiqueta"]
    assert "Cada 12 horas" in extra[-1]["etiqueta"]


def test_mensaje_de_guardado_apagado_y_con_proxima():
    assert "Ya no se actualiza sola" in web.mensaje_guardado(0)
    assert web.mensaje_guardado(1440).startswith("Guardado. La próxima será ")


def test_el_sondeo_sin_cambio_no_sustituye_nada():
    """M1 (Diseño): mientras siga «en curso» no se re-emite el texto (un lector no lo repite cada 5 s)."""
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.CORRIENDO
    rescan_biblioteca._estado.iniciado = datetime.now(UTC)
    r = _get("/ui/biblioteca/actualizar/estado?curso=1")
    assert r.status_code == 204 and r.text == ""
    assert r.headers["cache-control"] == "no-store"
    assert "curso=1" in _get().text                                    # el sondeo lo pide con la marca


def test_el_sondeo_al_terminar_si_sustituye_y_deja_el_boton_habilitado():
    _terminado(nuevos_registrados=1)
    r = _get("/ui/biblioteca/actualizar/estado?curso=1")
    assert r.status_code == 200 and "Biblioteca al día" in r.text
    assert 'id="actualizar-boton"' in r.text and "disabled" not in r.text.split('id="actualizar-boton"', 1)[1].split(">", 1)[0]


def test_ningun_fragmento_se_cachea():
    """N-3 (SecOps): todos llevan `Cache-Control: no-store`."""
    for ruta in ("/ui/biblioteca/actualizar", "/ui/biblioteca/actualizar/estado"):
        assert _get(ruta).headers["cache-control"] == "no-store", ruta
    r = TestClient(app).post("/ui/biblioteca/actualizar", headers={"HX-Request": "true"})
    assert r.headers["cache-control"] == "no-store"
    rescan_biblioteca.reiniciar_para_pruebas()


def test_el_foco_lo_recibe_la_region_estable_y_el_sondeo_solo_cambia_su_contenido():
    """M2 (Diseño): el foco no cae en BODY al terminar: lo tiene la región, que no se vuelve a sustituir."""
    rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.CORRIENDO
    rescan_biblioteca._estado.iniciado = datetime.now(UTC)
    html = _get().text
    assert 'hx-target="#actualizar-estado" hx-swap="innerHTML"' in html          # sondeo: solo el interior
    assert 'hx-target="#actualizar-estado" hx-swap="outerHTML"' in html          # formulario: la región, una vez
