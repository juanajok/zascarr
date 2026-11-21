# ruff: noqa: E501
"""F-06/F-07 (SecOps) — estado de la restauración en la interfaz (FR-24/25/29/30/32).

Lo que fijan estas pruebas:

- `ops_host.resolver_restauracion` lee `ops-restaurar.json` (fases, resultado, error, `base_en_su_sitio` y
  `recuentos`) y `omitida.json` con `accion:"restaurar"`, sin pintar nunca una cadena libre del fichero.
- Mientras hay una restauración en marcha: `/estado` no ofrece botones «Restaurar…», el `POST` de restaurar no
  contacta con el auxiliar y el de copias tampoco.
- `/login` avisa («Se restauró una copia…») solo cuando consta `hecha` reciente, sin fecha.
- `config.py` declara el fichero de estado y el compose lo inyecta.
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.models import CodigoOps
from zascarr.services import ops_host, restauracion
from zascarr.services.ops_host import EstadoCopia

AHORA = 1_800_000_000
TS_COPIA = "backup-20260101_120000"
COPIA_DATE = 1_767_225_600  # 2026-01-01 12:00 en Europe/Madrid (epoch del id de la copia)


@pytest.fixture()
def ajustes(tmp_path, monkeypatch):
    estado = tmp_path / "estado"
    estado.mkdir()
    s = get_settings()
    for campo, nombre in (
        ("backup_status_file", "status.json"), ("ops_status_file", "ops-status.json"),
        ("copias_file", "copias.json"), ("omitida_file", "omitida.json"),
        ("ops_restaurar_status_file", "ops-restaurar.json"),
    ):
        monkeypatch.setattr(s, campo, str(estado / nombre))
    monkeypatch.setattr(s, "ops_socket_file", str(tmp_path / "ops.sock"))
    monkeypatch.setattr(s, "ops_key_file", str(tmp_path / "ops.key"))
    (tmp_path / "ops.key").write_text((bytes(range(32))).hex() + "\n")
    return SimpleNamespace(s=s, dir=estado, tmp=tmp_path)


def _escribir(a, nombre: str, datos) -> None:
    (a.dir / nombre).write_text(json.dumps(datos))


def _restaurando(a, *, fase="restaurando", resultado="en_curso", error=None, base=None,
                 actualizado=None, recuentos=None) -> None:
    _escribir(a, "ops-restaurar.json", {
        "schema": 1, "copia": TS_COPIA, "copia_epoch": COPIA_DATE,
        "inicio_epoch": AHORA - 120, "actualizado_epoch": AHORA - 5 if actualizado is None else actualizado,
        "fase": fase, "resultado": resultado, "error": error, "base_en_su_sitio": base,
        "recuentos": recuentos,
    })


# ── lector del estado ────────────────────────────────────────────────────────────────────────────
def test_sin_fichero_no_hay_restauracion(ajustes):
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.SIN_DATOS
    assert not v.en_marcha and v.mensaje == ""


def test_fase_con_la_app_sirviendo_dice_que_zascarr_sigue_funcionando(ajustes):
    _restaurando(ajustes, fase="restaurando")
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.EN_MARCHA and v.en_marcha
    assert "Preparando la copia" in v.mensaje and "sigue funcionando" in v.mensaje
    assert "copia del" in v.mensaje


def test_fase_con_la_app_parada_avisa_de_que_no_responde(ajustes):
    _restaurando(ajustes, fase="cambiando")
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.en_marcha and "Cambiando los datos" in v.mensaje
    assert "dejará de responder" in v.mensaje and "recarga la página" in v.mensaje
    assert "10 minutos" in v.mensaje


def test_en_curso_obsoleto_es_sin_noticias(ajustes):
    _restaurando(ajustes, fase="cambiando", actualizado=AHORA - ops_host.SIN_NOTICIAS_RESTAURAR_S - 1)
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.SIN_NOTICIAS and not v.en_marcha
    assert "No hay noticias de la restauración" in v.mensaje


def test_hecha_usa_recuentos_con_miles_espanoles(ajustes):
    _restaurando(ajustes, fase="arrancando", resultado="hecha", base=True,
                 recuentos={"series": 42, "issues": 1230, "files": 1180})
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.HECHA and not v.en_marcha
    assert "restaurada: 42 series, 1.230 números y 1.180 archivos anotados" in v.mensaje
    assert "Entra con tu contraseña de siempre" in v.mensaje
    assert v.recuentos == {"series": 42, "issues": 1230, "files": 1180}


@pytest.mark.parametrize("error,texto", [
    ("precondition_failed", "no pudo preparar la restauración"),
    ("copia_no_encontrada", "ya no está en el disco"),
    ("copia_no_valida", "está dañada"),
    ("revision_distinta", "otra versión de ZascArr"),
    ("sin_espacio", "No hay sitio en el disco"),
    ("seguridad_ilegible", "no pudo conservar tu configuración de acceso"),
    ("autenticacion_no_activada", "Activa la contraseña"),
    ("restauracion_fallida", "no se pudo cargar"),
    ("copia_previa_fallida", "copia de lo de ahora"),
    ("cambio_fallido", "volvió a como estaba"),
    ("arranque_fallido", "volvió a como estaba"),
    ("recuperacion_fallida", "Avisa a quien instaló ZascArr cuanto antes"),
    ("unexpected", "No se sabe por qué falló"),
    ("lo_que_sea", "No se sabe por qué falló"),
])
def test_fallida_tiene_causa_y_accion_del_catalogo(ajustes, error, texto):
    _restaurando(ajustes, fase="cambiando", resultado="fallida", error=error, base=True)
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.FALLO
    assert texto in v.mensaje


def test_fallida_con_base_fuera_de_su_sitio_lo_dice(ajustes):
    _restaurando(ajustes, resultado="fallida", error="recuperacion_fallida", base=False)
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.base_en_su_sitio is False and "podría no responder" in v.mensaje


def test_omitida_con_accion_restaurar_es_no_arranco(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "accion": "restaurar", "pedida_epoch": AHORA - 60})
    _escribir(ajustes, "omitida.json", {"schema": 1, "accion": "restaurar", "omitida_epoch": AHORA - 50,
                                        "motivo": "operacion_en_curso"})
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.NO_ARRANCO and not v.en_marcha
    assert "había otra tarea en marcha" in v.mensaje


def test_omitida_de_una_copia_no_afecta_a_la_restauracion(ajustes):
    _escribir(ajustes, "omitida.json", {"schema": 1, "omitida_epoch": AHORA - 50,
                                        "motivo": "operacion_en_curso"})
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.SIN_DATOS


def test_aceptada_sin_fichero_de_fases_se_pinta_en_marcha(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "accion": "restaurar", "pedida_epoch": AHORA - 3,
                                            "copia": TS_COPIA, "resultado": "aceptada"})
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.en_marcha and v.estado == ops_host.EstadoRestaurar.EN_MARCHA


def test_ficheros_hostiles_no_se_pintan_y_no_tumban_el_estado(ajustes):
    _restaurando(ajustes, fase="<script>alert(1)</script>", resultado="fallida",
                 error="<b>roto</b>", base="sí")
    vista = ops_host.resolver_restauracion(ajustes.s, AHORA)
    html = json.dumps([vista.estado, vista.mensaje, vista.detalle])
    assert "<script>" not in html and "<b>" not in html
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=True)
    assert v.estado == EstadoCopia.DIARIO                     # el estado de copias no se contamina


def test_el_estado_de_copias_ignora_la_omitida_de_restaurar(ajustes):
    _escribir(ajustes, "omitida.json", {"schema": 1, "accion": "restaurar",
                                        "omitida_epoch": AHORA - 10, "motivo": "operacion_en_curso"})
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=True)
    assert v.estado == EstadoCopia.DIARIO
    assert v.nocturna_omitida == ""


def test_la_restauracion_en_marcha_no_es_una_copia_en_marcha(ajustes):
    _escribir(ajustes, "ops-status.json", {"schema": 1, "accion": "restaurar", "pedida_epoch": AHORA - 3})
    v = ops_host.resolver_estado(ajustes.s, AHORA, disponible=True)
    assert v.estado != EstadoCopia.EN_MARCHA
    assert not v.en_marcha


# ── la interfaz ─────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def cliente(ajustes, monkeypatch):
    from zascarr.main import app
    from zascarr.database import get_db

    monkeypatch.setattr(ops_host, "auxiliar_disponible", lambda s: True)

    async def _db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    yield c, ajustes
    app.dependency_overrides.pop(get_db, None)


def _con_sesion(c, monkeypatch, a):
    """Deja el cliente con una cookie de sesión válida (auth_mode password) para probar el POST."""
    from zascarr.services.auth import COOKIE_NAME, crear_cookie_sesion

    monkeypatch.setattr(a.s, "auth_mode", "password")
    monkeypatch.setattr(a.s, "auth_password_hash", "pbkdf2_sha256$10000$00$" + "11" * 32)
    monkeypatch.setattr(a.s, "secret_key", "secreto-de-pruebas")
    monkeypatch.setattr(a.s, "auth_session_version", 0)
    c.cookies.set(COOKIE_NAME, crear_cookie_sesion("secreto-de-pruebas", 0))


def _estado_render(c, monkeypatch, a):
    from zascarr.web import estado as web_estado

    monkeypatch.setattr(web_estado.disponibilidad, "ultima_comprobacion",
                        AsyncMock(return_value=SimpleNamespace(sin_dato=True)))
    monkeypatch.setattr(web_estado.disponibilidad, "contar_no_disponibles", AsyncMock(return_value=0))
    monkeypatch.setattr(web_estado.cobertura, "calcular", AsyncMock(side_effect=RuntimeError("x")))
    monkeypatch.setattr(restauracion, "revision_actual", AsyncMock(return_value=None))
    return c.get("/estado")


def test_estado_con_restauracion_en_marcha_no_ofrece_botones_restaurar(cliente, monkeypatch):
    c, a = cliente
    _restaurando(a, fase="restaurando")
    _escribir(a, "copias.json", {"schema": 1, "copias": [
        {"id": TS_COPIA, "revision": "0020", "verificada": True, "creada_epoch": COPIA_DATE, "bytes": 1024},
    ]})
    monkeypatch.setattr(restauracion, "revision_actual", AsyncMock(return_value="0020"))
    t = _estado_render(c, monkeypatch, a).text
    assert 'href="/ui/copias/restaurar/' not in t                   # sin botones «Restaurar…»
    assert "Preparando la copia" in t                                # y se ve el estado de la restauración
    assert 'id="restauracion-estado"' in t


def test_estado_anuncia_la_restauracion_hecha(cliente, monkeypatch):
    c, a = cliente
    _restaurando(a, fase="arrancando", resultado="hecha", base=True,
                 recuentos={"series": 1, "issues": 2, "files": 3})
    t = _estado_render(c, monkeypatch, a).text
    assert "restaurada: 1 series, 2 números y 3 archivos anotados" in t


def test_post_de_restaurar_con_otra_restauracion_en_marcha_no_contacta(cliente, monkeypatch):
    c, a = cliente
    _restaurando(a, fase="cambiando")
    monkeypatch.setattr(ops_host, "leer_copias", lambda _s: [{"id": TS_COPIA, "revision": "0020", "verificada": True}])
    monkeypatch.setattr(restauracion, "revision_actual", AsyncMock(return_value="0020"))
    _con_sesion(c, monkeypatch, a)
    reauth = AsyncMock()
    pedir = AsyncMock()
    monkeypatch.setattr(restauracion, "comprobar_contrasena_actual", reauth)
    monkeypatch.setattr(ops_host, "pedir_restaurar", pedir)
    r = c.post("/ui/copias/restaurar", data={"copia": TS_COPIA, "contrasena": "x", "entiendo": "si"})
    assert r.status_code == 200
    assert "otra tarea de mantenimiento" in r.text
    assert not reauth.called and not pedir.called


@pytest.mark.asyncio
async def test_solicitar_comprueba_la_restauracion_en_marcha_antes_de_la_contrasena(ajustes, monkeypatch):
    monkeypatch.setattr(ops_host, "leer_copias", lambda _s: [{"id": TS_COPIA, "revision": "0020", "verificada": True}])
    monkeypatch.setattr(restauracion, "revision_actual", AsyncMock(return_value="0020"))
    monkeypatch.setattr(ajustes.s, "auth_mode", "password")
    _restaurando(ajustes, fase="cambiando")
    reauth = AsyncMock()
    monkeypatch.setattr(restauracion, "comprobar_contrasena_actual", reauth)
    codigo, mensaje = await restauracion.solicitar(
        object(), ajustes.s, copia=TS_COPIA, contrasena="x", entiendo=True)
    assert codigo is CodigoOps.OPERACION_EN_CURSO
    assert not reauth.called


def test_post_de_copias_con_restauracion_en_marcha_no_contacta(cliente, monkeypatch):
    c, a = cliente
    _restaurando(a, fase="cambiando")
    pedir = AsyncMock(return_value=CodigoOps.ACEPTADA)
    monkeypatch.setattr(ops_host, "pedir_copia", pedir)
    r = c.post("/ui/copias/pedir")
    assert r.status_code == 200 and not pedir.called
    assert "restauración" in r.text.lower()
    assert "disabled" in r.text


# ── aviso en /login (FR-32) ─────────────────────────────────────────────────────────────────────
def test_login_avisa_solo_de_una_restauracion_hecha_reciente(ajustes, monkeypatch):
    from zascarr.main import app

    monkeypatch.setattr(ajustes.s, "auth_mode", "password")
    ahora = int(time.time())
    _restaurando(ajustes, resultado="hecha", base=True, actualizado=ahora - 60,
                 recuentos={"series": 1, "issues": 1, "files": 1})
    assert ops_host.aviso_de_login(ajustes.s, ahora) == (
        "Se restauró una copia. Entra con tu contraseña de siempre.")
    t = TestClient(app).get("/login").text
    assert "Se restauró una copia. Entra con tu contraseña de siempre." in t
    assert " de noviembre" not in t and " de enero" not in t        # sin fecha: /login es público


def test_login_no_avisa_si_es_antigua_o_fallida(ajustes, monkeypatch):
    from zascarr.main import app

    monkeypatch.setattr(ajustes.s, "auth_mode", "password")
    ahora = int(time.time())
    _restaurando(ajustes, resultado="hecha", base=True,
                 actualizado=ahora - ops_host.AVISO_LOGIN_S - 1)
    assert ops_host.aviso_de_login(ajustes.s, ahora) is None
    _restaurando(ajustes, resultado="fallida", error="cambio_fallido", base=True)
    assert ops_host.aviso_de_login(ajustes.s, ahora) is None
    t = TestClient(app).get("/login").text
    assert "Se restauró una copia" not in t


# ── configuración (FR-30) ───────────────────────────────────────────────────────────────────────
def test_config_declara_el_fichero_y_el_compose_lo_inyecta():
    raiz = __import__("pathlib").Path(__file__).resolve().parents[1]
    assert "ops_restaurar_status_file" in type(get_settings()).model_fields
    compose = (raiz / "docker-compose.yml").read_text(encoding="utf-8")
    assert "OPS_RESTAURAR_STATUS_FILE=/run/backup-status/ops-restaurar.json" in compose


def test_el_contexto_solo_conserva_las_copias_restaurables():
    from zascarr.web import copias as modulo

    contexto = modulo._contexto(
        modulo.VistaCopias("ok", "Copia hecha"),
        [{"id": "backup-1", "restaurable": True}, {"id": "backup-2", "restaurable": False}],
    )
    assert [c["id"] for c in contexto["copias"]] == ["backup-1"]


# ── UATP-06 D-5: claves nuevas del intento (T-06-06) ───────────────────────────────────────────
def test_las_claves_nuevas_del_intento_no_cambian_la_causa_ni_se_pintan(ajustes):
    """`intento`/`comprobacion`/`copia_version` son aditivas: el lector las ignora (FR-24, D-5)."""
    intento = "a1b2c3d4e5f60718"
    _escribir(ajustes, "ops-restaurar.json", {
        "schema": 1, "intento": intento, "copia": TS_COPIA, "copia_epoch": COPIA_DATE,
        "inicio_epoch": AHORA - 120, "actualizado_epoch": AHORA - 5,
        "fase": "verificando", "resultado": "fallida", "error": "copia_no_valida",
        "comprobacion": "sha256_copia", "base_en_su_sitio": True, "recuentos": None,
        "copia_version": {"head": "a" * 40, "build_sha": "b" * 40,
                          "app_version": "1.15.1", "alembic": "0020"},
    })
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.FALLO
    assert "está dañada" in v.mensaje and "Elige otra" in v.mensaje
    assert v.base_en_su_sitio is True
    visible = json.dumps([v.estado.value if hasattr(v.estado, "value") else v.estado,
                          v.mensaje, v.detalle])
    assert intento not in visible and "sha256_copia" not in visible and "0020" not in visible


@pytest.mark.parametrize("extra", [
    {"intento": 1234567890123456, "comprobacion": ["sha256_copia"],
     "copia_version": "1.15.1"},
    {"intento": "<script>alert(1)</script>", "comprobacion": {"x": "y"},
     "copia_version": {"head": "a" * 40}},
    {"intento": None, "comprobacion": None, "copia_version": None},
])
def test_un_intento_hostil_no_tumba_el_lector_ni_se_pinta(ajustes, extra):
    """Un fichero con tipos erróneos no da 500 ni pinta cadenas libres; se queda en la causa genérica."""
    datos = {
        "schema": 1, "copia": TS_COPIA, "copia_epoch": COPIA_DATE,
        "inicio_epoch": AHORA - 120, "actualizado_epoch": AHORA - 5,
        "fase": "verificando", "resultado": "fallida", "error": "<b>roto</b>",
        "base_en_su_sitio": True, "recuentos": None,
    }
    datos.update(extra)
    _escribir(ajustes, "ops-restaurar.json", datos)
    v = ops_host.resolver_restauracion(ajustes.s, AHORA)
    assert v.estado == ops_host.EstadoRestaurar.FALLO
    assert "<script>" not in v.mensaje and "<b>" not in v.mensaje
    assert "sha256_copia" not in v.mensaje
