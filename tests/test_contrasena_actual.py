"""BL-OPS3 (#456): cambiar cómo se entra exige la contraseña actual (servicio, router y plantilla).

T-01, T-02, T-04..T-08, T-10 y T-11 de la spec. La verificación real de la contraseña (PBKDF2) se sustituye
por un doble que cuenta llamadas; el hash guardado es un texto cualquiera. Nada de esto toca un secreto real.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog
from fastapi.testclient import TestClient

from tests.test_web_ajustes import FakeSession, _override_get_db
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import auth, seguridad
from zascarr.services.auth import COOKIE_NAME, crear_cookie_sesion, sesion_valida
from zascarr.services.reautenticacion import Reauth, ResultadoReauth
from zascarr.services.seguridad import (
    MENSAJE_ACTUAL_INCORRECTA,
    MENSAJE_COLA_LLENA,
    MENSAJE_FALTA_ACTUAL,
    MENSAJE_NO_COINCIDEN,
    exige_contrasena_actual,
    fijar_seguridad,
    fijar_seguridad_desde_el_equipo,
    mensaje_bloqueada,
)

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
ACTUAL = "la-contrasena-actual-larga"
NUEVA = "otra-contrasena-nueva-larga"


def _s(**kw) -> SimpleNamespace:
    base = dict(auth_mode="password", auth_username="", auth_password_hash="pbkdf2…", base_url="",
                auth_session_version=1)
    base.update(kw)
    return SimpleNamespace(**base)


# ── T-01: la regla pura (AC-04) ──────────────────────────────────────────────────────────────────
class TestMatriz:
    @pytest.mark.parametrize("cambio,esperado", [
        (dict(password=NUEVA), True),                                        # contraseña nueva
        (dict(modo="none"), True),                                           # apagar
        (dict(modo="user_password", usuario="ana"), True),                   # añadir usuario
        (dict(base_url="https://a.org"), True),                              # dirección distinta
        (dict(), False),                                                     # sin ningún cambio
        (dict(password=""), False),                                          # contraseña en blanco: conservar
    ])
    def test_con_contrasena_en_vigor(self, cambio, esperado):
        pedido = dict(modo="password", usuario="", password="", base_url=None) | cambio
        assert exige_contrasena_actual(_s(), **pedido) is esperado

    def test_debilitar_user_password_a_password_la_exige(self):
        s = _s(auth_mode="user_password", auth_username="ana")
        assert exige_contrasena_actual(s, modo="password", usuario="ana", password="", base_url=None)

    def test_cambiar_solo_el_usuario_en_user_password_la_exige(self):
        s = _s(auth_mode="user_password", auth_username="ana")
        assert exige_contrasena_actual(s, modo="user_password", usuario="eva", password="", base_url=None)

    def test_la_barra_final_de_la_direccion_se_normaliza_por_los_dos_lados(self):
        """N-1: el BASE_URL del .env con «/» final y el mismo valor del formulario no piden la actual."""
        s = _s(base_url="https://a.org/")
        assert not exige_contrasena_actual(s, modo="password", usuario="", password="", base_url="https://a.org")
        assert not exige_contrasena_actual(s, modo="password", usuario="", password="", base_url="https://a.org/")
        assert exige_contrasena_actual(s, modo="password", usuario="", password="", base_url="https://b.org")

    @pytest.mark.parametrize("partida", [
        dict(auth_mode="none", auth_password_hash=""),                       # activar por primera vez
        dict(auth_mode="none", auth_password_hash="hash-sobrante"),          # reactivar con hash sobrante
    ])
    def test_sin_contrasena_en_vigor_no_hay_actual_que_pedir(self, partida):
        s = _s(**partida)
        assert not exige_contrasena_actual(s, modo="password", usuario="", password=NUEVA, base_url=None)


# ── T-02: el servicio (AC-01..03, AC-13) ─────────────────────────────────────────────────────────
@pytest.fixture
def servicio(monkeypatch):
    """Ajustes con contraseña en vigor, guardado y reautenticación espiados."""
    ajustes = _s()
    guardados: list[dict] = []
    reauth = SimpleNamespace(resultado=ResultadoReauth(Reauth.OK), llamadas=0)

    class _Svc:
        def __init__(self, _db):
            pass

        async def save(self, cambios):
            guardados.append(cambios)

    async def _comprobar(_password, _settings):
        reauth.llamadas += 1
        return reauth.resultado

    async def _hash(_p):
        return "hash-nuevo"

    limpiar = MagicMock()
    monkeypatch.setattr(seguridad, "get_settings", lambda: ajustes)
    monkeypatch.setattr(seguridad, "RuntimeSettingsService", _Svc)
    monkeypatch.setattr(seguridad, "comprobar_contrasena_actual", _comprobar)
    monkeypatch.setattr(seguridad, "hash_password_async", _hash)
    monkeypatch.setattr(seguridad, "limpiar_cache_basic", limpiar)
    return SimpleNamespace(ajustes=ajustes, guardados=guardados, reauth=reauth, limpiar=limpiar)


class TestServicio:
    async def _nueva(self, **kw):
        datos = dict(modo="password", usuario="", password=NUEVA, base_url=None) | kw
        return await fijar_seguridad(MagicMock(), **datos)

    @pytest.mark.asyncio
    async def test_sin_la_actual_no_se_guarda_nada_y_no_se_sube_la_version(self, servicio):
        """AC-01."""
        r = await self._nueva(password_repetida=NUEVA)
        assert r.error == MENSAJE_FALTA_ACTUAL and r.motivo_rechazo == "falta_actual"
        assert servicio.guardados == [] and servicio.limpiar.call_count == 0
        assert servicio.reauth.llamadas == 0, "sin la actual ni siquiera se intenta comprobar"

    @pytest.mark.asyncio
    async def test_con_la_actual_correcta_se_guarda_y_se_sube_la_version(self, servicio):
        """AC-02."""
        r = await self._nueva(contrasena_actual=ACTUAL, password_repetida=NUEVA)
        assert r.error is None and r.cambia_credenciales and r.cambios == ("contrasena",)
        (guardado,) = servicio.guardados
        assert guardado["auth_session_version"] == 2 and guardado["auth_password_hash"] == "hash-nuevo"
        servicio.limpiar.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resultado,mensaje,motivo", [
        (ResultadoReauth(Reauth.INCORRECTA), MENSAJE_ACTUAL_INCORRECTA, "actual_incorrecta"),
        (ResultadoReauth(Reauth.OCUPADA), MENSAJE_COLA_LLENA, "ocupada"),
    ])
    async def test_actual_incorrecta_u_ocupada_no_guardan_nada(self, servicio, resultado, mensaje, motivo):
        """AC-03, AC-06."""
        servicio.reauth.resultado = resultado
        r = await self._nueva(contrasena_actual="mal", password_repetida=NUEVA)
        assert r.error == mensaje and r.motivo_rechazo == motivo
        assert servicio.guardados == [] and servicio.limpiar.call_count == 0

    @pytest.mark.asyncio
    async def test_bloqueada_dice_la_hora_de_fin_y_no_guarda(self, servicio):
        """AC-05, AC-22."""
        servicio.reauth.resultado = ResultadoReauth(Reauth.BLOQUEADA, 1_700_000_000.0)
        r = await self._nueva(contrasena_actual="bien", password_repetida=NUEVA)
        assert r.motivo_rechazo == "bloqueada" and r.error == mensaje_bloqueada(1_700_000_000.0)
        assert re.search(r"hasta las \d\d:\d\d\.", r.error) and "ZascArr con normalidad" in r.error
        assert servicio.guardados == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pedido", [
        dict(modo="user_password", usuario="", password=""),                # sin usuario (ya hay hash)
        dict(password="corta"),                                              # nueva demasiado corta
        dict(password=NUEVA, password_repetida="otra-distinta"),            # no coinciden (Q-11)
    ])
    async def test_un_formulario_mal_rellenado_no_gasta_intentos(self, servicio, pedido):
        """AC-13: los errores de forma salen ANTES de comprobar la actual."""
        servicio.ajustes.auth_username = ""
        r = await self._nueva(contrasena_actual=ACTUAL, **pedido)
        assert r.error and r.motivo_rechazo is None
        assert servicio.reauth.llamadas == 0 and servicio.guardados == []

    @pytest.mark.asyncio
    async def test_las_dos_contrasenas_nuevas_deben_coincidir(self, servicio):
        r = await self._nueva(contrasena_actual=ACTUAL, password_repetida="distinta-de-la-nueva")
        assert r.error == MENSAJE_NO_COINCIDEN

    @pytest.mark.asyncio
    async def test_sin_cambios_no_se_pide_la_actual(self, servicio):
        """BR-03."""
        r = await fijar_seguridad(MagicMock(), modo="password", usuario="", password="", base_url=None)
        assert r.error is None and not r.cambia_credenciales and r.cambios == ()
        assert servicio.reauth.llamadas == 0

    @pytest.mark.asyncio
    async def test_solo_la_direccion_pide_la_actual_pero_no_sube_la_version(self, servicio):
        servicio.reauth.resultado = ResultadoReauth(Reauth.OK)
        r = await fijar_seguridad(MagicMock(), modo="password", usuario="", password="",
                                  base_url="https://a.org", contrasena_actual=ACTUAL)
        assert r.cambios == ("direccion",) and not r.cambia_credenciales
        assert "auth_session_version" not in servicio.guardados[0]
        assert servicio.reauth.llamadas == 1

    @pytest.mark.asyncio
    async def test_activar_la_contrasena_por_primera_vez_no_pide_la_actual(self, servicio):
        servicio.ajustes.auth_mode, servicio.ajustes.auth_password_hash = "none", ""
        r = await self._nueva(password_repetida=NUEVA)
        assert r.error is None and servicio.reauth.llamadas == 0 and r.cambia_credenciales

    @pytest.mark.asyncio
    async def test_desde_el_equipo_no_pide_la_actual(self, servicio):
        """FR-02, AC-10: el instalador (en el equipo, como root) cambia la contraseña sin la actual."""
        r = await fijar_seguridad_desde_el_equipo(
            MagicMock(), modo="password", usuario="", password=NUEVA, base_url=None)
        assert r.error is None and r.cambia_credenciales
        assert servicio.reauth.llamadas == 0 and servicio.guardados


# ── T-04..T-11: el router y la plantilla ─────────────────────────────────────────────────────────
@pytest.fixture
def con_contrasena(monkeypatch):
    """La instalación tiene una contraseña en vigor; el cliente trae su cookie de sesión. La verificación
    cuenta las llamadas a PBKDF2 (`auth_calls`) y acierta si `.correcta`."""
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {c: getattr(s, c) for c in _ALL_FIELDS}
    s.auth_mode, s.auth_username, s.auth_password_hash = "password", "", "hash-guardado"
    s.secret_key, s.auth_session_version, s.base_url = "s" * 64, 1, ""
    estado = SimpleNamespace(correcta=True, llamadas=0)

    async def _validas(_u, _p, _s_):
        estado.llamadas += 1
        return estado.correcta

    async def _sin_espera():
        return None

    async def _hash(_p):
        return "hash-nuevo"

    monkeypatch.setattr(auth, "credenciales_validas", _validas)
    monkeypatch.setattr(auth, "esperar_retraso", _sin_espera)
    monkeypatch.setattr(seguridad, "hash_password_async", _hash)
    app.dependency_overrides[get_db] = _override_get_db(FakeSession())
    yield estado
    app.dependency_overrides.pop(get_db, None)
    for c, v in originales.items():
        setattr(s, c, v)


def _cliente() -> TestClient:
    c = TestClient(app)
    s = get_settings()
    c.cookies.set(COOKIE_NAME, crear_cookie_sesion(s.secret_key, s.auth_session_version))
    return c


def _post(cliente, **campos):
    datos = {"auth_mode": "password", "auth_username": "", "auth_password": "", "auth_password_actual": "",
             "auth_password_repetida": "", "base_url": ""} | campos
    return cliente.post("/ui/ajustes/guardar/seguridad", data=datos)


def _inputs_de_contrasena(html: str) -> list[str]:
    return re.findall(r"<input[^>]*type=\"password\"[^>]*>", html, flags=re.S)


class TestRouter:
    def test_sin_la_actual_responde_el_texto_y_no_cambia_nada(self, con_contrasena):
        """AC-01 por la web: error al hueco, campo de la actual vaciado e inválido, tarjeta sin recargar."""
        r = _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA)
        assert r.status_code == 200 and MENSAJE_FALTA_ACTUAL in r.text
        assert get_settings().auth_password_hash == "hash-guardado" and get_settings().auth_session_version == 1
        assert 'aria-invalid="true"' in r.text and 'hx-swap-oob="true"' in r.text
        assert "HX-Retarget" not in r.headers and 'id="tarjeta-seguridad"' not in r.text

    def test_con_la_actual_correcta_sustituye_toda_la_tarjeta_y_reemite_la_cookie(self, con_contrasena):
        """AC-02, AC-14, AC-18."""
        r = _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA, auth_password_actual=ACTUAL)
        assert r.status_code == 200
        assert r.headers["HX-Retarget"] == "#tarjeta-seguridad" and r.headers["HX-Reswap"] == "outerHTML"
        assert 'id="tarjeta-seguridad"' in r.text and "las de otros aparatos se han cerrado" in r.text
        assert get_settings().auth_session_version == 2 and get_settings().auth_password_hash == "hash-nuevo"
        assert COOKIE_NAME in r.headers["set-cookie"]
        # la cookie nueva vale con la versión nueva; la vieja (versión 1) ya no vale (la cookie lleva la hora
        # de emisión: se valida, no se compara el texto)
        secreto = get_settings().secret_key
        nueva = r.cookies.get(COOKIE_NAME)
        assert sesion_valida(nueva, secreto, 2) and not sesion_valida(nueva, secreto, 1)
        assert not sesion_valida(crear_cookie_sesion(secreto, 1), secreto, 2)
        assert all("value=" not in i for i in _inputs_de_contrasena(r.text))
        assert "Tu contraseña actual" in r.text                     # ya trae el campo de la actual
        assert 'id="guardar-seguridad"' in r.text                   # el foco vuelve al botón (UX)
        assert 'role="status"' in r.text                            # el éxito se anuncia a lectores de pantalla

    def test_actual_incorrecta_no_cambia_nada(self, con_contrasena):
        """AC-03."""
        con_contrasena.correcta = False
        r = _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA, auth_password_actual="mal")
        assert MENSAJE_ACTUAL_INCORRECTA in r.text and 'aria-invalid="true"' in r.text
        assert get_settings().auth_password_hash == "hash-guardado" and "HX-Retarget" not in r.headers

    def test_bloqueo_tras_cinco_fallos_aunque_la_sexta_sea_correcta(self, con_contrasena):
        """AC-05: sin PBKDF2 durante el bloqueo; se vacían las nuevas además de la actual."""
        con_contrasena.correcta = False
        cliente = _cliente()
        for _ in range(5):
            _post(cliente, auth_password=NUEVA, auth_password_repetida=NUEVA, auth_password_actual="mal")
        llamadas = con_contrasena.llamadas
        con_contrasena.correcta = True
        r = _post(cliente, auth_password=NUEVA, auth_password_repetida=NUEVA, auth_password_actual=ACTUAL)
        assert "Has fallado la contraseña varias veces" in r.text and re.search(r"hasta las \d\d:\d\d", r.text)
        assert con_contrasena.llamadas == llamadas, "el bloqueo no calcula PBKDF2"
        assert 'id="auth-password-actual"' in r.text and 'id="auth-password"' in r.text
        assert 'id="auth-password-repetida"' in r.text                 # las dos nuevas se vacían (AC-19)
        assert get_settings().auth_password_hash == "hash-guardado"

    def test_no_coinciden_se_vacian_las_nuevas_y_no_gasta_intento(self, con_contrasena):
        r = _post(_cliente(), auth_password=NUEVA, auth_password_repetida="otra", auth_password_actual=ACTUAL)
        assert MENSAJE_NO_COINCIDEN in r.text and con_contrasena.llamadas == 0
        assert 'id="auth-password-repetida"' in r.text

    def test_solo_la_direccion_va_al_hueco_y_vacia_los_campos(self, con_contrasena):
        r = _post(_cliente(), base_url="https://a.org", auth_password_actual=ACTUAL)
        assert r.status_code == 200 and "HX-Retarget" not in r.headers and "guardado" in r.text.lower()
        assert 'id="auth-password-actual"' in r.text and get_settings().auth_session_version == 1

    def test_activar_por_primera_vez_trae_el_campo_de_la_actual_y_apagar_lo_quita(self, con_contrasena):
        """AC-18 (d): sin recargar la página el segundo cambio ya encuentra el campo."""
        s = get_settings()
        s.auth_mode, s.auth_password_hash = "none", ""
        r = TestClient(app).post("/ui/ajustes/guardar/seguridad", data={
            "auth_mode": "password", "auth_password": NUEVA, "auth_password_repetida": NUEVA})
        assert r.headers["HX-Retarget"] == "#tarjeta-seguridad" and "Tu contraseña actual" in r.text
        s.auth_mode, s.auth_password_hash, s.auth_session_version = "password", "hash-nuevo", 5
        r2 = _post(_cliente(), auth_mode="none", auth_password_actual=ACTUAL)
        assert r2.headers["HX-Retarget"] == "#tarjeta-seguridad" and "Tu contraseña actual" not in r2.text

    def test_registro_de_rechazos_y_cambios_sin_valores(self, con_contrasena):
        """AC-20."""
        with structlog.testing.capture_logs() as logs:
            _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA)                  # falta
            _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA,
                  auth_password_actual=ACTUAL)                                                     # cambia
        rechazos = [e for e in logs if e["event"] == "ajustes.seguridad_rechazada"]
        cambios = [e for e in logs if e["event"] == "ajustes.seguridad_cambiada"]
        assert [e["motivo"] for e in rechazos] == ["falta_actual"]
        assert [e["cambios"] for e in cambios] == [["contrasena"]]
        volcado = json.dumps(logs, default=str)
        assert NUEVA not in volcado and ACTUAL not in volcado

    def test_el_registro_de_cambio_y_de_rechazo_no_lleva_valores(self, con_contrasena):
        """QA W08/W09 (el más serio: el registro es donde acabaría una contraseña): se piden usuario, contraseña
        nueva, actual y dirección con valores reconocibles y NINGUNO llega a un evento de registro."""
        valores = ("USUARIO-RECONOCIBLE", NUEVA, ACTUAL, "https://reconocible.example.org", "mal-intento-9z")
        get_settings().auth_mode = "user_password"
        get_settings().auth_username = "usuario-viejo"
        con_contrasena.correcta = False
        with structlog.testing.capture_logs() as logs:
            _post(_cliente(), auth_mode="user_password", auth_username=valores[0], auth_password=valores[1],
                  auth_password_repetida=valores[1], auth_password_actual=valores[4], base_url=valores[3])
            con_contrasena.correcta = True
            _post(_cliente(), auth_mode="user_password", auth_username=valores[0], auth_password=valores[1],
                  auth_password_repetida=valores[1], auth_password_actual=ACTUAL, base_url=valores[3])
        eventos = [e["event"] for e in logs]
        assert "ajustes.seguridad_rechazada" in eventos and "ajustes.seguridad_cambiada" in eventos
        volcado = json.dumps(logs, default=str)
        for valor in valores:
            assert valor not in volcado, f"un valor del formulario llegó al registro: {valor!r}"
        cambiada = next(e for e in logs if e["event"] == "ajustes.seguridad_cambiada")
        assert set(cambiada["cambios"]) == {"contrasena", "usuario", "direccion"}

    @pytest.mark.parametrize("campo", ["auth_password", "auth_password_actual", "auth_username", "base_url"])
    def test_el_centinela_no_aparece_en_ninguna_respuesta_ni_en_el_registro(self, con_contrasena, campo):
        """AC-07, contra la ruta real y la versión de FastAPI instalada: nunca un 422 que repita lo escrito."""
        centinela = f"CENTINELA-{campo}-ñ-9f3a"
        cliente = _cliente()
        respuestas = []
        with structlog.testing.capture_logs() as logs:
            respuestas.append(_post(cliente, **{campo: centinela}))                       # modo válido
            respuestas.append(_post(cliente, **{campo: centinela, "auth_mode": "lo-que-sea"}))   # 400
            respuestas.append(cliente.post("/ui/ajustes/guardar/seguridad", data={campo: centinela}))  # sin modo
            respuestas.append(cliente.post("/ui/ajustes/guardar/seguridad",
                                           data={"auth_mode": ["password", "none"], campo: [centinela, centinela]}))
            respuestas.append(_post(cliente, **{campo: centinela * 400}))                 # 10 KB
            respuestas.append(cliente.post("/ui/ajustes/guardar/seguridad", json={campo: centinela}))
            respuestas.append(cliente.post(
                "/ui/ajustes/guardar/seguridad", content=f"--x\r\nContent-Disposition: form-data; name=\"{campo}\"\r\n\r\n{centinela}",
                headers={"Content-Type": "multipart/form-data; boundary=x"}))
            respuestas.append(cliente.post(
                "/ui/ajustes/guardar/seguridad", content=f"{campo}={centinela}",
                headers={"Content-Type": "multipart/form-data"}))                         # sin boundary
        for r in respuestas:
            assert r.status_code != 422, r.text[:200]
            assert centinela not in r.text, f"{campo}: el centinela se repite en una respuesta ({r.status_code})"
        assert centinela not in json.dumps(logs, default=str)

    def test_el_modo_ausente_es_400_con_texto_fijo(self, con_contrasena):
        r = _cliente().post("/ui/ajustes/guardar/seguridad", data={})
        assert r.status_code == 400 and r.json()["detail"] == "Modo de autenticación no reconocido"


class TestPlantilla:
    def test_con_contrasena_en_vigor_el_campo_va_antes_de_guardar_y_tras_el_detalle_tecnico(self, con_contrasena):
        """AC-09, AC-19."""
        html = _cliente().get("/ui/ajustes").text
        tarjeta = html[html.index('id="tarjeta-seguridad"'):]
        tarjeta = tarjeta[:tarjeta.index("</fieldset>")]
        assert "Tu contraseña actual" in tarjeta and 'autocomplete="current-password"' in tarjeta
        assert tarjeta.index("Detalle técnico") < tarjeta.index("Tu contraseña actual") < tarjeta.index(">Guardar<")
        assert "<label>Contraseña nueva" in tarjeta and "Repite la contraseña nueva" in tarjeta
        nueva = next(i for i in _inputs_de_contrasena(tarjeta) if 'name="auth_password"' in i)
        assert 'autocomplete="new-password"' in nueva           # el gestor no rellena la antigua
        assert 'aria-live="polite"' in tarjeta and "¿La has olvidado?" in tarjeta
        # UX (foco): al sustituir la tarjeta el botón se elimina; htmx restaura el foco al elemento con el MISMO
        # id, así que el botón lleva uno estable (sin él el foco volvería a BODY)
        assert 'id="guardar-seguridad"' in tarjeta
        assert 'aria-describedby="resultado-seguridad"' in tarjeta       # el campo de la actual apunta al resultado
        assert all("value=" not in i for i in _inputs_de_contrasena(tarjeta))

    def test_sin_contrasena_en_vigor_no_aparece_el_campo(self):
        html = TestClient(app).get("/ui/ajustes").text
        tarjeta = html[html.index('id="tarjeta-seguridad"'):]
        tarjeta = tarjeta[:tarjeta.index("</fieldset>")]
        assert "Tu contraseña actual" not in tarjeta and "auth_password_actual" not in tarjeta


# ── Pruebas estáticas (AC-08, AC-12; SecOps A-1) ──────────────────────────────────────────────────
CLAVES_DE_ACCESO = {"auth_mode", "auth_username", "auth_password_hash", "auth_session_version",
                    "secret_key", "base_url"}
#: Dónde puede escribirse el acceso: el servicio, el rehash de `/login`, el instalador y el propio servicio de
#: ajustes en tiempo de ejecución (`ensure_secret_key`).
ESCRIBEN_ACCESO = {"services/seguridad.py", "web/auth.py", "cli/seguridad.py", "services/runtime_settings.py"}
#: `.save(...)` de Pillow, que no es el servicio de ajustes.
SAVE_DE_IMAGENES = {"utils/cover.py", "utils/portada_rar.py"}
ESCRITOR_PRIVADO = {"_guardar_seguridad", "_comprobar_actual", "_comprobar_forma"}


def _saves_sospechosos(fuente: str, ruta: str) -> list[int]:
    """Líneas de `.save(...)` que pueden escribir claves de acceso desde un sitio NO permitido: un diccionario
    literal con alguna de esas claves (o con `**`), o cualquier primer argumento que no sea un diccionario
    literal (una variable `cambios`, una llamada…), que es como se evadía la versión anterior de la prueba."""
    if ruta in ESCRIBEN_ACCESO:
        return []
    marcadas = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "save" and nodo.args):
            continue
        primero = nodo.args[0]
        if isinstance(primero, ast.Dict):
            llaves = [k.value if isinstance(k, ast.Constant) else None for k in primero.keys]
            if None in llaves or set(llaves) & CLAVES_DE_ACCESO:
                marcadas.append(nodo.lineno)
        elif ruta not in SAVE_DE_IMAGENES:
            marcadas.append(nodo.lineno)
    return marcadas


def _usos_del_escritor_privado(fuente: str) -> list[str]:
    """Nombres del escritor privado de seguridad usados en este código: como nombre, atributo o importación
    (con o sin alias)."""
    usos = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Name) and nodo.id in ESCRITOR_PRIVADO:
            usos.append(nodo.id)
        elif isinstance(nodo, ast.Attribute) and nodo.attr in ESCRITOR_PRIVADO:
            usos.append(nodo.attr)
        elif isinstance(nodo, ast.ImportFrom):
            usos += [a.name for a in nodo.names if a.name in ESCRITOR_PRIVADO]
    return usos


class TestEstaticas:
    def test_los_parametros_del_router_son_str_form_vacio_sin_restricciones(self):
        """AC-08: ninguna restricción de campo (con una incumplida el 422 devolvería lo escrito)."""
        from zascarr.web.ajustes import guardar_seguridad
        esperados = {"auth_mode", "auth_username", "auth_password", "auth_password_actual",
                     "auth_password_repetida", "base_url"}
        encontrados = {}
        for nombre, p in inspect.signature(guardar_seguridad).parameters.items():
            if nombre in esperados:
                encontrados[nombre] = p
        assert set(encontrados) == esperados
        for nombre, p in encontrados.items():
            assert p.annotation in (str, "str"), nombre
            assert p.default.default == "" and not p.default.metadata, f"{nombre} lleva restricciones"

    def test_solo_el_instalador_usa_fijar_seguridad_desde_el_equipo_y_el_router_no_la_importa(self):
        """AC-12 (b)."""
        usuarios = []
        for ruta in RAIZ.rglob("*.py"):
            texto = ruta.read_text(encoding="utf-8")
            if "fijar_seguridad_desde_el_equipo" in texto:
                usuarios.append(ruta.relative_to(RAIZ).as_posix())
        assert sorted(usuarios) == ["cli/seguridad.py", "services/seguridad.py"]
        assert "desde_el_equipo" not in (RAIZ / "web" / "ajustes.py").read_text(encoding="utf-8")

    def test_el_escritor_privado_solo_aparece_en_el_servicio(self):
        """SecOps A-1 (b): el escritor privado que no pide la actual y sus comprobaciones solo se nombran en
        `services/seguridad.py`, ni como nombre, ni como atributo, ni importado (con o sin alias)."""
        fuera = {}
        for ruta in RAIZ.rglob("*.py"):
            rel = ruta.relative_to(RAIZ).as_posix()
            if rel == "services/seguridad.py":
                continue
            usos = _usos_del_escritor_privado(ruta.read_text(encoding="utf-8"))
            if usos:
                fuera[rel] = usos
        assert fuera == {}, f"el escritor privado de seguridad se usa fuera del servicio: {fuera}"

    def test_solo_los_sitios_previstos_escriben_las_claves_de_acceso(self):
        """AC-12 (a), SecOps A-1 (a): nada fuera de la lista guarda claves de acceso, ni con un diccionario
        literal ni con una variable (`cambios = {...}; save(cambios)`)."""
        hallados = {}
        for ruta in RAIZ.rglob("*.py"):
            rel = ruta.relative_to(RAIZ).as_posix()
            lineas = _saves_sospechosos(ruta.read_text(encoding="utf-8"), rel)
            if lineas:
                hallados[rel] = lineas
        assert hallados == {}, f".save(...) a revisar fuera de los sitios previstos: {hallados}"

    # el análisis es la prueba: se comprueba con el código malo que SecOps usó para evadirlo
    @pytest.mark.parametrize("fuente", [
        'await RuntimeSettingsService(db).save({"auth_mode": "none"})',
        'cambios = {"auth_mode": "none"}\nawait RuntimeSettingsService(db).save(cambios)',     # variable
        'await RuntimeSettingsService(db).save({**extra})',                                    # desempaquetado
        'await servicio.save(construir())',                                                    # llamada
        'await svc.save({"secret_key": "x"})',
        'await svc.save({"base_url": ""})',
    ])
    def test_el_analisis_marca_las_escrituras_que_se_evadian(self, fuente):
        assert _saves_sospechosos(fuente, "web/otra_ruta.py") == [fuente.count("\n") + 1]

    @pytest.mark.parametrize("fuente", [
        'await RuntimeSettingsService(db).save({"prowlarr_url": "x"})',                        # otras claves
        'await RuntimeSettingsService(db).save({"amule_enabled": True, "amule_url": "u"})',
    ])
    def test_el_analisis_no_marca_las_escrituras_de_otras_claves(self, fuente):
        assert _saves_sospechosos(fuente, "web/ajustes.py") == []

    def test_el_analisis_marca_el_uso_del_escritor_privado_aunque_sea_con_alias(self):
        for fuente in ("from zascarr.services.seguridad import _guardar_seguridad as g",
                       "from zascarr.services import seguridad\nseguridad._guardar_seguridad(db)",
                       "_comprobar_actual(settings)"):
            assert _usos_del_escritor_privado(fuente), fuente
        assert _usos_del_escritor_privado("from zascarr.services.seguridad import fijar_seguridad") == []


class TestCli:
    @pytest.mark.asyncio
    async def test_fijar_contrasena_del_instalador_sigue_sin_pedir_la_actual(self, monkeypatch):
        """AC-10: aunque haya una contraseña en vigor, el instalador (en el equipo) la restablece sin la actual."""
        from zascarr.cli import seguridad as cli
        usadas = []

        async def _equipo(db, **kw):
            usadas.append(kw)
            return SimpleNamespace(error=None, aviso=None)

        monkeypatch.setattr(cli, "fijar_seguridad_desde_el_equipo", _equipo)
        codigo, _msg, _aviso = await cli.fijar_contrasena(MagicMock(), "una-contrasena-nueva-larga")
        assert codigo == cli.OK and usadas and usadas[0]["password"] == "una-contrasena-nueva-larga"
