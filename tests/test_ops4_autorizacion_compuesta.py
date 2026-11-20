"""Composición app-side reauth→autorización y cadena host→consumo durable.

Se ejecuta solo en pruebas: la actualización sigue deshabilitada y este archivo no
conecta la UI, el auxiliar, `main.py` ni ninguna unidad. El transporte real
(petición v4, envío único, reconciliación de resultado incierto) queda NOT RUN:
aquí se prueba la composición, la emisión y la verificación con el registro
durable, no el envío.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from deploy.ops import registro_repeticiones_ops4 as registro
from deploy.ops.verificador_autorizacion_ops4 import (
    CodigoAutorizacion,
    verificar_autorizacion,
)
from zascarr.config import Settings
from zascarr.services import autorizacion_actualizacion as emisor
from zascarr.services.reautenticacion import Reauth, ResultadoReauth

CLAVE = bytes(range(32))
#: Clave de otro protocolo, del tamaño de `ops.key`; no sirve para esta ruta.
OTRA_CLAVE = bytes(range(32, 64))
ID = "a" * 32
ID_OTRO = "b" * 32
AHORA = 1_800_000_000
_ID_HEX = re.compile(r"[0-9a-f]{32}\Z")


def settings(auth_mode: str = "password") -> Settings:
    return Settings(auth_mode=auth_mode, auth_username="tester", auth_password_hash="")


class ComprobarFalso:
    """Doble del servicio compartido de reautenticación de OPS3."""

    def __init__(self, respuesta: object) -> None:
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, Settings]] = []

    async def __call__(self, contrasena: str, settings_: Settings) -> object:
        self.llamadas.append((contrasena, settings_))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


class EmitirFalso:
    """Doble del emisor puro: registra el orden y delega en el real si se pide."""

    def __init__(self, orden: list[str] | None = None) -> None:
        self.orden = orden if orden is not None else []
        self.llamadas: list[dict[str, object]] = []

    def __call__(self, **kwargs) -> bytes:
        self.orden.append("emitir")
        self.llamadas.append(kwargs)
        return emisor.crear_autorizacion(**kwargs)


def ok() -> ComprobarFalso:
    return ComprobarFalso(ResultadoReauth(Reauth.OK))


async def preparar(
    *,
    comprobar: object | None = None,
    emitir: object | None = None,
    ajustes: Settings | None = None,
    generar_id: object | None = None,
    usar_csprng: bool = False,
    **cambios: object,
) -> emisor.PreparacionAutorizacion:
    datos: dict[str, object] = {
        "clave": CLAVE,
        "contrasena": "actual",
        "entiendo": True,
        "habilitada": True,
        "ahora": AHORA,
    }
    if not usar_csprng:
        datos["generar_id"] = generar_id if generar_id is not None else (lambda: ID)
    datos.update(cambios)
    return await emisor.preparar_autorizacion(
        ajustes if ajustes is not None else settings(),
        comprobar=comprobar if comprobar is not None else ok(),
        emitir=emitir if emitir is not None else emisor.crear_autorizacion,
        **datos,
    )


@pytest.fixture
def directorio_autorizaciones(tmp_path: Path):
    ruta = tmp_path / "autorizaciones"
    ruta.mkdir(mode=0o700)
    fd = os.open(ruta, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield ruta, fd
    finally:
        os.close(fd)


# ── Puerta, validación y auth_mode: nada llega a reautenticar ─────────────────


@pytest.mark.parametrize("habilitada", [False, None, 1, "si", 0])
async def test_sin_habilitar_falla_cerrado_sin_reautenticar(habilitada) -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(
        comprobar=comprobar, emitir=emitir, habilitada=habilitada,
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_HABILITADA
    assert resultado.id is None
    assert resultado.autorizacion is None
    assert comprobar.llamadas == []
    assert emitir.llamadas == []


async def test_la_funcion_esta_deshabilitada_por_defecto() -> None:
    # Sin `habilitada=True` explícito no se reautentica ni se emite: la
    # actualización sigue deshabilitada mientras no haya una puerta separada.
    comprobar = ok()
    resultado = await emisor.preparar_autorizacion(
        settings(), clave=CLAVE, contrasena="actual", entiendo=True,
        comprobar=comprobar,
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_HABILITADA
    assert resultado.autorizacion is None
    assert comprobar.llamadas == []


async def test_la_puerta_es_lo_primero() -> None:
    # Ni siquiera la contraseña se mira: la función deshabilitada no valida nada.
    comprobar = ok()
    resultado = await preparar(
        comprobar=comprobar, contrasena=None, entiendo=None, habilitada=False,
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_HABILITADA
    assert comprobar.llamadas == []


@pytest.mark.parametrize("entiendo", [False, None, 1, "si", "true"])
async def test_confirmacion_requerida_no_reautentica(entiendo) -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(comprobar=comprobar, emitir=emitir, entiendo=entiendo)
    assert resultado.resultado is emisor.ResultadoAutorizacion.CONFIRMACION_REQUERIDA
    assert comprobar.llamadas == []
    assert emitir.llamadas == []


@pytest.mark.parametrize("contrasena", [
    None, 123, b"actual", "", "x" * 513, "\ud800",
])
async def test_contrasena_invalida_no_reautentica(contrasena) -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(comprobar=comprobar, emitir=emitir, contrasena=contrasena)
    assert resultado.resultado is emisor.ResultadoAutorizacion.CONTRASENA_INVALIDA
    assert comprobar.llamadas == []
    assert emitir.llamadas == []


async def test_auth_mode_none_no_reautentica() -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(
        comprobar=comprobar, emitir=emitir, ajustes=settings("none"),
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.AUTENTICACION_NO_ACTIVADA
    assert comprobar.llamadas == []
    assert emitir.llamadas == []


async def test_auth_mode_no_soportado_falla_cerrado() -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(
        comprobar=comprobar, emitir=emitir, ajustes=settings("otro"),
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_DISPONIBLE
    assert comprobar.llamadas == []
    assert emitir.llamadas == []


# ── Reautenticación: solo Reauth.OK llega a la emisión ───────────────────────


@pytest.mark.parametrize(("respuesta", "esperado", "hasta"), [
    (ResultadoReauth(Reauth.INCORRECTA),
     emisor.ResultadoAutorizacion.CONTRASENA_INCORRECTA, None),
    (ResultadoReauth(Reauth.OCUPADA), emisor.ResultadoAutorizacion.OCUPADA, None),
    (ResultadoReauth(Reauth.BLOQUEADA, 1_800_000_500.0),
     emisor.ResultadoAutorizacion.BLOQUEADA, 1_800_000_500.0),
    (RuntimeError("reauth caída"), emisor.ResultadoAutorizacion.NO_DISPONIBLE, None),
    (None, emisor.ResultadoAutorizacion.NO_DISPONIBLE, None),
    (object(), emisor.ResultadoAutorizacion.NO_DISPONIBLE, None),
    ("ok", emisor.ResultadoAutorizacion.NO_DISPONIBLE, None),
])
async def test_cada_resultado_no_ok_deniega_sin_emitir(respuesta, esperado, hasta) -> None:
    comprobar, emitir = ComprobarFalso(respuesta), EmitirFalso()
    resultado = await preparar(comprobar=comprobar, emitir=emitir)
    assert resultado.resultado is esperado
    assert resultado.id is None
    assert resultado.autorizacion is None
    assert resultado.hasta_epoch == hasta
    assert len(comprobar.llamadas) == 1
    assert emitir.llamadas == []


async def test_orden_reauth_antes_de_emitir() -> None:
    orden: list[str] = []

    class ReauthObservada(ComprobarFalso):
        async def __call__(self, contrasena, settings_):
            orden.append("reauth")
            return await super().__call__(contrasena, settings_)

    comprobar, emitir = ReauthObservada(ResultadoReauth(Reauth.OK)), EmitirFalso(orden)
    resultado = await preparar(comprobar=comprobar, emitir=emitir)
    assert orden == ["reauth", "emitir"]
    assert resultado.resultado is emisor.ResultadoAutorizacion.PREPARADA
    assert len(comprobar.llamadas) == 1
    assert comprobar.llamadas[0][0] == "actual"
    assert comprobar.llamadas[0][1].auth_mode == "password"


@pytest.mark.parametrize("auth_mode", ["password", "user_password"])
async def test_con_ok_emite_una_sola_vez(auth_mode: str) -> None:
    comprobar, emitir = ok(), EmitirFalso()
    resultado = await preparar(
        comprobar=comprobar, emitir=emitir, ajustes=settings(auth_mode),
    )
    assert resultado.resultado is emisor.ResultadoAutorizacion.PREPARADA
    assert isinstance(resultado.autorizacion, bytes)
    assert len(emitir.llamadas) == 1
    token = resultado.autorizacion
    assert b'"accion":"actualizar"' in token
    assert b"prueba" not in token.lower()
    assert b"password" not in token.lower()
    assert b"pbkdf2" not in token.lower()


# ── Clave dedicada recibida como argumento, ID CSPRNG y fallos cerrados ──────


@pytest.mark.parametrize("clave", [
    b"x" * 31, b"x" * 33, None, "x" * 32, bytearray(32), OTRA_CLAVE + b"x",
])
async def test_clave_invalida_no_emite(clave) -> None:
    emitir = EmitirFalso()
    resultado = await preparar(clave=clave, emitir=emitir)
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_DISPONIBLE
    assert resultado.id is None
    assert resultado.autorizacion is None
    assert emitir.llamadas == []


async def test_otra_clave_de_32_bytes_emite_con_ella_no_con_ops_key() -> None:
    # La composición no elige ni lee clave: usa exactamente la recibida.
    resultado = await preparar(clave=OTRA_CLAVE)
    assert resultado.resultado is emisor.ResultadoAutorizacion.PREPARADA
    verificado = verificar_autorizacion(
        resultado.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=lambda _: True, id_esperado=resultado.id,
    )
    assert verificado is CodigoAutorizacion.INVALIDA


async def test_id_csprng_unico_y_ligado_al_testigo() -> None:
    primero = await preparar(usar_csprng=True)
    segundo = await preparar(usar_csprng=True)
    assert primero.resultado is emisor.ResultadoAutorizacion.PREPARADA
    assert segundo.resultado is emisor.ResultadoAutorizacion.PREPARADA
    ids = [primero.id, segundo.id]
    assert all(isinstance(id_, str) and _ID_HEX.fullmatch(id_) for id_ in ids)
    assert ids[0] != ids[1]
    for preparada in (primero, segundo):
        assert b'"id":"' + preparada.id.encode() + b'"' in preparada.autorizacion


async def test_ttl_por_defecto_de_60() -> None:
    resultado = await preparar()
    verificado = verificar_autorizacion(
        resultado.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=lambda _: True, id_esperado=resultado.id,
    )
    assert verificado is CodigoAutorizacion.ACEPTADA
    assert b'"expira":1800000060' in resultado.autorizacion


@pytest.mark.parametrize("generar_id", [
    lambda: "A" * 32, lambda: "a" * 31, lambda: "../" + "a" * 29, lambda: None,
    lambda: 1 / 0,
])
async def test_generador_de_id_invalido_falla_cerrado(generar_id) -> None:
    emitir = EmitirFalso()
    resultado = await preparar(generar_id=generar_id, emitir=emitir)
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_DISPONIBLE
    assert resultado.id is None
    assert emitir.llamadas == []


class EmitirQueRevienta:
    def __call__(self, **_kwargs) -> bytes:
        raise RuntimeError("fallo de emisión")


@pytest.mark.parametrize("emitir", [
    EmitirQueRevienta(), lambda **_kw: b"", lambda **_kw: "texto",
    lambda **_kw: b"x" * 2049,
])
async def test_emision_dudosa_falla_cerrada(emitir) -> None:
    resultado = await preparar(emitir=emitir)
    assert resultado.resultado is emisor.ResultadoAutorizacion.NO_DISPONIBLE
    assert resultado.id is None
    assert resultado.autorizacion is None


async def test_sin_secretos_en_el_resultado() -> None:
    contrasena = "contrasena-muy-secreta-123"
    resultado = await preparar(contrasena=contrasena)
    texto = repr(resultado) + str(resultado)
    assert contrasena not in texto
    assert resultado.autorizacion is not None
    assert resultado.autorizacion.decode("utf-8") not in texto


async def test_el_mismo_intento_no_se_reemite_ni_reutiliza_el_id() -> None:
    emitir = EmitirFalso()
    primera = await preparar(emitir=emitir, usar_csprng=True)
    segunda = await preparar(emitir=emitir, usar_csprng=True)
    assert len(emitir.llamadas) == 2  # dos intentos distintos: sin reintento ni reemisión
    assert primera.id != segunda.id
    assert emitir.llamadas[0]["id_"] == primera.id
    assert emitir.llamadas[1]["id_"] == segunda.id


# ── Cadena completa: composición → verificador → registro durable ────────────


async def test_e2e_aceptada_una_vez_y_repetida_con_registro_durable(
    directorio_autorizaciones,
) -> None:
    ruta, fd = directorio_autorizaciones
    preparada = await preparar()
    reclamar = registro.crear_reclamador_durable(fd)
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=reclamar, id_esperado=preparada.id,
    ) is CodigoAutorizacion.ACEPTADA
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=reclamar, id_esperado=preparada.id,
    ) is CodigoAutorizacion.REPETIDA
    assert (ruta / f"{registro.PREFIJO_AUTORIZACION}{preparada.id}").exists()
    assert list(ruta.iterdir()) == [
        ruta / f"{registro.PREFIJO_AUTORIZACION}{preparada.id}"
    ]


async def test_e2e_id_esperado_distinto_no_consume(directorio_autorizaciones) -> None:
    ruta, fd = directorio_autorizaciones
    preparada = await preparar()
    consumos: list[str] = []

    def reclamar(id_: str) -> bool:
        consumos.append(id_)
        return registro.reclamar_autorizacion(id_, directorio_fd=fd)

    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=reclamar, id_esperado=ID_OTRO,
    ) is CodigoAutorizacion.INVALIDA
    assert consumos == []
    assert list(ruta.iterdir()) == []
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=reclamar, id_esperado=preparada.id,
    ) is CodigoAutorizacion.ACEPTADA
    assert consumos == [preparada.id]


async def test_e2e_testigo_con_otra_clave_no_consume(directorio_autorizaciones) -> None:
    ruta, fd = directorio_autorizaciones
    preparada = await preparar()
    assert verificar_autorizacion(
        preparada.autorizacion, clave=OTRA_CLAVE, ahora=AHORA,
        reclamar_uso=registro.crear_reclamador_durable(fd),
        id_esperado=preparada.id,
    ) is CodigoAutorizacion.INVALIDA
    assert list(ruta.iterdir()) == []


async def test_e2e_reauth_fallida_no_produce_testigo_ni_marca(
    directorio_autorizaciones,
) -> None:
    ruta, _fd = directorio_autorizaciones
    preparada = await preparar(
        comprobar=ComprobarFalso(ResultadoReauth(Reauth.INCORRECTA)),
    )
    assert preparada.autorizacion is None
    assert preparada.id is None
    assert list(ruta.iterdir()) == []


async def test_e2e_replay_tras_reapertura_y_purga_de_vistos(
    directorio_autorizaciones, tmp_path: Path,
) -> None:
    ruta, fd = directorio_autorizaciones
    preparada = await preparar()
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=registro.crear_reclamador_durable(fd),
        id_esperado=preparada.id,
    ) is CodigoAutorizacion.ACEPTADA
    # Proceso nuevo: reabre el directorio y ve la marca durable.
    nuevo_fd = os.open(ruta, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert verificar_autorizacion(
            preparada.autorizacion, clave=CLAVE, ahora=AHORA,
            reclamar_uso=registro.crear_reclamador_durable(nuevo_fd),
            id_esperado=preparada.id,
        ) is CodigoAutorizacion.REPETIDA
    finally:
        os.close(nuevo_fd)
    # La marca v3 de `vistos` no satisface ni reabre la autorización.
    vistos = tmp_path / "vistos"
    vistos.mkdir()
    (vistos / preparada.id).write_text("1800000000", encoding="ascii")
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=registro.crear_reclamador_durable(fd),
        id_esperado=preparada.id,
    ) is CodigoAutorizacion.REPETIDA
    for entrada in vistos.iterdir():
        entrada.unlink()
    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=registro.crear_reclamador_durable(fd),
        id_esperado=preparada.id,
    ) is CodigoAutorizacion.REPETIDA


async def test_e2e_fallo_del_registro_durable_no_acepta(
    directorio_autorizaciones,
) -> None:
    ruta, _fd = directorio_autorizaciones
    preparada = await preparar()

    def reclamar(_id: str) -> bool:
        raise registro.RegistroNoDisponibleError("persistencia no acreditada")

    assert verificar_autorizacion(
        preparada.autorizacion, clave=CLAVE, ahora=AHORA,
        reclamar_uso=reclamar, id_esperado=preparada.id,
    ) is CodigoAutorizacion.NO_DISPONIBLE
    assert list(ruta.iterdir()) == []


# ── Listas cerradas y concurrencia real con el registro durable ──────────────


def test_codigos_cerrados_de_la_composicion() -> None:
    assert {codigo.value for codigo in emisor.ResultadoAutorizacion} == {
        "no_habilitada", "confirmacion_requerida", "contrasena_invalida",
        "autenticacion_no_activada", "contrasena_incorrecta", "ocupada",
        "bloqueada", "no_disponible", "preparada",
    }


def test_codigos_cerrados_del_verificador() -> None:
    assert {codigo.value for codigo in CodigoAutorizacion} == {
        "aceptada", "invalida", "caducada", "repetida", "no_disponible",
    }


async def test_procesos_concurrentes_solo_una_aceptacion(
    directorio_autorizaciones,
) -> None:
    ruta, _fd = directorio_autorizaciones
    preparada = await preparar()
    assert preparada.autorizacion is not None
    token = preparada.autorizacion
    code = (
        "import os,sys\n"
        "from deploy.ops.registro_repeticiones_ops4 import crear_reclamador_durable\n"
        "from deploy.ops.verificador_autorizacion_ops4 import verificar_autorizacion\n"
        "fd=os.open(sys.argv[1], os.O_RDONLY|os.O_DIRECTORY)\n"
        "try:\n"
        "    print(verificar_autorizacion(bytes.fromhex(sys.argv[2]),\n"
        "        clave=bytes.fromhex(sys.argv[3]), ahora=int(sys.argv[4]),\n"
        "        reclamar_uso=crear_reclamador_durable(fd),\n"
        "        id_esperado=sys.argv[5]).value, flush=True)\n"
        "finally: os.close(fd)\n"
    )
    argv = [
        sys.executable, "-c", code, str(ruta), token.hex(), CLAVE.hex(),
        str(AHORA), ID,
    ]
    repo = Path(__file__).resolve().parents[1]
    processes = []
    try:
        for _ in range(6):
            processes.append(subprocess.Popen(
                argv, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ))
        resultados = [p.communicate(timeout=20) for p in processes]
        assert all(p.returncode == 0 for p in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()
    codigos = [salida.strip().decode() for salida, _err in resultados]
    assert codigos.count("aceptada") == 1
    assert codigos.count("repetida") == 5
    assert list(ruta.iterdir()) == [ruta / f"{registro.PREFIJO_AUTORIZACION}{ID}"]
