"""Servicio app v4 aislado; sin web, auxiliar ni ejecución."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deploy.ops import protocolo_actualizar_v4_ops4 as protocolo
from zascarr.config import get_settings
from zascarr.services.actualizacion_transporte_v4 import (
    CodigoTransporteV4,
    IntercambioInciertoError,
)
from zascarr.services.auth import hash_password
from zascarr.services.autorizacion_actualizacion import (
    PreparacionAutorizacion,
    ResultadoAutorizacion,
)
from zascarr.services.reautenticacion import (
    Reauth,
    ResultadoReauth,
    reiniciar_estado,
)
from zascarr.services.solicitud_actualizacion_v4 import (
    ResultadoSolicitudV4,
    solicitar_actualizacion_v4,
)

CLAVE = bytes(range(32))
AHORA = 1_800_000_000
SETTINGS = SimpleNamespace(auth_mode="password", ops_socket_file="/no/existe.sock")


async def ok(_contrasena, _settings):
    return ResultadoReauth(Reauth.OK)


async def incorrecta(_contrasena, _settings):
    return ResultadoReauth(Reauth.INCORRECTA)


async def bloqueada(_contrasena, _settings):
    return ResultadoReauth(Reauth.BLOQUEADA, hasta_epoch=AHORA + 30)


class Enviar:
    def __init__(self, codigo: CodigoTransporteV4 = CodigoTransporteV4.ACEPTADA) -> None:
        self.codigo = codigo
        self.llamadas: list[tuple] = []

    async def __call__(self, settings, peticion, *, id_, conversar=None):
        self.llamadas.append((settings, peticion, id_, conversar))
        return self.codigo


@pytest.mark.asyncio
async def test_no_habilitada_no_reauth_ni_envia() -> None:
    llamado = []

    async def comprobar(contrasena, settings):
        llamado.append(contrasena)
        return ResultadoReauth(Reauth.OK)

    enviar = Enviar()
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=False, ahora=AHORA, comprobar=comprobar, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.NO_HABILITADA
    assert llamado == [] and enviar.llamadas == []


@pytest.mark.asyncio
async def test_confirmacion_y_auth_mode_none_no_envian() -> None:
    enviar = Enviar()
    for entiendo, settings, esperado in (
        (False, SETTINGS, ResultadoSolicitudV4.CONFIRMACION_REQUERIDA),
        (True, SimpleNamespace(auth_mode="none"), ResultadoSolicitudV4.AUTENTICACION_NO_ACTIVADA),
    ):
        resultado = await solicitar_actualizacion_v4(
            settings, clave=CLAVE, contrasena="clave", entiendo=entiendo,
            habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
        )
        assert resultado.resultado is esperado
    assert enviar.llamadas == []


@pytest.mark.asyncio
@pytest.mark.parametrize("comprobar,esperado", [
    (incorrecta, ResultadoSolicitudV4.CONTRASENA_INCORRECTA),
    (bloqueada, ResultadoSolicitudV4.BLOQUEADA),
    (lambda *_: (_ for _ in ()).throw(RuntimeError()), ResultadoSolicitudV4.NO_DISPONIBLE),
])
async def test_reauth_no_ok_no_envia(comprobar, esperado) -> None:
    enviar = Enviar()
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=comprobar, enviar=enviar,
    )
    assert resultado.resultado is esperado
    assert enviar.llamadas == []


@pytest.mark.asyncio
async def test_exito_construye_v4_y_devuelve_id() -> None:
    enviar = Enviar()
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.ACEPTADA
    assert resultado.id and len(resultado.id) == 32
    _settings, peticion, id_, _ = enviar.llamadas[0]
    assert id_ == resultado.id
    objeto = protocolo.parsear(peticion)
    assert objeto is not None and objeto["id"] == resultado.id
    assert b"prueba" not in peticion and b"password" not in peticion
    assert protocolo.verificar_firma(CLAVE, objeto)


@pytest.mark.asyncio
async def test_clave_invalida_no_envia() -> None:
    enviar = Enviar()
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=b"x" * 31, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.NO_DISPONIBLE
    assert enviar.llamadas == []


@pytest.mark.asyncio
async def test_incertidumbre_no_se_reintenta() -> None:
    enviar = Enviar(CodigoTransporteV4.INCIERTO)
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.INCIERTA
    assert len(enviar.llamadas) == 1


@pytest.mark.asyncio
async def test_fallo_de_construccion_no_envia() -> None:
    enviar = Enviar()

    def construir(*_args, **_kwargs):
        raise ValueError("no se puede construir")

    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, construir=construir, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.NO_DISPONIBLE
    assert enviar.llamadas == []


@pytest.mark.asyncio
async def test_preparacion_inesperada_falla_cerrado() -> None:
    async def preparar(*_args, **_kwargs):
        return PreparacionAutorizacion(ResultadoAutorizacion.PREPARADA)

    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, preparar=preparar, enviar=Enviar(),
    )
    assert resultado.resultado is ResultadoSolicitudV4.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_ahora_invalido_no_llama_a_preparar() -> None:
    llamado = []

    async def preparar(*_args, **_kwargs):
        llamado.append(1)
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_HABILITADA)

    for ahora in (True, -1, 2**63):
        resultado = await solicitar_actualizacion_v4(
            SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
            habilitada=True, ahora=ahora, preparar=preparar, enviar=Enviar(),
        )
        assert resultado.resultado is ResultadoSolicitudV4.NO_DISPONIBLE
    assert llamado == []


@pytest.mark.asyncio
async def test_conversar_se_pasa_al_transporte() -> None:
    enviar = Enviar()
    conversar = object()
    await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
        conversar=conversar,
    )
    assert enviar.llamadas[0][3] is conversar


@pytest.mark.asyncio
async def test_resultado_no_expone_la_contrasena_ni_el_testigo() -> None:
    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="secreto-sintetico", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=incorrecta, enviar=Enviar(),
    )
    texto = repr(resultado)
    assert "secreto-sintetico" not in texto
    assert "pbkdf2" not in texto


@pytest.mark.asyncio
async def test_excepcion_incierta_del_transporte_es_incierta() -> None:
    async def enviar(*_args, **_kwargs):
        raise IntercambioInciertoError

    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.INCIERTA
    assert resultado.id is not None


@pytest.mark.asyncio
async def test_timeout_del_transporte_es_incierto() -> None:
    async def enviar(*_args, **_kwargs):
        raise TimeoutError

    resultado = await solicitar_actualizacion_v4(
        SETTINGS, clave=CLAVE, contrasena="clave", entiendo=True,
        habilitada=True, ahora=AHORA, comprobar=ok, enviar=enviar,
    )
    assert resultado.resultado is ResultadoSolicitudV4.INCIERTA


@pytest.mark.asyncio
async def test_composicion_con_reautenticacion_real() -> None:
    settings = get_settings().model_copy(update={
        "auth_mode": "password",
        "auth_username": "ana",
        "auth_password_hash": hash_password("secreta-sintetica"),
    })
    enviar = Enviar()
    reiniciar_estado()
    try:
        resultado = await solicitar_actualizacion_v4(
            settings, clave=CLAVE, contrasena="secreta-sintetica", entiendo=True,
            habilitada=True, ahora=AHORA, enviar=enviar,
        )
        assert resultado.resultado is ResultadoSolicitudV4.ACEPTADA
        assert len(enviar.llamadas) == 1
    finally:
        reiniciar_estado()


@pytest.mark.asyncio
async def test_contrasena_incorrecta_contra_reauth_real_no_envia() -> None:
    settings = get_settings().model_copy(update={
        "auth_mode": "password",
        "auth_username": "ana",
        "auth_password_hash": hash_password("secreta-sintetica"),
    })
    enviar = Enviar()
    reiniciar_estado()
    try:
        resultado = await solicitar_actualizacion_v4(
            settings, clave=CLAVE, contrasena="incorrecta", entiendo=True,
            habilitada=True, ahora=AHORA, enviar=enviar,
        )
        assert resultado.resultado is ResultadoSolicitudV4.CONTRASENA_INCORRECTA
        assert enviar.llamadas == []
    finally:
        reiniciar_estado()
